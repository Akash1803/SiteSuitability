"""Stage 2 - CLIP (clip.tn.gov.in) subdivision list per survey. Cached in portal.clip_*; only surveys not yet fetched are queried."""
import time

import geopandas as gpd
import pandas as pd

from .. import db
from ..util import split_vcode, survey_sort_key

NAME, TITLE = "clip", "CLIP subdivision list"
URL = "https://clip.tn.gov.in/clip/landstatus.html?id=7"


def _driver(show):
    from selenium import webdriver
    o = webdriver.ChromeOptions()
    if not show:
        o.add_argument("--headless=new")
        o.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    o.add_argument("--window-size=1400,1000")
    d = webdriver.Chrome(options=o)
    d.get(URL); time.sleep(5)
    return d


def fetch(pending, ctx, show=False):
    """pending: list of (vcode, survey_no). Writes results to the cache as it goes."""
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
    d = _driver(show)

    def sel(eid, val):
        WebDriverWait(d, 15).until(EC.element_to_be_clickable((By.ID, eid)))
        Select(d.find_element(By.ID, eid)).select_by_value(val); time.sleep(1)
    try:
        for i, (vc, sn) in enumerate(pending, 1):
            if ctx.stopped():
                break
            if i % 250 == 0:
                d.quit(); d = _driver(show)
            dd, tt, vv = split_vcode(vc)
            try:
                d_, t_, v_ = vc.split("_"); sel("dist", d_); sel("taluk", t_); sel("village", v_)
                box = d.find_element(By.ID, "surveyNo_integration"); box.clear(); box.send_keys(sn); time.sleep(2)
                dd_el = d.find_element(By.ID, "subDivNo_integration")
                ActionChains(d).move_to_element(dd_el).click().perform(); time.sleep(2)
                subs = [o.text.strip() for o in d.find_elements(By.XPATH, "//select[@id='subDivNo_integration']/option") if o.text.strip()]
                rows = [(vc, sn, s, "Success") for s in subs] or [(vc, sn, "-", "No Subdivision")]
                status = "Success"
            except Exception as e:  # keep going; the survey is retried on the next run
                rows, status = [], f"Error: {repr(e)[:120]}"
            with db.connect() as c:
                if rows:
                    c.execute("DELETE FROM portal.clip_subdivision WHERE vcode = %s AND survey_no = %s", (vc, sn))
                    with c.cursor() as cur:
                        cur.executemany("INSERT INTO portal.clip_subdivision (vcode, survey_no, sub_division, status) VALUES (%s,%s,%s,%s)", rows)
                    c.execute("""INSERT INTO portal.clip_survey_done (vcode, survey_no, status) VALUES (%s,%s,%s)
                                 ON CONFLICT (vcode, survey_no) DO UPDATE SET status = EXCLUDED.status, fetched_at = now()""", (vc, sn, status))
            ctx.progress(i, len(pending), f"CLIP {vc} survey {sn}: {len(rows)} subdivisions" if rows else f"CLIP {vc} {sn}: {status}")
    finally:
        d.quit()


def run(site, ctx):
    sv = gpd.read_file(site.parcels)
    keys = sorted({(v, str(s)) for v, s in zip(sv.village_code, sv.survey_no)}, key=lambda k: (k[0], survey_sort_key(k[1])))
    with db.connect() as c:
        done = {(a, b) for a, b in c.execute("SELECT vcode, survey_no FROM portal.clip_survey_done WHERE status = 'Success'")}
    pending = [k for k in keys if k not in done]
    ctx.log(f"CLIP: {len(keys)} surveys, {len(keys) - len(pending)} already in the cache, {len(pending)} to fetch")
    if pending:
        fetch(pending, ctx, show=ctx.options.get("show_browser", False))
    with db.connect() as c:
        rows = c.execute("SELECT vcode, survey_no, sub_division, status FROM portal.clip_subdivision").fetchall()
    df = pd.DataFrame(rows, columns=["vcode", "survey_no", "sub_division", "response_status"])
    df = df[[k in set(keys) for k in zip(df.vcode, df.survey_no)]].copy()
    df[["district_id", "taluk_id", "village_id"]] = pd.DataFrame([split_vcode(v) for v in df.vcode], index=df.index)
    df["_k"] = df.survey_no.map(survey_sort_key)
    df = df.sort_values(["vcode", "_k", "sub_division"])
    df_v = list(df.vcode)
    df = df[["survey_no", "sub_division", "district_id", "taluk_id", "village_id", "response_status"]]
    df.to_excel(site.clip_output, index=False)
    got = set(zip(df_v, df.survey_no))
    miss = [k for k in keys if k not in got]
    db.register_document(site.site_id, "clip_output", site.clip_output)
    if miss:
        raise RuntimeError(f"CLIP still missing for {len(miss)} surveys (run the stage again): {miss[:10]}")
    return f"{len(df)} subdivisions for {len(keys)} surveys"

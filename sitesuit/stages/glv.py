"""Stage 4 - GLV (TNReginet survey-wise search).
Step 1: map each revenue village to its TNReginet SRO / village ids (matched by name, cached, editable in GLV_Village_Map_<site>.xlsx).
Step 2: survey-wise search for every survey not yet in portal.glv. Output GLV_Output_<site>.xlsx (GLV_Survey_Wise + Survey_Summary)."""
import difflib
import re
import time

import geopandas as gpd
import pandas as pd

from .. import db
from ..reginet import Reginet
from ..util import norm_name, split_vcode, survey_sort_key

NAME, TITLE = "glv", "Guideline value (TNReginet)"
DONE = ("Success", "Nothing Found")
MIN_SCORE = 0.80


class NeedsReview(Exception):
    """raised when a village could not be matched; the map Excel must be filled in"""


def village_map(site, ctx, vills):
    """vills: [(vcode, village name)] -> {vcode: (zone, sro, village_id)}"""
    # 1. user edits in the map Excel win
    if site.glv_map.exists():
        m = pd.read_excel(site.glv_map, dtype=str).fillna("")
        with db.connect() as c:
            for r in m.itertuples():
                if r.village_list_id and r.sro_list_id:
                    c.execute("""INSERT INTO portal.reginet_village (vcode, zone_list_id, sro_list_id, sro_name, village_list_id, reginet_name, match_score, confirmed)
                                 VALUES (%s,%s,%s,%s,%s,%s,%s,true) ON CONFLICT (vcode) DO UPDATE SET zone_list_id=EXCLUDED.zone_list_id,
                                 sro_list_id=EXCLUDED.sro_list_id, sro_name=EXCLUDED.sro_name, village_list_id=EXCLUDED.village_list_id,
                                 reginet_name=EXCLUDED.reginet_name, confirmed=true, updated_at=now()""",
                              (r.vcode, r.zone_list_id or str(split_vcode(r.vcode)[0]), r.sro_list_id, r.sro_name, r.village_list_id, r.reginet_name, None))
    with db.connect() as c:
        known = {r[0]: r[1:] for r in c.execute("SELECT vcode, zone_list_id, sro_list_id, sro_name, village_list_id, reginet_name, match_score, confirmed FROM portal.reginet_village WHERE vcode = ANY(%s)", ([v for v, _ in vills],))}
    todo = [(v, n) for v, n in vills if v not in known or not known[v][3]]
    if todo:
        zones = sorted({str(split_vcode(v)[0]) for v, _ in todo})
        rg = Reginet(show=ctx.options.get("show_browser", False), log=ctx.log)
        try:
            for z in zones:
                with db.connect() as c:
                    opts = c.execute("SELECT sro_list_id, sro_name, village_list_id, village_name FROM portal.reginet_option WHERE zone_list_id = %s", (z,)).fetchall()
                if not opts:
                    ctx.log(f"TNReginet: listing SROs and villages of district {z} (one time) ...")
                    opts = rg.list_villages(z)
                    with db.connect() as c:
                        with c.cursor() as cur:
                            cur.executemany("""INSERT INTO portal.reginet_option VALUES (%s,%s,%s,%s,%s, now()) ON CONFLICT DO NOTHING""", [(z, *o) for o in opts])
                    ctx.log(f"  {len(opts)} villages under {len({o[0] for o in opts})} SROs")
                for v, n in [t for t in todo if str(split_vcode(t[0])[0]) == z]:
                    key = norm_name(n)
                    scored = sorted(((difflib.SequenceMatcher(None, key, norm_name(re.sub(r"\(.*?\)", "", o[3]))).ratio(), o) for o in opts), key=lambda x: -x[0])
                    best = scored[0] if scored else (0, None)
                    tie = len(scored) > 1 and scored[1][0] == best[0] and scored[1][1][2] != best[1][2]
                    with db.connect() as c:
                        c.execute("""INSERT INTO portal.reginet_village (vcode, zone_list_id, sro_list_id, sro_name, village_list_id, reginet_name, match_score, confirmed)
                                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vcode) DO UPDATE SET zone_list_id=EXCLUDED.zone_list_id, sro_list_id=EXCLUDED.sro_list_id,
                                     sro_name=EXCLUDED.sro_name, village_list_id=EXCLUDED.village_list_id, reginet_name=EXCLUDED.reginet_name,
                                     match_score=EXCLUDED.match_score, confirmed=EXCLUDED.confirmed, updated_at=now()""",
                                  (v, z, best[1][0] if best[1] else None, best[1][1] if best[1] else None, best[1][2] if best[1] else None,
                                   best[1][3] if best[1] else None, float(best[0]), bool(best[0] >= MIN_SCORE and not tie)))
        finally:
            rg.quit()
        with db.connect() as c:
            known = {r[0]: r[1:] for r in c.execute("SELECT vcode, zone_list_id, sro_list_id, sro_name, village_list_id, reginet_name, match_score, confirmed FROM portal.reginet_village WHERE vcode = ANY(%s)", ([v for v, _ in vills],))}
    m = pd.DataFrame([{"vcode": v, "village": n, "zone_list_id": known.get(v, [None] * 7)[0], "sro_list_id": known.get(v, [None] * 7)[1],
                       "sro_name": known.get(v, [None] * 7)[2], "village_list_id": known.get(v, [None] * 7)[3], "reginet_name": known.get(v, [None] * 7)[4],
                       "match_score": known.get(v, [None] * 7)[5], "confirmed": known.get(v, [None] * 7)[6]} for v, n in vills])
    if site.glv_map.exists():   # keep a typed indicative rate
        old = pd.read_excel(site.glv_map, dtype=str)
        if "indicative_rate_acre" in old.columns:
            m = m.merge(old[["vcode", "indicative_rate_acre"]], on="vcode", how="left")
    if "indicative_rate_acre" not in m.columns:
        m["indicative_rate_acre"] = ""
    m.to_excel(site.glv_map, index=False)
    bad = m[~m.confirmed.fillna(False).astype(bool)]
    if len(bad):
        raise NeedsReview(f"check the TNReginet village match for {', '.join(bad.village)} in {site.glv_map.name} "
                          f"(fill sro_list_id / village_list_id, then run the GLV stage again)")
    return {r.vcode: (str(r.zone_list_id), str(r.sro_list_id), str(r.village_list_id)) for r in m.itertuples()}


def run(site, ctx):
    sv = gpd.read_file(site.parcels); sv["survey_no"] = sv.survey_no.astype(str)
    vills = list(dict.fromkeys(zip(sv.village_code, sv.village)))
    vmap = village_map(site, ctx, vills)
    keys = sorted({(v, s) for v, s in zip(sv.village_code, sv.survey_no)}, key=lambda k: (k[0], survey_sort_key(k[1])))
    with db.connect() as c:
        have = {(a, b) for a, b in c.execute("SELECT DISTINCT vcode, survey_no FROM portal.glv WHERE status = ANY(%s)", (list(DONE),))}
    pending = [k for k in keys if k not in have]
    ctx.log(f"GLV: {len(keys)} surveys, {len(keys) - len(pending)} cached, {len(pending)} to search (about {len(pending) * 9 / 60:.0f} min)")
    if pending:
        rg = Reginet(show=ctx.options.get("show_browser", False), log=ctx.log)
        try:
            for attempt in range(3):
                left = []
                pause = 0
                for i, (vc, sn) in enumerate(pending, 1):
                    if ctx.stopped():
                        raise RuntimeError("stopped by user")
                    st, rows = rg.survey(*vmap[vc], sn)
                    while "403" in st and pause < 600:   # TNReginet refuses for a few minutes now and then: wait it out, do not burn the list
                        pause = min(max(60, pause * 2), 600)
                        ctx.log(f"GLV: TNReginet answers 403 Forbidden - waiting {pause} s"); rg.quit(); time.sleep(pause)
                        st, rows = rg.survey(*vmap[vc], sn)
                    if "403" not in st:
                        pause = 0
                    if st not in DONE:   # the portal often times out once; one immediate retry on a fresh page
                        ctx.log(f"GLV {vc} survey {sn}: {st} - retrying once"); rg.recover() if rg.d else None
                        st, rows = rg.survey(*vmap[vc], sn)
                    if st in DONE:
                        with db.connect() as c:
                            c.execute("DELETE FROM portal.glv WHERE vcode = %s AND survey_no = %s", (vc, sn))
                            data = [(vc, sn, j, r["Subdivision Number"], r["Guideline_Value_British"], r["Guideline_Value_Metric"], r["Land_Classification"],
                                     r["Effective_Start_Date"], st) for j, r in enumerate(rows, 1)] or [(vc, sn, 1, None, None, None, None, None, st)]
                            with c.cursor() as cur:
                                cur.executemany("INSERT INTO portal.glv VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())", data)
                    else:
                        left.append((vc, sn))
                    ctx.progress(i, len(pending), f"GLV {vc} survey {sn}: {st} ({len(rows)} rows)")
                if not left:
                    break
                ctx.log(f"GLV retry pass {attempt + 1}: {len(left)} surveys"); pending = left
        finally:
            rg.quit()
    with db.connect() as c:
        rows = c.execute("SELECT vcode, survey_no, row_no, subdivision, value_british, value_metric, classification, effective_date, status FROM portal.glv WHERE vcode = ANY(%s) ORDER BY vcode, survey_no, row_no",
                         (sorted({k[0] for k in keys}),)).fetchall()
    g = pd.DataFrame(rows, columns=["vcode", "survey_no", "row_no", "Subdivision Number", "Guideline_Value_British", "Guideline_Value_Metric", "Land_Classification", "Effective_Start_Date", "Status"])
    g = g[[k in set(keys) for k in zip(g.vcode, g.survey_no)]].copy()
    names = dict(vills)
    g["village"] = g.vcode.map(names)
    g[["district_id", "taluk_id", "village_id"]] = pd.DataFrame([split_vcode(v) for v in g.vcode], index=g.index)
    g[["zone_list_id", "sro_list_id", "village_list_id"]] = pd.DataFrame([vmap[v] for v in g.vcode], index=g.index)
    g["_k"] = g.survey_no.map(survey_sort_key); g = g.sort_values(["village", "_k", "row_no"])
    out = g[["village", "survey_no", "district_id", "taluk_id", "village_id", "zone_list_id", "sro_list_id", "village_list_id", "Subdivision Number",
             "Guideline_Value_British", "Guideline_Value_Metric", "Land_Classification", "Effective_Start_Date", "Status"]]
    num = pd.to_numeric(out.Guideline_Value_British.str.extract(r"^\s*([\d.]+)")[0], errors="coerce")
    unit = out.Guideline_Value_British.str.extract(r"/\s*(.*)$")[0].str.strip()
    ss = out.assign(num=num, unit=unit).groupby(["village", "survey_no"], sort=False).agg(
        subdiv_rows=("Subdivision Number", lambda s: s.notna().sum()), rate_min=("num", "min"), rate_max=("num", "max"),
        unit=("unit", lambda s: "; ".join(sorted(set(s.dropna())))), classes=("Land_Classification", lambda s: "; ".join(sorted(set(s.dropna())))),
        status=("Status", "first")).reset_index()
    with pd.ExcelWriter(site.glv_output, engine="openpyxl") as w:
        out.to_excel(w, sheet_name="GLV_Survey_Wise", index=False); ss.to_excel(w, sheet_name="Survey_Summary", index=False)
    db.register_document(site.site_id, "glv_output", site.glv_output)
    miss = [k for k in keys if k not in set(zip(g.vcode, g.survey_no))]
    if miss:
        raise RuntimeError(f"GLV still missing for {len(miss)} surveys - run the stage again: {miss[:10]}")
    return f"{len(out)} GLV rows; " + ", ".join(f"{k} {v}" for k, v in ss.status.value_counts().items())

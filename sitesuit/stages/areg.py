"""Stage 3 - A-register (Tamilnilam / tnagrisnet) for every CLIP subdivision, 4 requests in parallel on kept-alive connections, cached in portal.areg.
Writes the raw Excel and the consolidated A-register Excel (village / land type / govt-patta / sensitive flags / survey summary / records)."""
import io
import contextlib
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import pandas as pd
import requests
from psycopg.types.json import Jsonb

from .. import db
from ..util import GOVT, HA_TO_ACRE, split_vcode, survey_sort_key, vcode

NAME, TITLE = "areg", "A-register (Tamilnilam)"
API = "https://www.tnagrisnet.tn.gov.in/RES/landdetail/index/{d}/{t}/{v}/{s}/{sd}"
FIELDS = [("pattaNo", "patta_number"), ("GovtPri", "government_priority"), ("extHect", "extent_hectares"), ("extAres", "extent_ares"),
          ("landTypeEng", "land_type_english"), ("Poramboke", "poramboke"), ("cultivable", "cultivable"), ("remarks", "remarks"), ("remarks1", "remarks1"),
          # land-quality fields of the settlement register (soil class / sort / tharam codes, assessment Rs per hectare, irrigation source)
          ("soilTypPri", "soil_class"), ("soilTypSec", "soil_sort"), ("soilClass", "tharam"), ("taxHect", "assessment_rs_ha"), ("IrrSource", "irrigation_source")]
SOIL_KEYS = ("soil_class", "soil_sort", "tharam", "assessment_rs_ha", "irrigation_source")
SENSITIVE = [("Forest", "காடு|வனம்|forest"), ("Water body", "ஏரி|குளம்|கண்மாய்|ஊரணி|குட்டை|தாங்கல்|tank|pond"),
             ("Channel", "வாய்க்கால்|ஓடை|ஒடை|odai"), ("Temple/Church/Mosque", "கோயில்|கோவில்|ஆலயம்|மசூதி|தேவாலய|temple|church|mosque"),
             ("Burial", "சுடுகாடு|மயான|இடுகாடு|burial"), ("Village site", "நத்தம்|village site"), ("NH land", "நெடுஞ்சாலை|highway"), ("Well", "well|கிணறு")]


def _clean_owner(n):
    return " ".join(re.sub(r"[^\w\s஀-௿]", "", n).split()).strip()


_local = threading.local()


def _session():
    """one kept-alive connection per worker thread: a new TLS connection per record cost ~1.2 s, a kept-alive one ~0.15 s"""
    if getattr(_local, "s", None) is None:
        _local.s = requests.Session()
    return _local.s


def _conn():
    """one database connection per worker thread (opening one per record cost ~0.16 s)"""
    c = getattr(_local, "c", None)
    if c is None or c.closed:
        import psycopg
        from ..config import SETTINGS
        c = _local.c = psycopg.connect(SETTINGS.database_url, autocommit=True)
    return c


def fetch_one(vc, sn, sd):
    d, t, v = split_vcode(vc)
    url = API.format(d=d, t=t, v=v, s=sn, sd=sd if sd not in ("", "-") else "-")
    j, err = None, None
    for _ in range(3):
        try:
            r = _session().get(url, timeout=40); r.raise_for_status(); j = r.json(); break
        except Exception as e:
            err = e; _local.s = None; time.sleep(3)
    rec = {k: None for _, k in FIELDS}
    if j is None:
        return f"Error: {repr(err)[:100]}", rec
    if j == {"0": "Enter valid Survey No and Subdivision"}:
        return "Invalid Survey No or Subdivision", rec
    a = (j.get("aregData") or {}).get("areg", {}) or {}
    for src, k in FIELDS:
        rec[k] = (a.get(src) or "").strip()
    ch = (j.get("chittaData") or {}).get("chitta")
    ch = ch if isinstance(ch, list) else ([ch] if isinstance(ch, dict) else [])
    own = [o for o in (_clean_owner(x.get("owner") or "") for x in ch) if o]
    rec["owner_details"] = ", ".join(own) if own else "-"
    rec["owner_update_dates"] = ", ".join(x for x in ((o.get("updationdt") or "").strip() for o in ch) if x) or "-"
    rec["owner_number"] = len(own)
    return "Success", rec


def _store(vc, sn, sd, status, rec):
    sql = """INSERT INTO portal.areg (vcode, survey_no, sub_division, status, record) VALUES (%s,%s,%s,%s,%s)
             ON CONFLICT (vcode, survey_no, sub_division) DO UPDATE SET status=EXCLUDED.status, record=EXCLUDED.record, fetched_at=now()"""
    try:
        _conn().execute(sql, (vc, sn, sd, status, Jsonb(rec)))
    except Exception:            # connection dropped: open a fresh one for this record
        _local.c = None
        with db.connect() as c:
            c.execute(sql, (vc, sn, sd, status, Jsonb(rec)))


def run(site, ctx):
    clip = pd.read_excel(site.clip_output, dtype=str)
    clip["vcode"] = [vcode(a, b, c) for a, b, c in zip(clip.district_id, clip.taluk_id, clip.village_id)]
    clip["sub_division"] = clip.sub_division.fillna("-")
    keys = list(dict.fromkeys(zip(clip.vcode, clip.survey_no, clip.sub_division)))
    with db.connect() as c:
        have = {(a, b, s) for a, b, s in c.execute("SELECT vcode, survey_no, sub_division FROM portal.areg WHERE status = 'Success'")}
    pending = [k for k in keys if k not in have]
    ctx.log(f"A-register: {len(keys)} subdivisions, {len(keys) - len(pending)} cached, {len(pending)} to fetch (about {len(pending) / 10 / 60:.0f} min)")

    def job(k):
        if ctx.stopped():
            return k, "Stopped", {}
        st, rec = fetch_one(*k)
        if st == "Invalid Survey No or Subdivision" and k[2] == "-":
            st1, rec1 = fetch_one(k[0], k[1], "1")      # CLIP lists '-' but the register may hold only '<survey>/1' (Kattupakkam 500)
            if st1 == "Success":
                _store(k[0], k[1], "1", st1, rec1)
                return k, "Replaced by /1", rec1
        _store(*k, st, rec)
        return k, st, rec
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, (k, st, _) in enumerate(ex.map(job, pending), 1):
            if i % 25 == 0 or i == len(pending):
                ctx.progress(i, len(pending), f"A-register {i}/{len(pending)}")
    if ctx.stopped():
        raise RuntimeError("stopped by user")
    # replaced '-' rows -> point the CLIP list at '/1'
    with db.connect() as c:
        rows = c.execute("SELECT vcode, survey_no, sub_division, status, record FROM portal.areg WHERE vcode = ANY(%s)", (sorted({k[0] for k in keys}),)).fetchall()
    cache = {(a, b, s): (st, rec) for a, b, s, st, rec in rows}
    out = []
    for vc, sn, sd in keys:
        if (vc, sn, sd) not in cache or (cache[(vc, sn, sd)][0] != "Success" and (vc, sn, "1") in cache and sd == "-"):
            if (vc, sn, "1") in cache:
                sd = "1"
        st, rec = cache.get((vc, sn, sd), ("Not fetched", {}))
        d, t, v = split_vcode(vc)
        out.append({"survey_no": sn, "sub_division": sd, "district_id": d, "taluk_id": t, "village_id": v, "vcode": vc, "areg_status": st, **(rec or {})})
    raw = pd.DataFrame(out)
    raw.drop(columns=["vcode"]).to_excel(site.areg_raw, index=False)
    bad = raw[raw.areg_status != "Success"]
    summary = build_excel(site, raw)
    db.register_document(site.site_id, "areg_excel", site.areg_excel)
    db.save_summary(site.site_id, {"areg": summary})
    if len(bad):
        ctx.log(f"A-register not found for {len(bad)} subdivisions: {bad[['vcode', 'survey_no', 'sub_division', 'areg_status']].values.tolist()[:15]}")
    return f"{len(raw) - len(bad)} of {len(raw)} subdivisions found; site {summary['site_acre']:.2f} ac (patta {summary['patta_acre']:.2f}, govt {summary['govt_acre']:.2f})"


def build_excel(site, a):
    sv = gpd.read_file(site.parcels); sv["survey_no"] = sv.survey_no.astype(str)
    names = dict(zip(sv.village_code, sv.village))
    a = a.copy(); a["village"] = a.vcode.map(names); a["survey_no"] = a.survey_no.astype(str)
    key = sv[["village", "survey_no", "split", "puvi_acre", "inside_acre", "inside_pct"]].copy(); key["split"] = key.split.astype(bool)
    a = a.merge(key[["village", "survey_no", "split"]], on=["village", "survey_no"], how="left")
    ext = pd.to_numeric(a.extent_hectares, errors="coerce").fillna(0) + pd.to_numeric(a.extent_ares, errors="coerce").fillna(0) / 100
    a["areg_acre"] = (ext * HA_TO_ACRE).round(4); a.loc[a.areg_status != "Success", "areg_acre"] = None
    a["Unique ID 1"] = a.vcode + "_" + a.survey_no; a["Unique ID 2"] = a["Unique ID 1"] + "/" + a.sub_division.astype(str)

    def flag(r):
        t = " ".join(str(r.get(c)) for c in ("remarks", "remarks1", "poramboke") if str(r.get(c)) not in ("nan", "", "-", "None")).lower()
        return next((k for k, p in SENSITIVE if re.search(p, t)), "")
    a["sensitive_flag"] = a.apply(flag, axis=1)
    cols = ["village", "survey_no", "sub_division", "Unique ID 1", "Unique ID 2", "district_id", "taluk_id", "village_id", "split", "areg_status", "patta_number",
            "government_priority", "extent_hectares", "extent_ares", "areg_acre", "land_type_english", "poramboke", "cultivable", "owner_details",
            "owner_update_dates", "owner_number", "remarks", "remarks1", "sensitive_flag"]
    for c in cols:
        if c not in a.columns:
            a[c] = None
    rec = a[cols].copy(); rec["_k"] = rec.survey_no.map(survey_sort_key)
    rec = rec.sort_values(["village", "_k", "sub_division"]).drop(columns="_k")
    ok = rec[rec.areg_status == "Success"]
    own = lambda s: "Govt" if set(s) == {GOVT} else ("Patta" if GOVT not in set(s) else "Mixed")
    summ = ok.groupby(["village", "survey_no"]).agg(subdivisions=("sub_division", "count"), areg_acre=("areg_acre", "sum"),
                                                   land_type=("land_type_english", lambda s: "/".join(sorted(set(s.dropna())))), ownership=("government_priority", own),
                                                   sensitive=("sensitive_flag", lambda s: ", ".join(sorted(set(x for x in s if x))))).reset_index()
    summ = key.merge(summ, on=["village", "survey_no"], how="left")
    summ["site_acre"] = summ.areg_acre.where(~summ.split, summ.inside_acre).round(4)
    summ["area_basis"] = summ.split.map({False: "A-register (full survey inside)", True: "Geometry inside boundary (split survey)"})
    summ["_k"] = summ.survey_no.map(survey_sort_key); summ = summ.sort_values(["village", "_k"]).drop(columns="_k")
    vill = summ.groupby("village").agg(surveys=("survey_no", "count"), subdivisions=("subdivisions", "sum"), puvi_acre=("puvi_acre", "sum"),
                                       areg_acre=("areg_acre", "sum"), site_acre=("site_acre", "sum")).round(2).reset_index()
    vill = pd.concat([vill, pd.DataFrame([{"village": "TOTAL", **{c: round(vill[c].sum(), 2) for c in ("surveys", "subdivisions", "puvi_acre", "areg_acre", "site_acre")}}])])
    fac = summ.set_index(["village", "survey_no"]).eval("site_acre / areg_acre").fillna(0)
    ok2 = ok.copy(); ok2["site_acre"] = [r.areg_acre * (fac.get((r.village, r.survey_no), 1) if r.split else 1) for r in ok2.itertuples()]
    lt = ok2.groupby("land_type_english").site_acre.sum().round(2).reset_index().rename(columns={"land_type_english": "land_type", "site_acre": "acre"})
    go = ok2.assign(ownership=ok2.government_priority.map(lambda x: "Govt" if x == GOVT else "Patta")).groupby("ownership").site_acre.sum().round(2).reset_index().rename(columns={"site_acre": "acre"})
    fl = summ[summ.sensitive.fillna("") != ""][["village", "survey_no", "land_type", "ownership", "sensitive", "split", "site_acre"]]
    with pd.ExcelWriter(site.areg_excel, engine="openpyxl") as w:
        vill.to_excel(w, sheet_name="Village_Summary", index=False); lt.to_excel(w, sheet_name="Land_Type_Summary", index=False)
        go.to_excel(w, sheet_name="Govt_vs_Patta", index=False); fl.to_excel(w, sheet_name="Sensitive_Flags", index=False)
        summ.to_excel(w, sheet_name="Survey_Summary", index=False); rec.to_excel(w, sheet_name="AReg_Records", index=False)
    g = dict(zip(go.ownership, go.acre))
    return {"site_acre": float(summ.site_acre.sum()), "patta_acre": float(g.get("Patta", 0)), "govt_acre": float(g.get("Govt", 0)),
            "records": int(len(rec)), "found": int(len(ok)), "sensitive_surveys": fl[["village", "survey_no", "sensitive"]].values.tolist()}

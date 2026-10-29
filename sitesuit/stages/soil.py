"""Stage - soil and land quality from the A-register (settlement register fields that come with every subdivision):
soil class / sort / tharam codes, assessment (land revenue) rate per hectare, irrigation source.
Fetches only the fields still missing from the cache, adds them to the parcel layer and the master Excel, renders the soil map."""
import json
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import pandas as pd

from .. import db
from .areg import SOIL_KEYS, _store, fetch_one
from .master import write_geojson
from .maps import qgis_render

NAME, TITLE = "soil", "Soil + land quality slide"


def _clean(v):
    s = "" if v is None else str(v).strip()
    return "" if s in ("-", "None", "nan") else s


def run(site, ctx):
    sm = pd.read_excel(site.master, sheet_name="Subdivision_Master", dtype=str)
    sm = sm[sm.in_site.str.lower() == "true"].copy()
    keys = [(u[:9], s, d) for u, s, d in zip(sm.unique_id, sm.survey_no, sm.subdiv_no)]
    with db.connect() as c:
        cache = {(a, b, s_): r for a, b, s_, r in c.execute("SELECT vcode, survey_no, sub_division, record FROM portal.areg WHERE vcode = ANY(%s)",
                                                              (sorted({k[0] for k in keys}),))}
    todo = [k for k in keys if "tharam" not in (cache.get(k) or {})]
    ctx.log(f"soil fields: {len(keys)} subdivisions, {len(keys) - len(todo)} cached, {len(todo)} to fetch from the A-register")

    def job(k):
        if ctx.stopped():
            return k, None
        st, rec = fetch_one(*k)
        if st == "Success":
            _store(*k, st, rec)
        return k, rec if st == "Success" else None
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, (k, rec) in enumerate(ex.map(job, todo), 1):
            if rec:
                cache[k] = rec
            if i % 25 == 0 or i == len(todo):
                ctx.progress(i, len(todo), f"soil fields {i}/{len(todo)}")
    if ctx.stopped():
        raise RuntimeError("stopped by user")
    rows = []
    for (vc, sn, sd), u in zip(keys, sm.unique_id):
        r = cache.get((vc, sn, sd)) or {}
        rows.append({"unique_id": u, "soil_class": _clean(r.get("soil_class")), "soil_sort": _clean(r.get("soil_sort")), "tharam": _clean(r.get("tharam")),
                     "assessment_rs_ha": pd.to_numeric(_clean(r.get("assessment_rs_ha")) or None, errors="coerce"), "irrigation_source": _clean(r.get("irrigation_source"))})
    so = pd.DataFrame(rows)
    so["soil_code"] = [(f"{a}-{b}" if a and a != "0" else "Govt / no soil class") for a, b in zip(so.soil_class, so.soil_sort)]
    so["tharam_label"] = [("Tharam " + t if t and t != "0" else "Govt / not assessed") for t in so.tharam]
    sm = sm.merge(so, on="unique_id", how="left"); sm["site_acre"] = pd.to_numeric(sm.site_acre, errors="coerce")
    g = gpd.read_file(site.subdivisions)
    g = g.drop(columns=[c for c in so.columns if c in g.columns and c != "unique_id"]).merge(so, on="unique_id", how="left")
    write_geojson(g[[c for c in g.columns if c != "geometry"] + ["geometry"]], site.subdivisions)
    db.save_parcels(site.site_id, g)
    by_t = sm.groupby("tharam_label").agg(subdivisions=("unique_id", "size"), site_acre=("site_acre", "sum"),
                                          rate_min=("assessment_rs_ha", "min"), rate_max=("assessment_rs_ha", "max")).round(2).reset_index()
    by_c = sm.groupby(["land_type_english", "soil_code"]).agg(subdivisions=("unique_id", "size"), site_acre=("site_acre", "sum")).round(2).reset_index()
    irr = sm.assign(irr=sm.irrigation_source.replace("", "Not recorded")).groupby("irr").site_acre.sum().round(2)
    sheets = pd.read_excel(site.master, sheet_name=None)
    sheets["Soil_Land_Quality"] = pd.concat([by_t.assign(table="By tharam"), by_c.assign(table="By land type and soil class-sort")], ignore_index=True)
    with pd.ExcelWriter(site.master, engine="openpyxl") as w:
        for n, d in sheets.items():
            d.to_excel(w, sheet_name=n, index=False)
    qgis_render(site, ctx, only=["map_soil"])
    A = float(sm.site_acre.sum())
    pat = sm[sm.tharam_label != "Govt / not assessed"]
    wavg = float((pat.assessment_rs_ha * pat.site_acre).sum() / pat.site_acre.sum()) if pat.site_acre.sum() else 0.0
    data = {"total": A, "tharam": [{"label": r.tharam_label, "acre": float(r.site_acre), "n": int(r.subdivisions),
                                    "rate": (f"Rs {r.rate_min:.2f}" + (f" - {r.rate_max:.2f}" if r.rate_max != r.rate_min else "") + " /ha") if pd.notna(r.rate_min) and r.rate_max > 0 else "-"}
                                   for r in by_t.sort_values("site_acre", ascending=False).itertuples()],
            "irrigation": {k: float(v) for k, v in irr.items()}, "assessment_wavg": wavg,
            "classes": int(pat.soil_code.nunique()), "top_code": (pat.groupby("soil_code").site_acre.sum().idxmax() if len(pat) else "-")}
    db.save_summary(site.site_id, {"soil": data})
    return (f"{len(keys) - len(todo)} cached + {len(todo)} fetched; " + ", ".join(f"{t['label']} {t['acre']:.2f} ac" for t in data["tharam"][:5])
            + f"; mean assessment Rs {wavg:.2f}/ha")

"""Stage - government land classification: every government subdivision inside the site, classified from its A-register remark
(odai, railway, pathway, tank ...) or, with no remark, its land type and poramboke code. Map + MIS table (village, land type,
soil grade, surveys). Poramboke code names come from POROMBOKE_CODES (Excel: code, name) when the team has filled it in."""
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .. import db
from ..config import SETTINGS
from ..util import survey_sort_key
from .maps import qgis_render

NAME, TITLE = "govtland", "Government land classification slide"

# Tamil remark words -> English (checked in order; the first match wins)
REMARKS = [("ரெயில்வே", "Railway land"), ("இரயில்", "Railway land"), ("நெடுஞ்சாலை", "Highway land"), ("வண்டிப்பாதை", "Cart track"), ("வண்டிபாதை", "Cart track"),
           ("பாதை", "Pathway"), ("சாலை", "Road"), ("ஓடை", "Odai (stream)"), ("கால்வாய்", "Canal / channel"), ("வாய்க்கால்", "Channel"),
           ("ஏரி", "Eri (tank)"), ("குளம்", "Kulam (pond)"), ("குட்டை", "Kuttai (pond)"), ("தாங்கல்", "Thangal (tank)"), ("கண்மாய்", "Kanmoi (tank)"),
           ("மயான", "Burial ground"), ("சுடுகாடு", "Burial ground"), ("இடுகாடு", "Burial ground"), ("கோயில்", "Temple"), ("கோவில்", "Temple"),
           ("நத்தம்", "Natham (village site)"), ("மேய்க்கால்", "Meikkal (grazing land)"), ("காடு", "Forest"), ("மலை", "Hill"), ("களம்", "Threshing floor"),
           ("பள்ளி", "School"), ("அனாதீனம்", "Anadheenam (unassigned)"), ("தரிசு", "Tharisu (waste land)")]
PALETTE = ["#1565c0", "#00838f", "#6a1b9a", "#ef6c00", "#2e7d32", "#c62828", "#5d4037", "#f9a825", "#00acc1", "#8e24aa", "#7cb342", "#455a64", "#d81b60", "#9e9e9e"]


def code_names():
    f = Path(SETTINGS.ppt_template).parent / "Poramboke_Codes.xlsx"
    if not f.exists():
        return {}
    m = pd.read_excel(f, dtype=str).fillna("")
    return {r.code.strip().zfill(2): r.name.strip() for r in m.itertuples() if r.name.strip()}


def classify(remark, land_type, code, names):
    r = str(remark or "").strip()
    if r and r not in ("-", "nan", "None"):
        for k, v in REMARKS:
            if k in r:
                return v
        return f"Other remark ({r})"
    c = str(code or "").strip()
    c = "" if c in ("-", "nan", "None") else c.zfill(2)
    lt = str(land_type or "Government")
    if lt == "Poramboke":
        return f"Poramboke - {names[c]}" if c in names else (f"Poramboke (code {c})" if c else "Poramboke (no code)")
    return f"Government {lt} land" + (f" ({names[c]})" if c in names else (f" (code {c})" if c else ""))


def run(site, ctx):
    names = code_names()
    g = gpd.read_file(site.subdivisions)
    g["site_acre"] = pd.to_numeric(g.site_acre, errors="coerce")
    gov = g.ownership == "Govt"
    g["govt_cat"] = ""
    g.loc[gov, "govt_cat"] = [classify(r, lt, c, names) for r, lt, c in zip(g[gov].remarks, g[gov].land_type_english, g[gov].poramboke)]
    from .master import write_geojson
    write_geojson(g[[c for c in g.columns if c != "geometry"] + ["geometry"]], site.subdivisions)
    x = g[gov].copy()
    A = float(g.site_acre.sum()); GT = float(x.site_acre.sum())
    cats = x.groupby("govt_cat").site_acre.sum().sort_values(ascending=False)
    colors = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(cats.index)}
    (site.work / "govt_colors.json").write_text(__import__("json").dumps(colors), encoding="utf-8")
    qgis_render(site, ctx, only=["map_govt"])
    rows = []
    for cat, ac in cats.items():
        y = x[x.govt_cat == cat]; sv = sorted(set(y.survey_no.astype(str)), key=survey_sort_key)
        rows.append({"category": cat, "acre": float(ac), "subdivisions": int(len(y)), "color": colors[cat],
                     "villages": ", ".join(sorted(set(y.village))), "surveys": ", ".join(sv[:10]) + (f" +{len(sv) - 10} more" if len(sv) > 10 else "")})
    by_lt = {k: float(v) for k, v in x.groupby("land_type_english").site_acre.sum().sort_values(ascending=False).items()}
    by_v = {k: float(v) for k, v in x.groupby("village").site_acre.sum().sort_values(ascending=False).items()}
    soil = {}
    if "tharam_label" in x.columns:
        soil = {k: float(v) for k, v in x.groupby(x.tharam_label.fillna("Not fetched")).site_acre.sum().sort_values(ascending=False).items()}
    # MIS sheet in the master Excel
    mis = x[["village", "kide", "survey_no", "subdiv_no", "site_acre", "land_type_english", "poramboke", "remarks", "govt_cat"]
            + [c for c in ("tharam_label", "assessment_rs_ha", "sensitive_cat") if c in x.columns]].copy()
    mis["_k"] = mis.survey_no.map(survey_sort_key); mis = mis.sort_values(["govt_cat", "village", "_k"]).drop(columns="_k")
    sheets = pd.read_excel(site.master, sheet_name=None)
    sheets["Govt_Land_Classification"] = mis
    with pd.ExcelWriter(site.master, engine="openpyxl") as w:
        for n, d in sheets.items():
            d.to_excel(w, sheet_name=n, index=False)
    db.save_summary(site.site_id, {"govtland": {"total": A, "govt_acre": GT, "rows": rows, "by_land_type": by_lt, "by_village": by_v, "by_tharam": soil,
                                                "codes_named": bool(names)}})
    return f"government land {GT:.2f} ac ({GT / A * 100:.1f}%): " + ", ".join(f"{r['category']} {r['acre']:.2f}" for r in rows[:6])

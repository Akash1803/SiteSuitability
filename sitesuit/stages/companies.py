"""Stage - company / institution ownership slide: pattas whose owners in the A-register are companies (Pvt Ltd, realtors,
promoters, builders ...) or institutions (trust, diocese, mutt ...). Names stay as the A-register writes them (Tamil);
an English type tag is added. The slide is only built when the site has such owners."""
import re

import geopandas as gpd
import pandas as pd

from .. import db
from .maps import qgis_render
from .master import write_geojson

NAME, TITLE = "companies", "Company ownership slide"
COMPANY = [("Realtors", r"ரியல்டார்|ரியால்டர்|ரியல்டர்|realtor"), ("Promoters", r"பிரமோட்டர்|புரோமோட்டர்|ப்ரோமோட்டர்|promoter"),
           ("Builders", r"பில்டர்|builder|ப்ரோபில்ட்"), ("Developers", r"டெவலப்பர்|developer"), ("Estates / properties", r"எஸ்டேட்|ப்ராப்பர்ட்டி|property|estate"),
           ("Industries", r"இண்டஸ்ட்ரீ|இன்டஸ்ட்ரீ|industr"), ("Company", r"பிரைவேட்|லிமிடெட்|பி\s?லி\b|பிலிட்|நிறுவனம்|கம்பெனி|கார்ப்பரேஷன்|எண்டர்பிரை|limited|\bltd\b|pvt|private|company|corporation|enterprise")]
INSTITUTION = [("Trust", r"டிரஸ்ட்|டிரஸ்டு|அறக்கட்டளை|trust"), ("Diocese / church", r"டயோசிஸ்|பிஷப்|சர்ச்|diocese|church|bishop"),
               ("Temple / mutt", r"தேவஸ்தானம்|ஆதீனம்|மடம்|திருக்கோயில்|devasthanam|mutt"), ("Waqf / mosque", r"வக்ஃப்|வக்பு|பள்ளிவாசல்|waqf"),
               ("Society", r"சொசைட்டி|சங்கம்|society")]
PALETTE = ["#e91e63", "#3f51b5", "#ff9800", "#009688", "#9c27b0", "#cddc39", "#795548", "#00bcd4", "#f44336", "#8bc34a"]


def kind(name):
    t = str(name).lower()
    for k, p in INSTITUTION:
        if re.search(p, t):
            return "Institution", k
    for k, p in COMPANY:
        if re.search(p, t):
            return "Company", k
    return None, None


def run(site, ctx):
    g = gpd.read_file(site.subdivisions)
    g["site_acre"] = pd.to_numeric(g.site_acre, errors="coerce").fillna(0)
    rows = []
    for i, r in g[g.ownership == "Patta"].iterrows():
        for nm in str(r.owner_details or "").split(","):
            nm = " ".join(nm.split())
            c, k = kind(nm)
            if c:
                rows.append({"idx": i, "name": nm, "class": c, "type": k}); break
    hit = pd.DataFrame(rows, columns=["idx", "name", "class", "type"])
    g["company_name"] = ""; g["company_class"] = ""
    for r in hit.itertuples():
        g.at[r.idx, "company_name"] = r.name; g.at[r.idx, "company_class"] = r._3
    by = (g[g.company_name != ""].groupby("company_name").agg(acre=("site_acre", "sum"), subdivisions=("unique_id", "size"), cls=("company_class", "first"),
                                                              villages=("village", lambda s: ", ".join(sorted(set(s)))),
                                                              pattas=("patta_number", "nunique")).sort_values("acre", ascending=False).reset_index())
    by["type"] = by.company_name.map(lambda n: kind(n)[1])
    top = list(by.company_name[:10])
    colors = {n: PALETTE[k] for k, n in enumerate(top)}
    g["company_map"] = [n if n in colors else ("Other company / institution" if n else "") for n in g.company_name]
    write_geojson(g[[c for c in g.columns if c != "geometry"] + ["geometry"]], site.subdivisions)
    data = {"n": int(len(by)), "acre": float(by.acre.sum()), "total": float(g.site_acre.sum()),
            "rows": [{"name": r.company_name, "acre": float(r.acre), "type": r.type, "cls": r.cls, "pattas": int(r.pattas), "villages": r.villages,
                      "color": colors.get(r.company_name, "#9e9e9e")} for r in by.itertuples()],
            "ranges": {"More than 10 acres": int((by.acre > 10).sum()), "More than 5 acres": int(((by.acre > 5) & (by.acre <= 10)).sum()),
                       "5 acres or less": int((by.acre <= 5).sum())}}
    sheets = pd.read_excel(site.master, sheet_name=None)
    sheets["Company_Ownership"] = by.rename(columns={"acre": "site_acre", "cls": "class"})
    with pd.ExcelWriter(site.master, engine="openpyxl") as w:
        for n, d in sheets.items():
            d.to_excel(w, sheet_name=n, index=False)
    if len(by):
        (site.work / "company_colors.json").write_text(__import__("json").dumps({**colors, "Other company / institution": "#9e9e9e"}), encoding="utf-8")
        qgis_render(site, ctx, only=["map_company"])
    db.save_summary(site.site_id, {"companies": data})
    if not len(by):
        return "no company or institution owners in the A-register - the slide is left out"
    return f"{len(by)} companies / institutions hold {by.acre.sum():.2f} ac: " + ", ".join(f"{r.company_name[:30]} {r.acre:.2f}" for r in by.head(3).itertuples())

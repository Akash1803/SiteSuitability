"""Stage - patta holdings slide: pattas inside the site grouped by holding size (area of each patta number inside the site),
the largest pattas with their owners as the A-register records them, and a map of parcels by holding size."""
import geopandas as gpd
import pandas as pd

from .. import db
from .maps import qgis_render
from .master import write_geojson

NAME, TITLE = "owners", "Patta holdings slide"
RANGES = [(0, 2, "2 acres or less"), (2, 5, "More than 2 up to 5 acres"), (5, 10, "More than 5 up to 10 acres"), (10, 1e9, "More than 10 acres")]
COLORS = {"2 acres or less": "#fff59d", "More than 2 up to 5 acres": "#ffb74d", "More than 5 up to 10 acres": "#f4511e", "More than 10 acres": "#b71c1c",
          "Government land": "#90a4ae"}
COMPANY = ("limited", "ltd", "pvt", "private", "லிமிடெட்", "பிரைவேட்", "நிறுவனம்", "கம்பெனி", "company", "realtors", "promoters", "builders")


def rng(a):
    return next(lab for lo, hi, lab in RANGES if lo < a <= hi) if a > 0 else RANGES[0][2]


def run(site, ctx):
    g = gpd.read_file(site.subdivisions)
    g["site_acre"] = pd.to_numeric(g.site_acre, errors="coerce").fillna(0)
    pat = g[(g.ownership == "Patta") & g.patta_number.notna() & (g.patta_number.astype(str).str.strip() != "")].copy()
    pat["pkey"] = pat.unique_id.str[:9] + "_" + pat.patta_number.astype(str).str.strip()
    h = pat.groupby("pkey").agg(village=("village", "first"), patta=("patta_number", "first"), acre=("site_acre", "sum"),
                                owners=("owner_details", lambda s: next((x for x in s if isinstance(x, str) and x.strip() not in ("", "-")), "-")),
                                owner_count=("owner_number", lambda s: int(pd.to_numeric(s, errors="coerce").max() or 0)),
                                subdivisions=("unique_id", "size")).reset_index()
    h["range"] = h.acre.map(rng)
    h["company"] = h.owners.str.lower().map(lambda t: any(k in t for k in COMPANY))
    g["holding_class"] = "Government land"
    cls = dict(zip(h.pkey, h.range))
    m = (g.ownership == "Patta") & g.patta_number.notna()
    g.loc[m, "holding_class"] = (g[m].unique_id.str[:9] + "_" + g[m].patta_number.astype(str).str.strip()).map(cls).fillna(RANGES[0][2])
    write_geojson(g[[c for c in g.columns if c != "geometry"] + ["geometry"]], site.subdivisions)
    qgis_render(site, ctx, only=["map_holding"])
    by = [{"range": lab, "pattas": int((h.range == lab).sum()), "acre": float(h[h.range == lab].acre.sum()), "color": COLORS[lab]} for _, _, lab in RANGES]
    top = h.sort_values("acre", ascending=False).head(6)
    sheets = pd.read_excel(site.master, sheet_name=None)
    out = h.sort_values("acre", ascending=False)[["village", "patta", "acre", "subdivisions", "owner_count", "range", "company", "owners"]]
    sheets["Patta_Holdings"] = out.rename(columns={"acre": "site_acre"})
    with pd.ExcelWriter(site.master, engine="openpyxl") as w:
        for n, d in sheets.items():
            d.to_excel(w, sheet_name=n, index=False)
    data = {"pattas": int(len(h)), "patta_acre": float(h.acre.sum()), "by_range": by, "companies": int(h.company.sum()), "company_acre": float(h[h.company].acre.sum()),
            "top": [{"village": r.village, "patta": str(r.patta), "acre": float(r.acre), "owners": (r.owners[:90] + ("..." if len(r.owners) > 90 else "")),
                     "owner_count": int(r.owner_count)} for r in top.itertuples()],
            "owner_entries": int(pd.to_numeric(h.owner_count, errors="coerce").fillna(0).sum())}
    db.save_summary(site.site_id, {"owners": data})
    return f"{len(h)} pattas: " + ", ".join(f"{b['range']} {b['pattas']}" for b in by) + f"; {data['companies']} company-held pattas"

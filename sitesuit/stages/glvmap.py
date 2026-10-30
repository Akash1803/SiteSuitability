"""Stage - GLV map slide: every parcel coloured by its guideline value band, kept in the unit TNReginet quotes
(per acre for land, per square foot for layout plots); government land 0."""
import geopandas as gpd
import pandas as pd

from .. import db
from .maps import qgis_render
from .master import write_geojson

NAME, TITLE = "glvmap", "GLV map slide"
ACRE_BANDS = [(0, 300000, "Up to Rs 3 lakh / acre"), (300000, 500000, "Rs 3 - 5 lakh / acre"), (500000, 1000000, "Rs 5 - 10 lakh / acre"), (1000000, 1e15, "Above Rs 10 lakh / acre")]
SQFT_BANDS = [(0, 100, "Up to Rs 100 / sq ft"), (100, 300, "Rs 100 - 300 / sq ft"), (300, 1e9, "Above Rs 300 / sq ft")]
COLORS = {"Up to Rs 3 lakh / acre": "#c8e6c9", "Rs 3 - 5 lakh / acre": "#81c784", "Rs 5 - 10 lakh / acre": "#388e3c", "Above Rs 10 lakh / acre": "#1b5e20",
          "Up to Rs 100 / sq ft": "#ffcdd2", "Rs 100 - 300 / sq ft": "#e57373", "Above Rs 300 / sq ft": "#b71c1c", "Govt / value 0": "#90a4ae", "No GLV data": "#eeeeee"}


def band(rate, unit):
    if pd.isna(rate) or unit not in ("Acre", "Square Feet"):
        return "No GLV data"
    if rate <= 0:
        return "Govt / value 0"
    for lo, hi, lab in (ACRE_BANDS if unit == "Acre" else SQFT_BANDS):
        if lo < rate <= hi:
            return lab
    return "No GLV data"


def run(site, ctx):
    g = gpd.read_file(site.subdivisions)
    g["glv_rate"] = pd.to_numeric(g.glv_rate, errors="coerce"); g["site_acre"] = pd.to_numeric(g.site_acre, errors="coerce")
    g["glv_band"] = [band(r, u) for r, u in zip(g.glv_rate, g.glv_unit)]
    write_geojson(g[[c for c in g.columns if c != "geometry"] + ["geometry"]], site.subdivisions)
    qgis_render(site, ctx, only=["map_glv"])
    order = [b[2] for b in ACRE_BANDS] + [b[2] for b in SQFT_BANDS] + ["Govt / value 0", "No GLV data"]
    agg = g.groupby("glv_band").agg(acre=("site_acre", "sum"), n=("unique_id", "size"), lo=("glv_rate", "min"), hi=("glv_rate", "max"))
    num = lambda v: None if pd.isna(v) else float(v)      # 'No GLV data' has no rate (NaN is not valid JSON)
    rows = [{"band": b, "acre": float(agg.loc[b, "acre"]), "n": int(agg.loc[b, "n"]), "color": COLORS[b],
             "lo": num(agg.loc[b, "lo"]), "hi": num(agg.loc[b, "hi"])} for b in order if b in agg.index]
    ac = g[g.glv_unit == "Acre"]; sq = g[g.glv_unit == "Square Feet"]
    data = {"rows": rows, "acre_range": [float(ac[ac.glv_rate > 0].glv_rate.min() or 0), float(ac.glv_rate.max() or 0)] if len(ac[ac.glv_rate > 0]) else None,
            "sqft_range": [float(sq.glv_rate.min()), float(sq.glv_rate.max())] if len(sq) else None, "total": float(g.site_acre.sum())}
    db.save_summary(site.site_id, {"glvmap": data})
    return "; ".join(f"{r['band']} {r['acre']:.2f} ac" for r in rows)

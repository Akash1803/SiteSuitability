"""Stage - sensitive land inside the site: water bodies, channels, temples, burial grounds, village site, forest, NH land and wells
as written in the A-register remarks, plus government poramboke with no remark. Map + table for the PPT."""
import geopandas as gpd
import pandas as pd

from .. import db
from ..util import survey_sort_key
from .maps import qgis_render

NAME, TITLE = "sensitive", "Sensitive land slide"
ORDER = ["Water body", "Channel", "Temple/Church/Mosque", "Burial", "Village site", "Forest", "NH land", "Well", "Other government poramboke"]


def category(flag, land_type):
    f = flag.strip() if isinstance(flag, str) else ""
    if f and f != "nan":
        return f
    return "Other government poramboke" if str(land_type) == "Poramboke" else ""


def run(site, ctx):
    g = gpd.read_file(site.subdivisions)
    g["sensitive_cat"] = [category(f, lt) for f, lt in zip(g.sensitive_flag, g.land_type_english)]
    from .master import write_geojson
    write_geojson(g[[c for c in g.columns if c != "geometry"] + ["geometry"]], site.subdivisions)
    qgis_render(site, ctx, only=["map_sensitive"])
    s = g[g.sensitive_cat != ""].copy()
    A = float(pd.to_numeric(g.site_acre, errors="coerce").sum())
    rows = []
    for cat in ORDER + sorted(set(s.sensitive_cat) - set(ORDER)):
        x = s[s.sensitive_cat == cat]
        if x.empty:
            continue
        sv = sorted(set(x.survey_no.astype(str)), key=survey_sort_key)
        rows.append({"category": cat, "acre": float(pd.to_numeric(x.site_acre, errors="coerce").sum()), "subdivisions": int(len(x)),
                     "surveys": ", ".join(sv[:12]) + (f" +{len(sv) - 12} more" if len(sv) > 12 else "")})
    tot = sum(r["acre"] for r in rows)
    db.save_summary(site.site_id, {"sensitive": {"total": A, "rows": rows, "sensitive_acre": tot}})
    return f"{tot:.2f} ac flagged ({tot / A * 100:.1f}% of the site): " + ", ".join(f"{r['category']} {r['acre']:.2f}" for r in rows)

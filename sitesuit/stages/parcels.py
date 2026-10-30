"""Stage 1 - boundary -> revenue villages -> Puvi survey parcels (edge parcels clipped) + Puvi FMB plots + CLIP input."""
import shutil

import geopandas as gpd
import pandas as pd
from shapely import force_2d, wkb
from shapely.ops import unary_union

from .. import db, loaders
from ..util import ACRE_M2, split_vcode, survey_sort_key, utm_epsg

NAME, TITLE = "parcels", "Survey parcels from Puvi"
MIN_INSIDE_PCT, MIN_INSIDE_M2, FULL_PCT = 1.0, 50.0, 99.5


def polys(geoms):
    """valid polygon geometry (make_valid can return a collection with lines: keep the polygon parts)"""
    import shapely
    from shapely.geometry import MultiPolygon, Polygon
    out = []
    for g in shapely.make_valid(geoms.values):
        if g is None or g.is_empty:
            out.append(None); continue
        if isinstance(g, (Polygon, MultiPolygon)):
            out.append(g); continue
        ps = [p for p in getattr(g, "geoms", []) if isinstance(p, (Polygon, MultiPolygon))]
        parts = [q for p in ps for q in (p.geoms if isinstance(p, MultiPolygon) else [p])]
        out.append(MultiPolygon(parts) if len(parts) > 1 else (parts[0] if parts else None))
    return gpd.GeoSeries(out, index=geoms.index, crs=geoms.crs)


def read_boundary(path):
    g = gpd.read_file(path)
    g = g.set_crs(4326) if g.crs is None else g.to_crs(4326)
    geom = force_2d(unary_union([force_2d(x) if x.is_valid else force_2d(x).buffer(0) for x in g.geometry if x is not None]))
    if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("boundary file has no polygon")
    return geom


def run(site, ctx):
    log = ctx.log
    src = ctx.options["boundary_file"]
    site.make_dirs()
    geom = read_boundary(src)
    for f in ([src] + [str(src)[:-4] + e for e in (".shx", ".dbf", ".prj", ".cpg")] if str(src).lower().endswith(".shp") else [src]):
        try:
            shutil.copy(f, site.root / "01_Source")
        except (FileNotFoundError, shutil.SameFileError):
            pass
    gpd.GeoDataFrame({"site": [site.name]}, geometry=[geom], crs=4326).to_file(site.boundary, driver="GeoJSON")
    site.site_id = db.upsert_site(site.name, site.root, geom.wkt)
    U = utm_epsg(geom.centroid.x)
    bnd_m = gpd.GeoSeries([geom], crs=4326).to_crs(U).make_valid().iloc[0]
    log(f"boundary {bnd_m.area / ACRE_M2:.2f} acres (map), UTM EPSG:{U}")

    loaders.load_revenue_villages(log)
    vills = loaders.villages_touching(geom.wkt)
    if not vills:
        raise RuntimeError("the boundary touches no Tamil Nadu revenue village")
    names = {v[0]: v for v in vills}
    log(f"{len(vills)} revenue villages touch the boundary: " + ", ".join(f"{v[3]} ({v[0]})" for v in vills))
    missing = loaders.ensure_puvi([v[0] for v in vills], log)

    with db.connect() as c:
        rows = c.execute("""SELECT vcode, survey_no, ST_AsBinary(ST_Union(ST_MakeValid(geom))) FROM cadastral.puvi_survey
                            WHERE vcode = ANY(%s) AND ST_Intersects(geom, ST_GeomFromText(%s, 4326)) GROUP BY vcode, survey_no""",
                         ([v[0] for v in vills], geom.wkt)).fetchall()
        frows = c.execute("""SELECT vcode, kide, survey_no, subdiv_no, ST_AsBinary(geom) FROM cadastral.puvi_fmb
                             WHERE vcode = ANY(%s) AND ST_Intersects(geom, ST_GeomFromText(%s, 4326))""", ([v[0] for v in vills], geom.wkt)).fetchall()
    sv = gpd.GeoDataFrame([{"village_code": r[0], "survey_no": r[1]} for r in rows], geometry=[wkb.loads(bytes(r[2])) for r in rows], crs=4326).to_crs(U)
    sv["puvi_acre"] = (sv.area / ACRE_M2).round(4)
    sv["geometry"] = polys(sv.geometry)       # Puvi shapes are sometimes self-intersecting: repair before clipping
    sv = sv[sv.geometry.notna()].copy()
    sv["geometry"] = sv.geometry.intersection(bnd_m)
    sv["inside_m2"] = sv.area
    sv["inside_acre"] = (sv.inside_m2 / ACRE_M2).round(4)
    sv["inside_pct"] = (sv.inside_acre / sv.puvi_acre * 100).round(1)
    dropped = sv[(sv.inside_pct < MIN_INSIDE_PCT) | (sv.inside_m2 < MIN_INSIDE_M2)]
    sv = sv[(sv.inside_pct >= MIN_INSIDE_PCT) & (sv.inside_m2 >= MIN_INSIDE_M2)].copy()
    sv["split"] = sv.inside_pct < FULL_PCT
    sv["area_basis"] = sv.split.map({False: "A-register (full survey inside)", True: "Geometry inside boundary (split survey)"})
    sv["kide"] = sv.survey_no; sv["subdiv_no"] = "-"; sv["area_acre"] = sv.inside_acre
    sv["district"] = sv.village_code.map(lambda v: names[v][1]); sv["taluk"] = sv.village_code.map(lambda v: names[v][2])
    sv["village"] = sv.village_code.map(lambda v: names[v][3])
    sv["_k"] = sv.survey_no.map(survey_sort_key)
    sv = sv.sort_values(["village", "_k"]).drop(columns=["_k", "inside_m2"])
    cols = ["kide", "survey_no", "subdiv_no", "area_acre", "area_basis", "split", "puvi_acre", "inside_acre", "inside_pct", "village", "taluk", "district", "village_code", "geometry"]
    sv[cols].to_crs(4326).to_file(site.parcels, driver="GeoJSON")
    log(f"{len(sv)} surveys ({int(sv.split.sum())} split edge surveys); {len(dropped)} slivers under {MIN_INSIDE_PCT}% / {MIN_INSIDE_M2:.0f} m2 left out")

    want = set(zip(sv.village_code, sv.survey_no))
    f = gpd.GeoDataFrame([{"village_code": r[0], "kide": r[1], "survey_no": r[2], "subdiv_no": r[3] or ""} for r in frows],
                         geometry=[wkb.loads(bytes(r[4])) for r in frows], crs=4326)
    if len(f):
        f = f[[k in want for k in zip(f.village_code, f.survey_no)]].to_crs(U)
        f["plot_acre_full"] = (f.area / ACRE_M2).round(4)
        f["geometry"] = polys(f.geometry)
        f = f[f.geometry.notna()].copy()
        f["geometry"] = f.geometry.intersection(bnd_m)
        f = f[~f.geometry.is_empty].copy()
        f["plot_acre_inside"] = (f.area / ACRE_M2).round(4)
        f["village"] = f.village_code.map(lambda v: names[v][3])
        f = f[["kide", "survey_no", "subdiv_no", "plot_acre_full", "plot_acre_inside", "village", "village_code", "geometry"]].to_crs(4326)
    else:
        f = gpd.GeoDataFrame(columns=["kide", "survey_no", "subdiv_no", "plot_acre_full", "plot_acre_inside", "village", "village_code", "geometry"], geometry="geometry", crs=4326)
    f.to_file(site.puvi_fmb, driver="GeoJSON")
    no_fmb = sorted(want - set(zip(f.village_code, f.survey_no)))
    log(f"{len(f)} Puvi FMB plots; surveys without Puvi FMB: {len(no_fmb)}")

    ci = sv[["survey_no", "village_code"]].drop_duplicates().copy()
    ci[["district_id", "taluk_id", "village_id"]] = pd.DataFrame([split_vcode(v) for v in ci.village_code], index=ci.index)
    ci[["survey_no", "district_id", "taluk_id", "village_id"]].to_excel(site.clip_input, index=False)
    vt = sv.groupby("village").agg(surveys=("survey_no", "size"), inside_acre=("inside_acre", "sum")).round(2)
    db.save_summary(site.site_id, {"utm": U, "boundary_acre": round(bnd_m.area / ACRE_M2, 2), "surveys": len(sv), "split_surveys": int(sv.split.sum()),
                                   "villages": [{"vcode": v[0], "district": v[1], "taluk": v[2], "village": v[3], "lgd": v[4]} for v in vills if v[0] in set(sv.village_code)],
                                   "puvi_missing": missing, "surveys_without_fmb": [f"{a}_{b}" for a, b in no_fmb]})
    for k in ("boundary", "parcels", "puvi_fmb", "clip_input"):
        db.register_document(site.site_id, k, getattr(site, k))
    return f"{len(sv)} surveys in {vt.shape[0]} villages, {int(sv.split.sum())} split; " + ", ".join(f"{v} {int(r.surveys)}" for v, r in vt.iterrows())

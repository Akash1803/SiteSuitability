"""Stage - edge review: for every survey the boundary cuts, the user decides Full (whole survey, A-register area) / Part (only
what is inside the line) / Exclude; inside a Part survey each cut subdivision can again be Full / Part / Exclude, with an optional
typed area. Defaults: survey inside >= full_pct -> Full, else Part; subdivisions -> Part (area inside the line), which is the
rule used so far. The stage waits once for the review in the app, then applies the decisions to the master Excel and layer."""
import geopandas as gpd
import numpy as np
import pandas as pd

from .. import db
from ..util import ACRE_M2, SQFT_PER_M2, survey_sort_key

NAME, TITLE = "edges", "Edge review (cut surveys)"
DEC = ("Full", "Part", "Exclude")


class NeedsReview(Exception):
    pass


def review_state(sid):
    with db.connect() as c:
        r = c.execute("SELECT confirmed, full_pct FROM site.edge_review WHERE site_id = %s", (sid,)).fetchone()
    return (bool(r[0]), float(r[1])) if r else (False, 98.0)


def decisions(sid):
    with db.connect() as c:
        return {(lv, k): (d, t) for lv, k, d, t in c.execute("SELECT level, key, decision, typed_acre FROM site.edge_decision WHERE site_id = %s", (sid,))}


def candidates(site):
    """edge surveys and the subdivisions of each, with inside % and areas (from the parcels layer and the master Excel)"""
    sv = gpd.read_file(site.parcels); sv["survey_no"] = sv.survey_no.astype(str)
    sv = sv[sv.split.astype(str).str.lower() == "true"].copy()
    sv["key"] = sv.village_code + "_" + sv.survey_no
    sm = pd.read_excel(site.master, sheet_name="Subdivision_Master", dtype={"survey_no": str, "subdiv_no": str})
    sm["skey"] = sm.unique_id.str[:9] + "_" + sm.survey_no
    sub = sm[sm.skey.isin(set(sv.key))][["unique_id", "skey", "kide", "areg_acre", "parcel_acre", "inside_pct", "geometry_quality"]].copy()
    sv["_k"] = sv.survey_no.map(survey_sort_key)
    return sv.sort_values(["village", "_k"]).drop(columns="_k"), sub


def defaults(sv, sub, full_pct):
    d = {("survey", r.key): ("Full" if r.inside_pct >= full_pct else "Part") for r in sv.itertuples()}
    d.update({("subdiv", r.unique_id): ("Part" if r.parcel_acre > 0 else "Exclude") for r in sub.itertuples()})
    return d


def save(sid, rows, confirmed=None, full_pct=None):
    """rows: {(level, key): (decision, typed_acre, default)}"""
    with db.connect() as c:
        with c.cursor() as cur:
            cur.executemany("""INSERT INTO site.edge_decision (site_id, level, key, decision, typed_acre, default_decision) VALUES (%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (site_id, level, key) DO UPDATE SET decision = EXCLUDED.decision, typed_acre = EXCLUDED.typed_acre,
                               default_decision = COALESCE(EXCLUDED.default_decision, site.edge_decision.default_decision), updated_at = now()""",
                            [(sid, lv, k, d, t, df) for (lv, k), (d, t, df) in rows.items()])
        if confirmed is not None or full_pct is not None:
            c.execute("""INSERT INTO site.edge_review (site_id, confirmed, full_pct) VALUES (%s, COALESCE(%s, false), COALESCE(%s, 98))
                         ON CONFLICT (site_id) DO UPDATE SET confirmed = COALESCE(%s, site.edge_review.confirmed),
                         full_pct = COALESCE(%s, site.edge_review.full_pct), updated_at = now()""", (sid, confirmed, full_pct, confirmed, full_pct))


def prepare(site, ctx):
    """make sure every edge survey / subdivision has a decision (defaults for new ones) and its thumbnail"""
    sv, sub = candidates(site)
    confirmed, full_pct = review_state(site.site_id)
    have = decisions(site.site_id)
    new = {k: (v, None, v) for k, v in defaults(sv, sub, full_pct).items() if k not in have}
    if new:
        save(site.site_id, new, confirmed=False if not have else None, full_pct=full_pct)
        if have:      # new edge rows appeared (boundary or records changed): ask again
            save(site.site_id, {}, confirmed=False)
    thumbs = site.work / "edges"
    missing = [r.key for r in sv.itertuples() if not (thumbs / f"{r.key}.png").exists()]
    if missing:
        from .maps import qgis_render
        bbox = {r.key: list(r.geometry.bounds) for r in gpd.read_file(site.parcels).assign(key=lambda d: d.village_code + "_" + d.survey_no.astype(str)).itertuples()
                if r.key in set(missing)}
        full = gpd.read_file(site.work / "subdiv_full.geojson")
        for k, b in list(bbox.items()):           # frame the whole (unclipped) survey, not only its inside part
            parts = full[full.unique_id.str.startswith(k + "/")]
            if len(parts):
                x0, y0, x1, y1 = parts.total_bounds; bbox[k] = [min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)]
        (site.work / "edge_boxes.json").write_text(__import__("json").dumps(bbox), encoding="utf-8")
        thumbs.mkdir(exist_ok=True)
        qgis_render(site, ctx, only=["edges"])
    return sv, sub


def apply(site, ctx, sv, sub):
    dec = decisions(site.site_id)
    sheets = pd.read_excel(site.master, sheet_name=None)
    sm = sheets["Subdivision_Master"]; sm["survey_no"] = sm.survey_no.astype(str)
    sm["in_site"] = sm.in_site.astype(str).str.lower() == "true"
    sm["skey"] = sm.unique_id.str[:9] + "_" + sm.survey_no
    full = gpd.read_file(site.work / "subdiv_full.geojson").set_index("unique_id").geometry
    g = gpd.read_file(site.subdivisions)
    clipped = g.set_index("unique_id").geometry
    U = db.get_summary(site.site_id).get("utm", 32644)
    fullU = gpd.GeoSeries(full, crs=4326).to_crs(U)
    counts = {"Full": 0, "Part": 0, "Exclude": 0, "typed": 0}
    geoms = {}
    for i in sm.index[sm.skey.isin(set(sv.key))]:
        u, sk = sm.at[i, "unique_id"], sm.at[i, "skey"]
        sd = dec.get(("survey", sk), ("Part", None))[0]
        d, t = dec.get(("subdiv", u), ("Part", None)) if sd == "Part" else (sd, None)
        if d == "Exclude" or (d == "Part" and not t and (sm.at[i, "parcel_acre"] or 0) <= 0):
            sm.at[i, "in_site"] = False; sm.at[i, "site_acre"] = 0.0; sm.at[i, "area_basis"] = "Excluded in the edge review"; counts["Exclude"] += 1
        elif d == "Full":
            sm.at[i, "in_site"] = True; sm.at[i, "site_acre"] = sm.at[i, "areg_acre"]
            sm.at[i, "area_basis"] = "A-register (kept whole in the edge review)"; counts["Full"] += 1
            if u in fullU.index:
                geoms[u] = full[u]
        else:
            sm.at[i, "in_site"] = True
            if t:
                sm.at[i, "site_acre"] = round(float(t), 4); sm.at[i, "area_basis"] = "Area typed in the edge review"; counts["typed"] += 1
            else:
                sm.at[i, "site_acre"] = sm.at[i, "parcel_acre"]; sm.at[i, "area_basis"] = "Geometry inside boundary (split survey)"
            counts["Part"] += 1
        sm.at[i, "area_acre"] = sm.at[i, "site_acre"]
    sq = sm.site_acre * ACRE_M2 * SQFT_PER_M2
    sm["glv_sqft_area"] = np.where(sm.glv_unit == "Square Feet", sq.round(0), np.nan)
    sm["glv_value_lakh"] = np.where(sm.glv_unit == "Square Feet", sm.glv_rate.fillna(0) * sq / 1e5,
                                    np.where(sm.glv_unit == "Acre", sm.glv_rate.fillna(0) * sm.site_acre / 1e5, 0.0)).round(2)
    sm = sm.drop(columns="skey")
    # layer: rows in the site, whole shapes where kept whole
    from .master import LEAD, write_geojson, write_master
    ins = sm[sm.in_site].copy()
    geo = [geoms.get(u, clipped.get(u) if u in clipped.index else (full.get(u) if u in full.index else None)) for u in ins.unique_id]
    out = gpd.GeoDataFrame(ins[[c for c in LEAD if c in ins.columns]], geometry=geo, crs=4326)
    out = out[out.geometry.notna()]
    write_geojson(out, site.subdivisions)
    db.save_parcels(site.site_id, out)
    ov = sheets.get("Parcel_Overlaps", pd.DataFrame(columns=["unique_id_left", "unique_id_right", "m2"]))
    write_master(site, sm, ov)
    data = {"site_acre": float(ins.site_acre.sum()), "patta_acre": float(ins[ins.ownership == "Patta"].site_acre.sum()),
            "govt_acre": float(ins[ins.ownership == "Govt"].site_acre.sum()), "glv_crore": float(ins.glv_value_lakh.sum() / 100), "subdivisions": int(len(ins))}
    m = db.get_summary(site.site_id).get("master", {}); m.update(data)
    db.save_summary(site.site_id, {"master": m, "edges": counts})
    return counts, data


def run(site, ctx):
    sv, sub = prepare(site, ctx)
    if sv.empty:
        return "no survey is cut by the boundary - nothing to review"
    confirmed, _ = review_state(site.site_id)
    if not confirmed:
        raise NeedsReview(f"{len(sv)} surveys are cut by the boundary - open the edge review, check Full / Part / Exclude and press Continue")
    counts, data = apply(site, ctx, sv, sub)
    return (f"{len(sv)} cut surveys reviewed: {counts['Full']} subdivisions kept whole, {counts['Part']} inside part only"
            + (f" ({counts['typed']} typed)" if counts["typed"] else "") + f", {counts['Exclude']} excluded; site {data['site_acre']:.2f} ac")

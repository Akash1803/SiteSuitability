"""Stage 5 - master Excel + subdivision parcel layer.
A. every A-register subdivision gets CLIP status, GLV (exactly as TNReginet quotes) and its Puvi FMB match;
B. every record gets a polygon (exact FMB plot, else an approximate strip cut by A-register extent inside its parent plot / survey);
C. records are clipped to the boundary: full surveys keep the A-register area, split edge surveys the area inside the boundary."""
import io
import contextlib

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union
from shapely.validation import make_valid

from .. import db
from ..geometry import clean, fix_multipart, split_components, strip_split
from ..util import ACRE_M2, GOVT, SQFT_PER_M2, child_of, glv_pick, survey_sort_key, utm_epsg, vcode

NAME, TITLE = "master", "Master Excel + subdivision parcels"


def _use_glv(site, ctx):
    return bool(site.glv_output.exists() and ctx.is_on("glv"))


def stale(site, ctx):
    """re-build when GLV was ticked / unticked since the last build"""
    used = db.get_summary(site.site_id).get("master_used_glv")
    return used is not None and used != _use_glv(site, ctx)


# ---------------- A. records ----------------
def build_records(site, log, use_glv=True):
    a = pd.read_excel(site.areg_excel, sheet_name="AReg_Records", dtype=str)
    a["vcode"] = [vcode(d, t, v) for d, t, v in zip(a.district_id, a.taluk_id, a.village_id)]
    a["uid"] = a["Unique ID 2"]; a["sensitive_flag"] = a.sensitive_flag.fillna("")
    a["areg_acre"] = pd.to_numeric(a.areg_acre, errors="coerce"); a["split"] = a.split.astype(str).str.lower().eq("true")
    a = a.drop_duplicates("uid")
    c = pd.read_excel(site.clip_output, dtype=str)
    c["uid"] = [vcode(d, t, v) + "_" + s + "/" + (sd if isinstance(sd, str) else "-") for d, t, v, s, sd in zip(c.district_id, c.taluk_id, c.village_id, c.survey_no, c.sub_division)]
    a = a.merge(c.drop_duplicates("uid")[["uid", "response_status"]].rename(columns={"response_status": "clip_status"}), on="uid", how="left")
    a["clip_status"] = a.clip_status.fillna("not in CLIP output (A-register /1 used)")
    # ---- GLV ----
    gcols = ["district_id", "taluk_id", "village_id", "survey_no", "Subdivision Number", "Guideline_Value_British", "Land_Classification", "Effective_Start_Date", "Status"]
    g = pd.read_excel(site.glv_output, sheet_name="GLV_Survey_Wise", dtype=str) if use_glv else pd.DataFrame(columns=gcols)
    if not use_glv:
        log("GLV left out of this run - guideline value columns stay empty")
    g["vcode"] = [vcode(d, t, v) for d, t, v in zip(g.district_id, g.taluk_id, g.village_id)]
    g = g[g.Status == "Success"].copy()
    g["unit"] = g.Guideline_Value_British.str.extract(r"/\s*(.*)$")[0].str.strip().fillna("")
    g["num"] = pd.to_numeric(g.Guideline_Value_British.str.extract(r"^\s*([\d.]+)")[0], errors="coerce")
    g.loc[g.num == 0, "unit"] = "Acre"
    g["uid"] = g.vcode + "_" + g["Subdivision Number"].str.strip()
    gx = g.drop_duplicates("uid").set_index("uid")
    by_s = {k: list(zip(d.num, d.unit, d.Land_Classification, d.Effective_Start_Date)) for k, d in g.groupby(["vcode", "survey_no"])}
    ind = {}   # optional indicative Rs/acre per village typed into the GLV village map (villages TNReginet lists only as a blanket rate)
    if site.glv_map.exists():
        mp = pd.read_excel(site.glv_map, dtype=str)
        if "indicative_rate_acre" in mp.columns:
            ind = {r.vcode: float(r.indicative_rate_acre) for r in mp.itertuples() if str(r.indicative_rate_acre).replace(".", "", 1).isdigit()}
    out = []
    for r in a.itertuples():
        govt = (r.government_priority == GOVT) or str(r.land_type_english) == "Poramboke"
        if r.uid in gx.index:
            e = gx.loc[r.uid]
            out.append(("Exact subdivision entry" if e.num > 0 else "Exact entry, value 0 (TNReginet lists 0 for govt/poramboke land)", e.num, e.unit, e.Land_Classification, e.Effective_Start_Date)); continue
        p = glv_pick(by_s.get((r.vcode, r.survey_no), []), (r.areg_acre or 0) * ACRE_M2, govt)
        if p:
            out.append(p); continue
        cls = "Dry" if str(r.land_type_english) == "Dry" else ("Wet" if str(r.land_type_english) == "Wet" else "")
        vv = g[(g.vcode == r.vcode) & (g.unit == "Acre") & (g.num > 0) & g.Land_Classification.str.contains(cls, regex=False)]
        if len(vv):
            e = vv.sort_values("num").iloc[0]
            out.append((f"Indicative - no entry for survey {r.survey_no}: lowest {e.Land_Classification} rate of the village; confirm with SRO", e.num, "Acre", e.Land_Classification, e.Effective_Start_Date))
        elif ind.get(r.vcode):
            out.append((f"Indicative village rate Rs {ind[r.vcode]:,.0f}/acre from the GLV village map (no survey-wise entry); confirm with SRO", ind[r.vcode], "Acre", "Indicative", ""))
        else:
            out.append(("No GLV data", np.nan, "", "", ""))
    a[["glv_match", "glv_rate", "glv_unit", "glv_land_classification", "glv_effective_date"]] = pd.DataFrame(out, index=a.index)
    a["glv_value"] = [("" if (u == "" or pd.isna(x)) else f"{int(x)}/ {u}") for x, u in zip(a.glv_rate, a.glv_unit)]
    # ---- Puvi FMB match ----
    f = gpd.read_file(site.puvi_fmb)
    bad = f[~f.geom_type.isin(["Polygon", "MultiPolygon"])]
    if len(bad):
        log(f"FMB plots that are not polygons (ignored): {bad.kide.tolist()[:20]}")
    f = f[f.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    f["survey_no"] = f.survey_no.astype(str); f["kide"] = f.kide.astype(str); f["area_acre"] = f.plot_acre_full
    f["sub_norm"] = f.kide.str.split("/").map(lambda p: "".join(p[1:]) if len(p) > 1 and "".join(p[1:]) not in ("", "-") else "-")
    f["uid"] = f.village_code + "_" + f.survey_no + "/" + f.sub_norm
    if f.uid.duplicated().any():
        f = f.dissolve("uid", aggfunc={"kide": "first", "survey_no": "first", "subdiv_no": "first", "plot_acre_full": "sum", "plot_acre_inside": "sum",
                                       "village": "first", "village_code": "first", "area_acre": "sum", "sub_norm": "first"}).reset_index()
    multi = f.groupby(["village_code", "survey_no"]).uid.transform("size") > 1
    sl = f[multi & (f.sub_norm == "-")]
    if len(sl):
        log(f"whole-survey sliver plots dropped (other plots of the survey exist): {sl.uid.tolist()}")
        f = f[~(multi & (f.sub_norm == "-"))].copy()
    fk = dict(zip(f.uid, f.kide)); by = f.groupby(["village_code", "survey_no"]).sub_norm.apply(list).to_dict()

    def match(r):
        if r.uid in fk:
            return "Exact", r.uid
        subs = by.get((r.vcode, r.survey_no), [])
        if r.sub_division != "-":
            cands = [s for s in subs if child_of(r.sub_division, s)]
            if cands:
                return "Parent plot (subdivision split after the FMB)", f"{r.vcode}_{r.survey_no}/{max(cands, key=len)}"
            if "-" in subs:
                return "Whole-survey plot (FMB not subdivided)", f"{r.vcode}_{r.survey_no}/-"
        elif "-" in subs:
            return "Exact", f"{r.vcode}_{r.survey_no}/-"
        return ("No Puvi FMB for this survey" if not subs else "No matching FMB plot (FMB subdivisions named differently)"), ""
    m = a.apply(match, axis=1, result_type="expand"); a["fmb_match"], a["fmb_uid"] = m[0], m[1]
    cnt = a[a.fmb_uid != ""].groupby("fmb_uid").uid.size()
    a.loc[a.fmb_match.str.startswith("Whole") & (a.fmb_uid.map(cnt) == 1), "fmb_match"] = "Exact"
    a["fmb_kide"] = a.fmb_uid.map(fk).fillna(""); a["fmb_plot_acre"] = a.fmb_uid.map(dict(zip(f.uid, f.area_acre)))
    rec = a.copy(); rec["geometry"] = rec.fmb_uid.map(dict(zip(f.uid, f.geometry)))
    vec = gpd.read_file(site.parcels).to_crs(4326); vec["survey_no"] = vec.survey_no.astype(str)
    full = {}
    with db.connect() as c:   # full (unclipped) Puvi survey outlines for the split step
        for vc, sn, wkt in c.execute("SELECT vcode, survey_no, ST_AsText(ST_Union(geom)) FROM cadastral.puvi_survey WHERE vcode = ANY(%s) GROUP BY vcode, survey_no",
                                     (sorted(set(vec.village_code)),)):
            full[(vc, sn)] = wkt
    from shapely import wkt as _w
    one = rec.groupby(["vcode", "survey_no"]).uid.transform("size") == 1
    for i in rec.index[one]:
        k = (rec.at[i, "vcode"], rec.at[i, "survey_no"])
        if k in full:
            rec.at[i, "geometry"] = _w.loads(full[k]); rec.at[i, "fmb_match"] = "Exact"
    rec["parcel_status"] = rec.fmb_match.map(lambda m: "Own FMB plot" if m == "Exact" else ("Parent polygon - subdivision to be split" if m.startswith(("Parent", "Whole")) else "No polygon - FMB sheet to be georeferenced"))
    rec = rec.rename(columns={"areg_status": "areg_status", "Unique ID 2": "unique_id", "Unique ID 1": "survey_uid"}).drop(columns=["uid", "fmb_uid"])
    vg = gpd.GeoDataFrame({"village_code": list(k[0] for k in full), "survey_no": list(k[1] for k in full)}, geometry=[_w.loads(v) for v in full.values()], crs=4326)
    return gpd.GeoDataFrame(rec, geometry="geometry", crs=4326), f, vg


# ---------------- B. split ----------------
def split_records(rec, fmb, vec, U, log):
    r = rec.to_crs(U); fmb = fmb.to_crs(U); vec = vec.to_crs(U)
    r["geometry"] = r.geometry.apply(lambda g: g if g is None or g.is_valid else make_valid(g))
    fmb["geometry"] = fmb.geometry.apply(lambda g: g if g.is_valid else make_valid(g))
    fmb["vc_kide"] = fmb.village_code + "_" + fmb.kide
    r["geometry_quality"] = ""
    r.loc[r.parcel_status == "Own FMB plot", "geometry_quality"] = "Exact (Puvi FMB plot / survey outline)"
    for (vc, kide), grp in r[r.parcel_status.str.startswith("Parent")].groupby(["vcode", "fmb_kide"]):
        plot = fmb[fmb.vc_kide == vc + "_" + kide]
        if plot.empty:
            continue
        for idx, g in zip(grp.index, strip_split(plot.geometry.iloc[0], grp.areg_acre.values)):
            r.at[idx, "geometry"] = g; r.at[idx, "geometry_quality"] = "APPROXIMATE - parent plot split by A-reg extent (strip cut)"
        fix_multipart(r, list(grp.index))
    exact_all = r[r.geometry_quality.str.startswith("Exact")][["vcode", "survey_no", "geometry"]].copy()
    for (vc, sn), grp in r[r.parcel_status.str.startswith("No polygon")].groupby(["vcode", "survey_no"]):
        fp = fmb[(fmb.village_code == vc) & (fmb.survey_no == sn)]
        vv = vec[(vec.village_code == vc) & (vec.survey_no == sn)]
        vreg = unary_union(vv.geometry) if len(vv) else (unary_union(fp.geometry) if len(fp) else None)
        if vreg is None:
            log(f"no geometry at all for {vc} survey {sn}"); continue
        freg = unary_union(fp.geometry) if len(fp) else None
        region = freg if (freg is not None and freg.area >= 0.9 * vreg.area) else vreg
        nb = exact_all[~((exact_all.vcode == vc) & (exact_all.survey_no == sn))]
        nb = nb[nb.intersects(region)]
        if len(nb):
            region = clean(region.difference(unary_union(nb.geometry))) or region
        allrec = r[(r.vcode == vc) & (r.survey_no == sn)]
        exact = allrec[allrec.geometry_quality.str.startswith("Exact")]
        others = allrec[~allrec.geometry_quality.str.startswith("Exact")]
        remaining = clean(region.difference(unary_union(exact.geometry))) if len(exact) else region
        if remaining is None or remaining.area < 0.03 * region.area:
            share = others.areg_acre.sum() / max(allrec.areg_acre.sum(), 1e-9)
            if share > 0.2 or len(exact) == 0:
                for idx, g in zip(allrec.index, split_components(region, allrec.areg_acre.values)):
                    r.at[idx, "geometry"] = g; r.at[idx, "geometry_quality"] = "APPROXIMATE - FMB outdated for this survey; whole survey split among all records by A-reg extent (strip cut)"
                fix_multipart(r, list(allrec.index))
            else:
                big = exact.assign(_a=exact.geometry.area).sort_values("_a").index[-1]
                gi = [big] + list(others.index)
                for idx, g in zip(gi, strip_split(r.at[big, "geometry"], [r.at[i, "areg_acre"] for i in gi])):
                    r.at[idx, "geometry"] = g; r.at[idx, "geometry_quality"] = "APPROXIMATE - unlisted record carved from the largest FMB plot of the survey by A-reg extent (strip cut)"
                fix_multipart(r, gi)
            continue
        for idx, g in zip(others.index, split_components(remaining, others.areg_acre.values)):
            r.at[idx, "geometry"] = g; r.at[idx, "geometry_quality"] = "APPROXIMATE - survey re-subdivided after FMB; non-exact records share the remaining area by A-reg extent (strip cut)"
        fix_multipart(r, list(others.index))
    r["geometry"] = r.geometry.apply(lambda g: clean(g) if g is not None else None).apply(lambda g: g if g is None or g.is_valid else clean(g.buffer(0)))
    return r


# ---------------- C. finalize ----------------
LEAD = ["kide", "survey_no", "subdiv_no", "area_acre", "area_basis", "village", "unique_id", "survey_uid", "district_id", "taluk_id", "village_id",
        "areg_acre", "site_acre", "split", "inside_pct", "ownership", "patta_number", "government_priority", "land_type_english", "poramboke", "cultivable",
        "owner_details", "owner_number", "remarks", "remarks1", "sensitive_flag", "clip_status", "areg_status",
        "glv_match", "glv_value", "glv_unit", "glv_rate", "glv_sqft_area", "glv_value_lakh", "glv_land_classification", "glv_effective_date",
        "parcel_status", "geometry_quality", "fmb_match", "fmb_kide", "fmb_plot_acre", "parcel_acre"]


def run(site, ctx):
    log = ctx.log
    summ = db.get_summary(site.site_id)
    U = summ.get("utm") or utm_epsg(gpd.read_file(site.boundary).geometry.iloc[0].centroid.x)
    rec, fmb, vec = build_records(site, log, use_glv=_use_glv(site, ctx))
    log(f"{len(rec)} records: " + ", ".join(f"{k} {v}" for k, v in rec.parcel_status.value_counts().items()))
    r = split_records(rec, fmb, vec, U, log)
    r = r[r.geometry.notna()].copy()
    from .parcels import polys
    r["geometry"] = polys(r.geometry)          # self-intersecting Puvi/FMB shapes would stop the clip below
    r = r[r.geometry.notna()].copy()
    # unclipped subdivision shapes: the edge review uses them when a cut survey / subdivision is kept whole
    gpd.GeoDataFrame({"unique_id": r.unique_id.values}, geometry=r.geometry.values, crs=U).to_crs(4326).to_file(site.work / "subdiv_full.geojson", driver="GeoJSON")
    bnd = gpd.read_file(site.boundary).to_crs(U).make_valid().union_all()
    r["full_acre"] = (r.area / ACRE_M2).round(4)
    r["geometry"] = r.geometry.intersection(bnd)
    r["inside_acre"] = (r.area / ACRE_M2).round(4)
    r["inside_pct"] = np.where(r.full_acre > 0, (r.inside_acre / r.full_acre * 100).round(1), 0)
    r["in_site"] = ~(r.split & (r.inside_acre < 0.0005))
    r["area_basis"] = np.where(r.split, "Geometry inside boundary (split survey)", "A-register")
    r["site_acre"] = np.where(r.split, r.inside_acre, r.areg_acre).round(4)
    # no A-register record (the register has no entry for what CLIP lists): count the map area inside, never 0 or a guessed owner
    noreg = pd.to_numeric(r.areg_acre, errors="coerce").isna() & ~r.split
    r.loc[noreg, "site_acre"] = r.loc[noreg, "inside_acre"].round(4)
    r.loc[noreg, "area_basis"] = "Map area (no A-register record)"
    r.loc[~r.in_site, "site_acre"] = 0.0
    sq = r.site_acre * ACRE_M2 * SQFT_PER_M2
    r["glv_sqft_area"] = np.where(r.glv_unit == "Square Feet", sq.round(0), np.nan)
    r["glv_value_lakh"] = np.where(r.glv_unit == "Square Feet", r.glv_rate.fillna(0) * sq / 1e5, np.where(r.glv_unit == "Acre", r.glv_rate.fillna(0) * r.site_acre / 1e5, 0.0)).round(2)
    r["kide"] = np.where(r.sub_division == "-", r.survey_no, r.survey_no + "/" + r.sub_division)
    r["subdiv_no"] = r.sub_division; r["area_acre"] = r.site_acre
    r["ownership"] = np.where(r.government_priority == GOVT, "Govt", "Patta"); r["parcel_acre"] = r.inside_acre
    r.loc[r.areg_status.astype(str) != "Success", "ownership"] = "Unknown (no A-register record)"
    for col in LEAD:
        if col not in r.columns:
            r[col] = None
    site_g = r[r.in_site][LEAD + ["geometry"]].copy()
    site_g["_k"] = site_g.survey_no.map(survey_sort_key); site_g = site_g.sort_values(["village", "_k", "subdiv_no"]).drop(columns="_k")
    gi = site_g.set_index("unique_id").geometry
    ov = gpd.sjoin(site_g[["unique_id", "geometry"]], site_g[["unique_id", "geometry"]], predicate="overlaps")
    ov = ov[ov.unique_id_left < ov.unique_id_right].copy()
    ov["m2"] = [gi[x].intersection(gi[y]).area for x, y in zip(ov.unique_id_left, ov.unique_id_right)]
    ov = ov[ov.m2 > 1]
    gap = bnd.difference(unary_union(site_g.geometry))
    out_g = site_g.to_crs(4326)
    write_geojson(out_g, site.subdivisions)
    db.save_parcels(site.site_id, out_g)
    sm = r.drop(columns="geometry")[["in_site"] + LEAD].copy()
    write_master(site, sm, ov)
    ins = sm[sm.in_site]
    data = {"site_acre": float(ins.site_acre.sum()), "patta_acre": float(ins[ins.ownership == "Patta"].site_acre.sum()), "govt_acre": float(ins[ins.ownership == "Govt"].site_acre.sum()),
            "glv_crore": float(ins.glv_value_lakh.sum() / 100), "subdivisions": int(len(ins)), "overlaps": int(len(ov)), "gap_acre": float(gap.area / ACRE_M2),
            "exact_geometry": int(ins.geometry_quality.str.startswith("Exact").sum())}
    db.save_summary(site.site_id, {"master": data, "master_used_glv": _use_glv(site, ctx)})
    for k in ("subdivisions", "master"):
        db.register_document(site.site_id, k, getattr(site, k))
    return (f"{data['site_acre']:.2f} ac in {data['subdivisions']} subdivisions (patta {data['patta_acre']:.2f}, govt {data['govt_acre']:.2f}); "
            f"GLV Rs {data['glv_crore']:.1f} cr; {data['exact_geometry']} exact plots; {data['overlaps']} overlaps; gap {data['gap_acre']:.2f} ac")


def write_geojson(g, path):
    """write next to the old file then swap, so a layer QGIS has open does not block the run"""
    tmp = path.with_name(path.stem + "_new.geojson")
    g.to_file(tmp, driver="GeoJSON")
    try:
        if path.exists():
            path.unlink()
        tmp.rename(path)
    except PermissionError:
        pass   # the old file is locked (open in QGIS): the new one stays as *_new.geojson


def write_master(site, sm, ov):
    ins = sm[sm.in_site]
    surv = ins.groupby(["village", "survey_no"]).agg(
        subdivisions=("unique_id", "size"), split=("split", "first"), areg_acre=("areg_acre", "sum"), site_acre=("site_acre", "sum"),
        land_type=("land_type_english", lambda s: "/".join(sorted(set(s.dropna())))), ownership=("ownership", lambda s: s.iloc[0] if s.nunique() == 1 else "Mixed"),
        sensitive=("sensitive_flag", lambda s: ", ".join(sorted(set(x for x in s.fillna("") if x)))), glv_value_lakh=("glv_value_lakh", "sum")).reset_index()
    surv[["areg_acre", "site_acre", "glv_value_lakh"]] = surv[["areg_acre", "site_acre", "glv_value_lakh"]].round(2)
    surv["_k"] = surv.survey_no.map(survey_sort_key); surv = surv.sort_values(["village", "_k"]).drop(columns="_k")
    vill = surv.groupby("village").agg(surveys=("survey_no", "size"), subdivisions=("subdivisions", "sum"), areg_acre=("areg_acre", "sum"),
                                       site_acre=("site_acre", "sum"), glv_value_lakh=("glv_value_lakh", "sum")).round(2).reset_index()
    vill = pd.concat([vill, pd.DataFrame([{"village": "TOTAL", **{c: round(vill[c].sum(), 2) for c in ("surveys", "subdivisions", "areg_acre", "site_acre", "glv_value_lakh")}}])], ignore_index=True)
    own = ins.groupby("ownership").site_acre.sum(); lt = ins.groupby("land_type_english").site_acre.sum()
    sqr = ins[ins.glv_unit == "Square Feet"].glv_rate
    sens = ins[ins.sensitive_flag.fillna("") != ""].groupby("sensitive_flag").survey_no.nunique()
    cons = pd.DataFrame([
        ("Site", site.name),
        ("Total area (A-register basis)", f"{ins.site_acre.sum():.2f} acres - full surveys at A-register extent, split edge surveys at the area inside the boundary"),
        ("Villages", ", ".join(f"{v} {a:.2f} ac" for v, a in zip(vill.village[:-1], vill.site_acre[:-1]))),
        ("Surveys / subdivisions", f"{len(surv)} surveys, {len(ins)} subdivisions"),
        ("Patta / Govt", f"Patta {own.get('Patta', 0):.2f} ac, Govt {own.get('Govt', 0):.2f} ac"),
        ("Land type", ", ".join(f"{k} {v:.2f} ac" for k, v in lt.items())),
        ("Pattas", f"{ins[ins.ownership == 'Patta'].patta_number.nunique()} patta numbers"),
        ("Guideline value (indicative)", f"Rs {ins.glv_value_lakh.sum() / 100:.1f} crore; {int((ins.glv_unit == 'Square Feet').sum())} layout plots per Square Feet"
                                         + (f" (Rs {sqr.min():.0f}-{sqr.max():.0f}/sq ft)" if len(sqr) else "") + f", {int((ins.glv_unit == 'Acre').sum())} parcels per acre; govt land 0"),
        ("Crop data", "Pending"),
        ("Sensitive remarks (A-register)", ", ".join(f"{k}: {v} surveys" for k, v in sens.items()) or "none")], columns=["Item", "Value"])
    glvsum = ins.groupby(["village", "glv_unit", "glv_match"]).agg(subdivisions=("unique_id", "size"), site_acre=("site_acre", "sum"), glv_value_lakh=("glv_value_lakh", "sum")).round(2).reset_index()
    geos = ins.groupby("geometry_quality").agg(records=("unique_id", "size"), site_acre=("site_acre", "sum")).round(2).reset_index()
    notes = pd.DataFrame({"Note": [
        "Subdivision list = CLIP; A-register = Tamilnilam per subdivision; GLV = TNReginet survey-wise search; geometry = Puvi FMB / Puvi vector.",
        "Area: full surveys at the A-register extent; split edge surveys at the area inside the boundary (CLIP and A-register still run on the full survey).",
        "GLV columns exactly as TNReginet quotes (per Square Feet for layouts, per acre for land). Unlisted subdivisions: lowest sq-ft rate of the survey for layout plots (<= 500 m2), "
        "else the lowest acre rate of the survey; govt/poramboke 0; surveys with no entry take the lowest same-class rate of the village (indicative, confirm with SRO).",
        "Geometry: exact Puvi FMB plots where the subdivision matches; the rest are APPROXIMATE strip cuts by A-register extent inside their parent plot / survey (geometry_quality).",
        "Crop columns are appended by the crop stage."]})
    with pd.ExcelWriter(site.master, engine="openpyxl") as w:
        cons.to_excel(w, sheet_name="Consolidated_Result", index=False); vill.to_excel(w, sheet_name="Village_Summary", index=False)
        surv.to_excel(w, sheet_name="Survey_Master", index=False); sm.to_excel(w, sheet_name="Subdivision_Master", index=False)
        glvsum.to_excel(w, sheet_name="GLV_Basis_Summary", index=False); geos.to_excel(w, sheet_name="Parcel_Geometry_Summary", index=False)
        ov.drop(columns=["geometry", "index_right"], errors="ignore").round(1).to_excel(w, sheet_name="Parcel_Overlaps", index=False)
        notes.to_excel(w, sheet_name="Notes", index=False)

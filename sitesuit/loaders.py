"""Load reference data into PostGIS: TN revenue villages (once), Puvi vector + FMB (per village, on demand),
statewide crop-survey files, and earlier portal outputs (so finished sites seed the cache)."""
import glob
import os
import warnings

import geopandas as gpd
import pandas as pd
from psycopg.types.json import Jsonb
from shapely import force_2d
from shapely.geometry import MultiPolygon, Polygon

from . import db
from .config import SETTINGS
from .util import safe_sub, vcode

warnings.filterwarnings("ignore")


def _multi(g):
    if g is None or g.is_empty:
        return None
    g = force_2d(g)
    if not g.is_valid:
        g = g.buffer(0)
    if isinstance(g, Polygon):
        return MultiPolygon([g])
    if isinstance(g, MultiPolygon):
        return g
    polys = [p for p in getattr(g, "geoms", []) if isinstance(p, (Polygon, MultiPolygon))]
    parts = [q for p in polys for q in (p.geoms if isinstance(p, MultiPolygon) else [p])]
    return MultiPolygon(parts) if parts else None


def load_revenue_villages(log=print, force=False):
    with db.connect() as c:
        n = c.execute("SELECT count(*) FROM ref.village").fetchone()[0]
    if n and not force:
        log(f"ref.village already has {n} villages")
        return n
    log("reading revenue_village.shp (18,503 villages) ...")
    v = gpd.read_file(SETTINGS.revenue_village_shp).to_crs(4326)
    v = v[v.district_c.notna() & v.taluk_code.notna() & v.village_co.notna()].copy()
    v["vc"] = [vcode(d, t, x) for d, t, x in zip(v.district_c, v.taluk_code, v.village_co)]
    v = v.drop_duplicates("vc")
    rows = [(r.vc, int(r.district_c), int(r.taluk_code), str(r.village_co), r.dist_name, r.taluk_name, r.vill_name,
             None if pd.isna(r.lgd_villag) else str(r.lgd_villag).split(".")[0], (_multi(r.geometry).wkt if _multi(r.geometry) else None))
            for r in v.itertuples()]
    with db.connect() as c:
        c.execute("TRUNCATE ref.village")
        with c.cursor() as cur:
            cur.executemany("""INSERT INTO ref.village (vcode, district_c, taluk_code, village_co, district, taluk, village, lgd_village, geom)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s, ST_GeomFromText(%s, 4326))""", rows)
    log(f"loaded {len(rows)} revenue villages")
    return len(rows)


def villages_touching(boundary_wkt):
    with db.connect() as c:
        return c.execute("""SELECT vcode, district, taluk, village, lgd_village FROM ref.village
                            WHERE ST_Intersects(geom, ST_GeomFromText(%s, 4326)) ORDER BY vcode""", (boundary_wkt,)).fetchall()


def puvi_files(vc):
    d, t, v = vc.split("_")
    base = os.path.join(SETTINGS.puvi_root, d, t, v)
    vec = sorted(glob.glob(os.path.join(base, "vector", "*.shp")))
    fmb = sorted(glob.glob(os.path.join(base, "fmb", "georef", "*.shp"))) or sorted(glob.glob(os.path.join(base, "fmb", "*.shp")))
    fmb = [f for f in fmb if "merged" in os.path.basename(f).lower()] or fmb
    return (vec[0] if vec else None), (fmb[0] if fmb else None)


def _survey_col(df):
    for c in df.columns:
        if c.lower() in ("survey_no", "surveyno", "survey", "sy_no"):
            return c
    for c in df.columns:
        if "survey" in c.lower() or c.lower() == "kide":
            return c
    raise KeyError(f"no survey column in {list(df.columns)}")


def ensure_puvi(vcodes, log=print):
    """Load Puvi vector + FMB of the given villages into cadastral.* unless already loaded. Returns villages with no folder."""
    with db.connect() as c:
        have = {r[0] for r in c.execute("SELECT vcode FROM cadastral.loaded_village WHERE vcode = ANY(%s)", (list(vcodes),))}
    missing = []
    for vc in vcodes:
        if vc in have:
            continue
        vf, ff = puvi_files(vc)
        if not vf:
            missing.append(vc); log(f"  {vc}: no Puvi vector folder"); continue
        g = gpd.read_file(vf).to_crs(4326)
        sc = _survey_col(g)
        g["survey_no"] = g[sc].astype(str).str.split("/").str[0].str.strip().str.replace(r"\.0$", "", regex=True)
        srows = [(vc, r.survey_no, r.survey_no, _multi(r.geometry).wkt) for r in g.itertuples() if _multi(r.geometry) is not None]
        frows = []
        if ff:
            f = gpd.read_file(ff).to_crs(4326)
            kc = "KIDE" if "KIDE" in f.columns else _survey_col(f)
            k = f[kc].astype(str).str.strip()
            for kide, geom in zip(k, f.geometry):
                if geom is None or geom.is_empty:
                    continue
                parts = kide.split("/")
                frows.append((vc, kide, parts[0].strip(), "/".join(p.strip() for p in parts[1:]) or None, force_2d(geom).wkt))
        with db.connect() as c:
            c.execute("DELETE FROM cadastral.puvi_survey WHERE vcode = %s", (vc,)); c.execute("DELETE FROM cadastral.puvi_fmb WHERE vcode = %s", (vc,))
            with c.cursor() as cur:
                cur.executemany("INSERT INTO cadastral.puvi_survey (vcode, survey_no, kide, geom) VALUES (%s,%s,%s, ST_GeomFromText(%s,4326))", srows)
                if frows:
                    cur.executemany("INSERT INTO cadastral.puvi_fmb (vcode, kide, survey_no, subdiv_no, geom) VALUES (%s,%s,%s,%s, ST_GeomFromText(%s,4326))", frows)
            c.execute("""INSERT INTO cadastral.loaded_village (vcode, vector_file, fmb_file, surveys, fmb_plots) VALUES (%s,%s,%s,%s,%s)
                         ON CONFLICT (vcode) DO UPDATE SET vector_file=EXCLUDED.vector_file, fmb_file=EXCLUDED.fmb_file,
                         surveys=EXCLUDED.surveys, fmb_plots=EXCLUDED.fmb_plots, loaded_at=now()""", (vc, vf, ff, len(srows), len(frows)))
        log(f"  {vc}: loaded {len(srows)} survey polygons, {len(frows)} FMB plots")
    return missing


# ---------- crop survey (statewide files from the teammate's faas_db export) ----------
CROP_COLS = ["crop_survey_id", "village_code", "survey_number", "sub_division_number", "patta_number", "land_type", "crop_season_type_name",
             "crop_name", "crop_classification", "crop_area_acres", "sown_date", "tree_count"]


def load_crop_workbook(path, log=print):
    """Excel with one sheet per season ('Rabi 2024', 'Kharif 2024', 'Summer 2025', ...) in the faas_db export columns.
    Rows are de-duplicated on (season, crop_survey_id); existing rows are replaced."""
    xs = pd.read_excel(path, sheet_name=None, dtype=str)
    total = 0
    for season, d in xs.items():
        if "crop_survey_id" not in d.columns:
            continue
        d = d.drop_duplicates("crop_survey_id")
        rows = []
        for r in d.itertuples(index=False):
            g = r._asdict()
            area = pd.to_numeric(g.get("crop_area_acres"), errors="coerce")
            rows.append((season, g["crop_survey_id"], str(g.get("village_code") or "").split(".")[0], (g.get("survey_number") or "").strip(),
                         (g.get("sub_division_number") or "").strip() or None, g.get("patta_number"), g.get("land_type"), g.get("crop_season_type_name"),
                         g.get("crop_name"), g.get("crop_classification"), None if pd.isna(area) else float(area), g.get("sown_date"), g.get("tree_count"), str(path)))
        with db.connect() as c:
            with c.cursor() as cur:
                cur.executemany("""INSERT INTO crop.survey_record (season, crop_survey_id, lgd_village_code, survey_number, sub_division_number, patta_number,
                                   land_type, crop_season_type_name, crop_name, crop_classification, crop_area_acres, sown_date, tree_count, source_file)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                   ON CONFLICT (season, crop_survey_id) DO UPDATE SET lgd_village_code=EXCLUDED.lgd_village_code, survey_number=EXCLUDED.survey_number,
                                   sub_division_number=EXCLUDED.sub_division_number, crop_season_type_name=EXCLUDED.crop_season_type_name, crop_name=EXCLUDED.crop_name,
                                   crop_area_acres=EXCLUDED.crop_area_acres, source_file=EXCLUDED.source_file, loaded_at=now()""", rows)
        log(f"crop {season}: {len(rows)} entries"); total += len(rows)
    return total


# ---------- seed the portal cache from earlier site outputs ----------
def import_clip_output(path, log=print):
    c_ = pd.read_excel(path, dtype=str)
    rows = [(vcode(r.district_id, r.taluk_id, r.village_id), str(r.survey_no).strip(), safe_sub(r.sub_division), r.response_status) for r in c_.itertuples()]
    with db.connect() as c:
        with c.cursor() as cur:
            cur.executemany("""INSERT INTO portal.clip_subdivision VALUES (%s,%s,%s,%s, now()) ON CONFLICT (vcode, survey_no, sub_division)
                               DO UPDATE SET status = EXCLUDED.status""", rows)
            cur.executemany("""INSERT INTO portal.clip_survey_done VALUES (%s,%s,'Success', now()) ON CONFLICT DO NOTHING""",
                            sorted({(a, b) for a, b, _, _ in rows}))
    log(f"CLIP cache: {len(rows)} rows from {path}")


def import_areg_raw(path, log=print):
    a = pd.read_excel(path, dtype=str)
    st = "response_status.1" if "response_status.1" in a.columns else "response_status"
    rows = []
    for r in a.to_dict("records"):
        vc = vcode(r["district_id"], r["taluk_id"], r["village_id"])
        keep = ("patta_number", "government_priority", "extent_hectares", "extent_ares", "land_type_english", "poramboke", "cultivable",
                "remarks", "remarks1", "owner_details", "owner_update_dates", "owner_number")
        rec = {k: (None if (isinstance(r.get(k), float) and r.get(k) != r.get(k)) else r.get(k)) for k in keep}
        rows.append((vc, str(r["survey_no"]).strip(), safe_sub(r["sub_division"]), r.get(st), Jsonb(rec)))
    with db.connect() as c:
        with c.cursor() as cur:
            cur.executemany("""INSERT INTO portal.areg VALUES (%s,%s,%s,%s,%s, now()) ON CONFLICT (vcode, survey_no, sub_division)
                               DO UPDATE SET status = EXCLUDED.status, record = EXCLUDED.record, fetched_at = now()""", rows)
    log(f"A-register cache: {len(rows)} rows from {path}")


def import_glv_output(path, log=print, sheet=0):
    g = pd.read_excel(path, sheet_name=sheet, dtype=str)
    g["vc"] = [vcode(d, t, v) for d, t, v in zip(g.district_id, g.taluk_id, g.village_id)]
    g["survey_no"] = g.survey_no.str.strip()
    rows, mp = [], {}
    for (vc_, sn), grp in g.groupby(["vc", "survey_no"]):
        for i, r in enumerate(grp.to_dict("records"), 1):
            rows.append((vc_, sn, i, r.get("Subdivision Number"), r.get("Guideline_Value_British"), r.get("Guideline_Value_Metric"),
                         r.get("Land_Classification"), r.get("Effective_Start_Date"), r.get("Status")))
        r0 = grp.iloc[0]
        if "village_list_id" in grp.columns:
            mp[vc_] = (str(r0.zone_list_id).split(".")[0], str(r0.sro_list_id).split(".")[0], str(r0.village_list_id).split(".")[0])
    with db.connect() as c:
        with c.cursor() as cur:
            cur.executemany("DELETE FROM portal.glv WHERE vcode = %s AND survey_no = %s", sorted({(a, b) for a, b, *_ in rows}))
            cur.executemany("INSERT INTO portal.glv VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())", rows)
            cur.executemany("""INSERT INTO portal.reginet_village (vcode, zone_list_id, sro_list_id, village_list_id, confirmed) VALUES (%s,%s,%s,%s,true)
                               ON CONFLICT (vcode) DO UPDATE SET zone_list_id=EXCLUDED.zone_list_id, sro_list_id=EXCLUDED.sro_list_id,
                               village_list_id=EXCLUDED.village_list_id, confirmed=true, updated_at=now()""", [(k, *v) for k, v in mp.items()])
    log(f"GLV cache: {len(rows)} rows, {len(mp)} village ids from {path}")

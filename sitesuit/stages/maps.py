"""Stage 9 - connectivity (OpenStreetMap via Overpass) + district/taluk lines + satellite base renders (standalone PyQGIS)."""
import glob
import json
import math
import os
import subprocess
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely import wkb
from shapely.geometry import LineString, Point

from .. import db
from ..config import SETTINGS

NAME, TITLE = "maps", "Connectivity + map renders"
PALETTE = ["#2ecc71", "#4a8df0", "#ff7f0e", "#a855f7", "#f0c419", "#e74c3c", "#1abc9c", "#ff69b4"]


def overpass(q, cache):
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    for attempt in range(3):
        try:
            r = requests.post(SETTINGS.overpass_url, data={"data": q}, timeout=240)
            r.raise_for_status(); d = r.json()
            cache.write_text(json.dumps(d), encoding="utf-8"); return d
        except Exception as e:
            err = e; time.sleep(10)
    raise RuntimeError(f"Overpass failed: {err}")


def build_conn(site, geom):
    x0, y0, x1, y1 = geom.bounds
    near = f"{y0 - 0.03},{x0 - 0.03},{y1 + 0.03},{x1 + 0.03}"
    wide = f"{y0 - 0.3},{x0 - 0.3},{y1 + 0.3},{x1 + 0.3}"
    q = (f"[out:json][timeout:200];(way[highway~\"^(tertiary|unclassified)$\"]({near});"
         f"way[highway~\"^(motorway|trunk|primary|secondary)$\"]({wide});way[railway=rail]({wide});node[railway~\"^(station|halt)$\"]({wide});"
         f"node[place~\"^(town|city)$\"]({wide});node[place=village]({near}););out geom;")
    els = overpass(q, site.work / "osm_overpass.json")["elements"]
    roads, rail, st, pl = [], [], [], []
    for e in els:
        t = e.get("tags", {})
        if e["type"] == "way" and "geometry" in e:
            gg = LineString([(p["lon"], p["lat"]) for p in e["geometry"]])
            if "highway" in t:
                roads.append({"osm_id": e["id"], "highway": t["highway"], "name": t.get("name:en") or t.get("name"), "ref": t.get("ref"), "geometry": gg})
            elif t.get("railway") == "rail":
                rail.append({"osm_id": e["id"], "name": t.get("name:en") or t.get("name"), "geometry": gg})
        elif e["type"] == "node":
            gg = Point(e["lon"], e["lat"])
            if t.get("railway") in ("station", "halt"):
                st.append({"name": t.get("name:en") or t.get("name"), "kind": t["railway"], "geometry": gg})
            elif "place" in t:
                pl.append({"name": t.get("name:en") or t.get("name"), "place": t["place"], "geometry": gg})
    L = {}
    cols = {"roads": ["osm_id", "highway", "name", "ref"], "rail": ["osm_id", "name"], "stations": ["name", "kind"], "towns": ["name", "place"]}
    out = site.work / "conn.gpkg"
    if out.exists():
        out.unlink()
    for k, v in (("roads", roads), ("rail", rail), ("stations", st), ("towns", pl)):
        L[k] = gpd.GeoDataFrame(v, geometry="geometry", crs=4326) if v else gpd.GeoDataFrame(columns=cols[k] + ["geometry"], geometry="geometry", crs=4326)
        L[k].to_file(out, layer=k, driver="GPKG")
    return out, L


def bearing(a, b):
    dx = (b.x - a.x) * math.cos(math.radians(a.y)); dy = b.y - a.y
    return round(math.degrees(math.atan2(dx, dy)) % 360, 1)


def connectivity(site, geom, L, U):
    b = gpd.GeoSeries([geom], crs=4326).to_crs(U).iloc[0]; c = geom.centroid
    km = lambda gdf: (gdf.to_crs(U).distance(b) / 1000).round(2)
    R = L["roads"].copy(); R["km"] = km(R) if len(R) else []
    R["label"] = [(f"{n} ({r})" if n and r else (n or r or "")) for n, r in zip(R.name.fillna(""), R.ref.fillna("").str.replace("MDR", "MDR ").str.replace("SH", "SH ").str.replace("NH", "NH "))]
    out = {"lines": [], "road_ids": [], "village_road_ids": [], "arrows": [], "stations": []}

    def nearest(mask, n):
        x = R[mask & (R.label != "")].sort_values("km")
        return x.drop_duplicates("label").head(n), x
    rl = L["rail"]
    if len(rl):
        d = float(km(rl).min())
        out["rail_km"] = d
        out["lines"].append("Railway line abuts the site" if d < 0.2 else f"Railway line - {d:.2f} km")
    vr, vall = nearest(R.highway.isin(["tertiary", "unclassified"]) & R.name.notna() & (R.km <= 1.5), 2)
    for r in vr.itertuples():
        out["lines"].append(f"{r.name} - {r.km:.2f} km")
    out["village_road_ids"] = [int(i) for i in vall[vall.name.isin(vr.name)].osm_id]
    md, mall = nearest(R.ref.fillna("").str.startswith("MDR") | ((R.highway == "secondary") & R.name.notna()), 2)
    for r in md.itertuples():
        out["lines"].append(f"{r.label} - {r.km:.2f} km")
    out["road_ids"] = [int(i) for i in mall[mall.label.isin(md.label)].osm_id]
    S = L["stations"].copy()
    if len(S):
        S["km"] = km(S); S = S.sort_values("km").head(2)
        for r in S.itertuples():
            out["lines"].append(f"{r.name} Rly Stn - {r.km:.2f} km"); out["stations"].append([r.name, r.geometry.x, r.geometry.y, r.km])
    sh, _ = nearest(R.ref.fillna("").str.startswith("SH"), 1)
    for r in sh.itertuples():
        out["lines"].append(f"{r.label} - {r.km:.2f} km")
    nh, _ = nearest(R.ref.fillna("").str.startswith("NH"), 1)
    for r in nh.itertuples():
        out["lines"].append(f"{r.label} - {r.km:.2f} km"); out["nh"] = f"{r.label} - {r.km:.2f} km"
    T = L["towns"]; T = T[T.place.isin(["town", "city"]) & T.name.notna()].copy()
    if len(T):
        T["km"] = km(T); T = T.sort_values("km").head(2)
        for r in T.itertuples():
            out["lines"].append(f"{r.name} Town - {r.km:.2f} km"); out["arrows"].append([bearing(c, r.geometry), f"To {r.name} Town\n{r.km:.2f} km"])
    # nearest existing SIPCOT park (straight line)
    best = None
    for f in glob.glob(str(SETTINGS.sipcot_parks_dir / "*" / "*Outer_Boundary*.geojson")):
        try:
            d = float(gpd.read_file(f).to_crs(U).distance(b).min() / 1000)
        except Exception:
            continue
        nm = Path(f).parent.name.replace("_", " ")
        if best is None or d < best[1]:
            best = (nm, d)
    if best:
        out["sipcot_park"] = f"Nearest SIPCOT Park: {best[0].replace(' AP', '')} - {best[1]:.1f} km"
    return out


def build_admin(site, geom):
    x0, y0, x1, y1 = geom.bounds
    env = f"POLYGON(({x0 - 0.5} {y0 - 0.5},{x1 + 0.5} {y0 - 0.5},{x1 + 0.5} {y1 + 0.5},{x0 - 0.5} {y1 + 0.5},{x0 - 0.5} {y0 - 0.5}))"
    with db.connect() as c:
        d = c.execute("SELECT district, ST_AsBinary(ST_Union(geom)) FROM ref.village WHERE ST_Intersects(geom, ST_GeomFromText(%s,4326)) GROUP BY district", (env,)).fetchall()
        t = c.execute("SELECT district, taluk, ST_AsBinary(ST_Union(geom)) FROM ref.village WHERE ST_Intersects(geom, ST_GeomFromText(%s,4326)) GROUP BY district, taluk", (env,)).fetchall()
    out = site.work / "admin.gpkg"
    if out.exists():
        out.unlink()
    gpd.GeoDataFrame({"district": [r[0] for r in d]}, geometry=[wkb.loads(bytes(r[1])) for r in d], crs=4326).to_file(out, layer="district", driver="GPKG")
    gpd.GeoDataFrame({"district": [r[0] for r in t], "taluk": [r[1] for r in t]}, geometry=[wkb.loads(bytes(r[2])) for r in t], crs=4326).to_file(out, layer="taluk", driver="GPKG")
    return out


def run(site, ctx):
    summ = db.get_summary(site.site_id)
    U = summ.get("utm", 32644)
    geom = gpd.read_file(site.boundary).geometry.iloc[0]
    ctx.log("fetching roads / railway / towns from OpenStreetMap ...")
    conn, L = build_conn(site, geom)
    cn = connectivity(site, geom, L, U)
    (site.work / "connectivity.json").write_text(json.dumps(cn, indent=1), encoding="utf-8")
    admin = build_admin(site, geom)
    vills = [v["village"] for v in summ.get("villages", [])]
    raw = site.work / "render"; raw.mkdir(exist_ok=True)
    params = {"out_dir": str(raw), "boundary": str(site.boundary), "parcels": str(site.subdivisions), "conn": str(conn), "admin": str(admin), "utm": U,
              "road_ids": cn["road_ids"], "village_road_ids": cn["village_road_ids"], "village_colors": {v: PALETTE[i % len(PALETTE)] for i, v in enumerate(vills)}}
    pj = site.work / "render_params.json"; pj.write_text(json.dumps(params), encoding="utf-8")
    if not SETTINGS.qgis_python.exists():
        raise RuntimeError(f"QGIS python not found: {SETTINGS.qgis_python} (set QGIS_PYTHON in .env)")
    ctx.log("rendering satellite maps with QGIS (about 1 minute) ...")
    script = Path(__file__).resolve().parent.parent / "qgis_render.py"
    (raw / "_render_info.json").unlink(missing_ok=True)
    p = subprocess.run(["cmd", "/c", str(SETTINGS.qgis_python), str(script), str(pj)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if not (raw / "_render_info.json").exists():   # QGIS may exit non-zero on shutdown after a good render
        raise RuntimeError("QGIS render failed: " + (p.stderr or p.stdout)[-800:])
    db.save_summary(site.site_id, {"connectivity": {k: v for k, v in cn.items() if k not in ("road_ids", "village_road_ids")}, "village_colors": params["village_colors"]})
    return "; ".join(cn["lines"][:6])

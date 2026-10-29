"""Stage - regional context slide (after the location map): the site against the region's key logistics nodes -
nearest seaports, airport, existing SIPCOT parks and the national highway network - with straight-line and road distance
(public OSRM router, a handful of requests per site) and drive time."""
import glob
import json
import math
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely import wkb
from shapely.geometry import LineString, Point

from .. import db
from ..config import SETTINGS
from .maps import overpass, qgis_render

NAME, TITLE = "regional", "Regional context slide"
OSRM = "https://router.project-osrm.org/route/v1/driving/{a};{b}?overview=false"
# major seaports and airports of / near Tamil Nadu (approximate terminal locations)
PORTS = [("Chennai Port", 13.0985, 80.2950), ("Kamarajar Port (Ennore)", 13.2569, 80.3259), ("Kattupalli Port", 13.3070, 80.3410),
         ("V.O. Chidambaranar Port (Thoothukudi)", 8.7480, 78.1910), ("Karaikal Port", 10.8400, 79.8500), ("Cuddalore Port", 11.7370, 79.7820),
         ("Nagapattinam Port", 10.7700, 79.8480), ("Krishnapatnam Port", 14.2500, 80.1200)]
AIRPORTS = [("Chennai International Airport", 12.9941, 80.1709), ("Tiruchirappalli Airport", 10.7654, 78.7097), ("Coimbatore Airport", 11.0300, 77.0434),
            ("Madurai Airport", 9.8345, 78.0934), ("Thoothukudi Airport", 8.7242, 78.0258), ("Salem Airport", 11.7833, 78.0656),
            ("Puducherry Airport", 11.9680, 79.8100), ("Bengaluru Kempegowda Airport", 13.1986, 77.7066), ("Tirupati Airport", 13.6325, 79.5433)]


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def road(a, b):
    try:
        r = requests.get(OSRM.format(a=f"{a[1]},{a[0]}", b=f"{b[1]},{b[0]}"), timeout=30).json()
        if r.get("code") == "Ok":
            return round(r["routes"][0]["distance"] / 1000, 1), round(r["routes"][0]["duration"] / 60)
    except Exception:
        pass
    finally:
        time.sleep(1.1)       # OSRM demo server: at most one request a second
    return None, None


def run(site, ctx):
    geom = gpd.read_file(site.boundary).geometry.iloc[0]
    c = (geom.centroid.y, geom.centroid.x)
    marks = []
    for kind, lst, n in (("Seaport", PORTS, 2), ("Airport", AIRPORTS, 1)):
        for nm, la, lo in sorted(lst, key=lambda p: km(c, (p[1], p[2])))[:n]:
            marks.append({"kind": kind, "name": nm, "lat": la, "lon": lo})
    parks = []
    for f in glob.glob(str(SETTINGS.sipcot_parks_dir / "*" / "*Outer_Boundary*.geojson")):
        try:
            g = gpd.read_file(f).to_crs(4326).union_all()
        except Exception:
            continue
        p = g.representative_point(); parks.append((km(c, (p.y, p.x)), Path(f).parent.name.replace("_", " ").replace(" AP", ""), p.y, p.x))
    kept = []
    for d_, nm, la, lo in sorted(parks):        # one park can be split over two districts: keep parks at least 5 km apart
        if all(km((la, lo), (k[2], k[3])) >= 5 for k in kept):
            kept.append((d_, nm, la, lo))
        if len(kept) == 2:
            break
    for d_, nm, la, lo in kept:
        marks.append({"kind": "SIPCOT park", "name": f"SIPCOT {nm}", "lat": la, "lon": lo})
    ctx.log(f"road distances for {len(marks)} landmarks (OSRM) ...")
    for m in marks:
        m["km"] = round(km(c, (m["lat"], m["lon"])), 1)
        m["road_km"], m["minutes"] = road(c, (m["lat"], m["lon"]))
    # region extent: site + landmarks within 120 km (far ones are listed, not drawn)
    near = [m for m in marks if m["km"] <= 120] or marks[:1]
    lats = [c[0]] + [m["lat"] for m in near]; lons = [c[1]] + [m["lon"] for m in near]
    pad = 0.12
    bbox = [min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad]
    # NH / expressway network + district lines for the wide map
    q = f"[out:json][timeout:240];(way[highway~\"^(motorway|trunk)$\"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}););out geom;"
    els = overpass(q, site.work / "osm_regional.json")["elements"]
    nh = [{"ref": e.get("tags", {}).get("ref"), "geometry": LineString([(p["lon"], p["lat"]) for p in e["geometry"]])} for e in els if e["type"] == "way" and "geometry" in e]
    out = site.work / "regional.gpkg"
    if out.exists():
        out.unlink()
    gpd.GeoDataFrame(nh or [{"ref": None, "geometry": LineString([(c[1], c[0]), (c[1], c[0] + 1e-6)])}], geometry="geometry", crs=4326).to_file(out, layer="nh", driver="GPKG")
    env = f"POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]}))"
    with db.connect() as cn:
        rows = cn.execute("SELECT district, ST_AsBinary(ST_SimplifyPreserveTopology(ST_Union(geom), 0.002)) FROM ref.village WHERE ST_Intersects(geom, ST_GeomFromText(%s,4326)) GROUP BY district", (env,)).fetchall()
    gpd.GeoDataFrame({"district": [r[0] for r in rows]}, geometry=[wkb.loads(bytes(r[1])) for r in rows], crs=4326).to_file(out, layer="district", driver="GPKG")
    (site.work / "regional_bbox.json").write_text(json.dumps(bbox), encoding="utf-8")
    qgis_render(site, ctx, only=["region_wide"])
    db.save_summary(site.site_id, {"regional": {"marks": marks, "bbox": bbox}})
    return "; ".join(f"{m['name']} {m['km']} km" + (f" (road {m['road_km']} km, {m['minutes']} min)" if m["road_km"] else "") for m in marks)

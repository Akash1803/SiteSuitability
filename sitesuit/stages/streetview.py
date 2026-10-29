"""Stage 10 - street-view points for the PPT.
Picks up to 4 viewpoints on the roads next to the site (spread along the boundary, bigger roads first, camera facing the site)
and gives each a Google Maps street-view link. Photos for the hidden full-photo slides come from, in this order:
  1. your own pictures in 07_PPT_Maps/street_view/pin_<n>.png|jpg (for example screenshots you took), or
  2. the Google Street View Static API when GOOGLE_MAPS_KEY is set in .env (a company key; billable, a few rupees per site).
Without either, the slide still has the pins and each pin opens that spot in Google Maps."""
import json
import math

import geopandas as gpd
import numpy as np
import requests

from .. import db
from ..config import SETTINGS

NAME, TITLE = "streetview", "Street view points"
RANK = {"motorway": 0, "trunk": 0, "primary": 1, "secondary": 2, "tertiary": 3, "unclassified": 4}
MAX_PINS, NEAR_M, STEP_M = 4, 150, 40


def pick_points(geom, roads, U, n=MAX_PINS):
    b = gpd.GeoSeries([geom], crs=4326).to_crs(U).iloc[0]
    r = roads.to_crs(U)
    r = r[r.distance(b) <= NEAR_M].copy()
    if r.empty:
        return []
    cand = []
    for row in r.itertuples():
        g = row.geometry
        for d in np.arange(0, g.length, STEP_M):
            p = g.interpolate(d)
            dist = p.distance(b)
            if dist <= NEAR_M:
                cand.append((RANK.get(row.highway, 5), dist, p, row.name if isinstance(row.name, str) else (row.ref if isinstance(row.ref, str) else row.highway)))
    if not cand:
        return []
    best_rank = min(c[0] for c in cand)
    pool = [c for c in cand if c[0] <= best_rank + 1] if len([c for c in cand if c[0] <= best_rank + 1]) >= n else cand
    chosen = [min(pool, key=lambda c: (c[0], c[1]))]
    while len(chosen) < n:          # farthest-point sampling: spread the pins around the site
        nxt = max(pool, key=lambda c: min(c[2].distance(x[2]) for x in chosen) - 30 * c[0])
        if min(nxt[2].distance(x[2]) for x in chosen) < 250:
            break
        chosen.append(nxt)
    c = b.centroid
    pts = gpd.GeoSeries([x[2] for x in chosen], crs=U).to_crs(4326)
    out = []
    for i, (x, p4) in enumerate(zip(chosen, pts), 1):
        heading = (math.degrees(math.atan2(c.x - x[2].x, c.y - x[2].y)) + 360) % 360
        out.append({"n": i, "label": str(x[3]), "lat": round(p4.y, 7), "lon": round(p4.x, 7), "heading": int(round(heading))})
    return out


def run(site, ctx):
    summ = db.get_summary(site.site_id)
    U = summ.get("utm", 32644)
    geom = gpd.read_file(site.boundary).geometry.iloc[0]
    roads = gpd.read_file(site.work / "conn.gpkg", layer="roads")
    pts = pick_points(geom, roads, U)
    if not pts:
        raise RuntimeError("no mapped road within 150 m of the boundary - no street-view points")
    key = SETTINGS.google_maps_key
    own = site.maps_dir / "street_view"; own.mkdir(exist_ok=True)
    for p in pts:
        p["pano"], p["date"] = None, ""
        if key:      # metadata is free; it gives the exact panorama and its date
            try:
                m = requests.get("https://maps.googleapis.com/maps/api/streetview/metadata",
                                 params={"location": f"{p['lat']},{p['lon']}", "radius": 80, "source": "outdoor", "key": key}, timeout=30).json()
                if m.get("status") == "OK":
                    p["pano"], p["date"] = m.get("pano_id"), m.get("date", "")
            except Exception as e:
                ctx.log(f"street view metadata failed for pin {p['n']}: {e}")
        p["url"] = (f"https://www.google.com/maps/@?api=1&map_action=pano&pano={p['pano']}&heading={p['heading']}&pitch=0&fov=90" if p["pano"] else
                    f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={p['lat']},{p['lon']}&heading={p['heading']}&pitch=0&fov=90")
        mine = [f for f in (own / f"pin_{p['n']}.png", own / f"pin_{p['n']}.jpg") if f.exists()]
        if mine:
            p["photo"], p["photo_source"] = str(mine[0]), "your picture"
        elif key and p["pano"]:
            img = site.work / f"sv_pin_{p['n']}.jpg"
            r = requests.get("https://maps.googleapis.com/maps/api/streetview",
                             params={"size": "640x400", "scale": 2, "pano": p["pano"], "heading": p["heading"], "pitch": 0, "fov": 90, "key": key}, timeout=60)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                img.write_bytes(r.content); p["photo"], p["photo_source"] = str(img), "Google Street View"
        p.setdefault("photo", None)
    (site.work / "streetview.json").write_text(json.dumps(pts, indent=1), encoding="utf-8")
    with_photo = sum(1 for p in pts if p["photo"])
    db.save_summary(site.site_id, {"streetview": {"pins": len(pts), "photos": with_photo}})
    note = "" if with_photo else f" (no photos: pins open Google Maps; put pin_1..{len(pts)}.png in 07_PPT_Maps/street_view or set GOOGLE_MAPS_KEY)"
    return f"{len(pts)} pins: " + "; ".join(f"{p['n']} {p['label']}" for p in pts) + f"; {with_photo} with photo" + note

"""Stage - boundary dimensions and road / rail frontage, drawn on the existing Boundary slide (no extra slide):
overall length and width (minimum rotated rectangle), perimeter, compactness, and the length of boundary that runs
along each road or the railway (within 40 m).
Roads with a name / ref in OpenStreetMap are labelled by it. A road the site touches that has no name in OSM, or that
OSM does not have at all but the satellite does (Microsoft Road Detections, ref.detected_road), is still a frontage:
its centreline is traced outward from both ends of the frontage until it reaches a place or joins a named road, and each
end is labelled with where it leads ("To <village>", "Joins <road>")."""
import math

import geopandas as gpd
from shapely.geometry import LineString, Point, mapping
from shapely.ops import linemerge, substring, unary_union

from .. import db

NAME, TITLE = "dimensions", "Boundary dimensions + frontage"
NEAR_M, MIN_FRONT_M, MIN_UNNAMED_M = 40, 50, 100
HW = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified"}
MINOR = {"tertiary", "unclassified", "residential", "track", "service", "road", "living_street", "tertiary_link", "secondary_link"}
TRACE_M, JOIN_M, PLACE_NEAR_M, DRAW_M = 6000, 25, 400, 2500
SAT_LABEL = "Road on satellite, not in OSM"


def _label(n, r):
    n = n if isinstance(n, str) and n.strip() else None; r = r if isinstance(r, str) and r.strip() else None
    return f"{n} ({r})" if n and r else (n or r)


def _local_osm(site, b4326, log):
    """every OSM way tagged highway + place nodes within ~9 km (cached per site)"""
    from .maps import overpass
    x0, y0, x1, y1 = b4326.bounds; m = 0.08
    bb = f"{y0 - m},{x0 - m},{y1 + m},{x1 + m}"
    q = (f"[out:json][timeout:180];(way[highway]({bb});"
         f"node[place~\"^(village|hamlet|town|city|suburb|neighbourhood|locality)$\"]({bb}););out geom;")
    els = overpass(q, site.work / "osm_frontage.json", log)["elements"]
    roads, places = [], []
    for e in els:
        t = e.get("tags", {})
        if e["type"] == "way" and "geometry" in e and "highway" in t and len(e["geometry"]) > 1:
            roads.append({"osm_id": e["id"], "highway": t["highway"], "name": t.get("name:en") or t.get("name"), "ref": t.get("ref"),
                          "geometry": LineString([(p["lon"], p["lat"]) for p in e["geometry"]])})
        elif e["type"] == "node" and (t.get("name:en") or t.get("name")):
            places.append({"name": t.get("name:en") or t.get("name"), "place": t.get("place"), "geometry": Point(e["lon"], e["lat"])})
    R = gpd.GeoDataFrame(roads, geometry="geometry", crs=4326) if roads else gpd.GeoDataFrame(columns=["osm_id", "highway", "name", "ref", "geometry"], geometry="geometry", crs=4326)
    P = gpd.GeoDataFrame(places, geometry="geometry", crs=4326) if places else gpd.GeoDataFrame(columns=["name", "place", "geometry"], geometry="geometry", crs=4326)
    return R, P


def _detected(b4326):
    """satellite-detected road lines around the site; empty when the table was never loaded"""
    x0, y0, x1, y1 = b4326.bounds; m = 0.08
    try:
        with db.connect() as c:
            rows = c.execute("SELECT width_m, ST_AsBinary(geom) FROM ref.detected_road WHERE geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)",
                             (x0 - m, y0 - m, x1 + m, y1 + m)).fetchall()
    except Exception:
        rows = []
    from shapely import wkb
    return gpd.GeoDataFrame({"width_m": [r[0] for r in rows]}, geometry=[wkb.loads(bytes(r[1])) for r in rows], crs=4326)


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def _head(line, from_start, m=60):
    """direction of the first ~m metres of a line, walking away from the chosen end"""
    if not from_start:
        line = LineString(line.coords[::-1])
    p = line.interpolate(min(m, line.length))
    return _unit(line.coords[0], (p.x, p.y))


def _trace(start, heading, lines, named, limit):
    """walk the road network from `start` (heading = unit vector) choosing the straightest continuation at each joint.
    lines: [(LineString, label or None)]. Returns (path LineString or None, joined label or None)."""
    pts = [start]; pos = start; dist = 0.0; used = set()
    while dist < limit:
        hit = [lab for g, lab in named if g.distance(Point(pos)) <= JOIN_M]
        if hit and dist > 30:
            return LineString(pts) if len(pts) > 1 else None, hit[0]
        best = None
        for i, (g, lab) in enumerate(lines):
            if i in used or lab:
                continue
            for from_start in (True, False):
                end = g.coords[0] if from_start else g.coords[-1]
                if math.dist(end, pos) > JOIN_M:
                    continue
                h = _head(g, from_start); cos = h[0] * heading[0] + h[1] * heading[1]
                if cos > 0.5 and (best is None or cos > best[0]):
                    best = (cos, i, g if from_start else LineString(g.coords[::-1]))
        if best is None:
            break
        _, i, g = best; used.add(i)
        cs = list(g.coords); pts += cs[1:]; dist += g.length; pos = cs[-1]
        heading = _unit(cs[-2], cs[-1]) if len(cs) > 1 else heading
    return (LineString(pts) if len(pts) > 1 else None), None


def _where(path, joined, places, site_geom):
    """text for one end: first named place the road passes (beyond the site), else the road it joins, else the nearest
    place to where the trace stops, else a compass direction"""
    if path is not None and len(places):
        far = places[places.distance(site_geom) > 300].copy()
        far["d"] = far.distance(path); far = far[far.d <= PLACE_NEAR_M]
        if len(far):
            far["along"] = [path.project(g) for g in far.geometry]
            return f"To {far.sort_values('along').iloc[0]['name']}"
    if joined:
        return f"Joins {joined}"
    if path is not None and len(places):
        end = Point(path.coords[-1]); p = places.assign(d=places.distance(end)).sort_values("d")
        if len(p) and p.iloc[0].d <= 3000:
            return f"Towards {p.iloc[0]['name']}"
    if path is not None:
        (x0, y0), (x1, y1) = path.coords[0], path.coords[-1]
        ang = math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360
        return "Towards " + ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][int((ang + 22.5) // 45) % 8]
    return "Road end"


def run(site, ctx):
    U = db.get_summary(site.site_id).get("utm", 32644)
    b4326 = gpd.read_file(site.boundary).geometry.iloc[0]
    b = gpd.GeoSeries([b4326], crs=4326).to_crs(U).iloc[0]
    ring = unary_union([p.exterior for p in getattr(b, "geoms", [b])])
    mrr = b.minimum_rotated_rectangle
    xs, ys = mrr.exterior.coords.xy
    e = [((xs[i], ys[i]), (xs[i + 1], ys[i + 1])) for i in range(4)]
    L = lambda s: math.dist(*s)
    long_e = max(e[:2], key=L); short_e = min(e[:2], key=L)
    conn = site.work / "conn.gpkg"
    to4326 = lambda g: mapping(gpd.GeoSeries([g], crs=U).to_crs(4326).iloc[0])
    fronts = []
    if conn.exists():
        roads = gpd.read_file(conn, layer="roads").to_crs(U)
        roads = roads[roads.highway.isin(HW)].copy()
        roads["label"] = [_label(n, r) for n, r in zip(roads.name, roads.ref)]
        roads = roads[roads.label.notna() & (roads.distance(b) <= NEAR_M)]
        items = [(lab, unary_union(list(gr.geometry))) for lab, gr in roads.groupby("label")]
        rail = gpd.read_file(conn, layer="rail").to_crs(U)
        rail = rail[rail.distance(b) <= NEAR_M]
        if len(rail):
            items.append(("Railway line", unary_union(list(rail.geometry))))
        for lab, geom in items:
            seg = ring.intersection(geom.buffer(NEAR_M))
            if seg.is_empty or seg.length < MIN_FRONT_M:
                continue
            seg = linemerge(seg) if seg.geom_type == "MultiLineString" else seg
            fronts.append({"label": lab, "m": round(seg.length), "geom": to4326(seg), "_seg": seg})
    # ---- roads without a name in OSM, and roads only the satellite shows ----
    try:
        R, P = _local_osm(site, b4326, ctx.log)
    except Exception as ex:                                       # Overpass down: named frontage still stands
        ctx.log(f"  local roads not fetched ({str(ex)[:80]}) - unnamed road frontage skipped")
        R = P = None
    unnamed = []
    if R is not None:
        R = R.to_crs(U); P = P.to_crs(U)
        R["label"] = [_label(n, r) for n, r in zip(R.name, R.ref)]
        R["label"] = R.label.where(R.label.notna(), None).astype(object)
        lab_of = lambda v: v if isinstance(v, str) else None
        D = _detected(b4326).to_crs(U)
        if len(D) and len(R):                                     # keep only what OSM lacks: under half its length near an OSM way
            osm_buf = unary_union(list(R.geometry)).buffer(12)
            D = D[[g.intersection(osm_buf).length < 0.5 * g.length for g in D.geometry]]
        cand = [(g, "osm") for g, lab, hw in zip(R.geometry, R.label, R.highway) if lab_of(lab) is None and hw in MINOR] + [(g, "sat") for g in D.geometry]
        inner = b.buffer(-NEAR_M)
        # a road that runs through the site is not a frontage (it is reported as a crossing on the maps, not here)
        cand = [(g, s) for g, s in cand if g.distance(b) <= NEAR_M and (inner.is_empty or g.intersection(inner).length < 60)]
        covered = unary_union([f["_seg"].buffer(5) for f in fronts]) if fronts else None
        if cand:
            seg = ring.intersection(unary_union([g for g, _ in cand]).buffer(NEAR_M))
            if covered is not None:
                seg = seg.difference(covered)
            seg = linemerge(seg) if seg.geom_type == "MultiLineString" else seg
            pieces = [g for g in getattr(seg, "geoms", [seg]) if g.geom_type == "LineString" and g.length >= MIN_UNNAMED_M]
            net = [(g, lab_of(lab)) for g, lab in zip(R.geometry, R.label)] + [(g, None) for g in D.geometry]
            named = [(g, lab_of(lab)) for g, lab in zip(R.geometry, R.label) if lab_of(lab)]
            for pc in pieces:
                src = [(g, s) for g, s in cand if g.distance(pc) <= NEAR_M + 5]
                if not src:
                    continue
                main = unary_union([g for g, _ in src]); main = linemerge(main) if main.geom_type == "MultiLineString" else main
                main = max(getattr(main, "geoms", [main]), key=lambda g: g.intersection(pc.buffer(NEAR_M + 5)).length)
                kind = "sat" if sum(g.length for g, s in src if s == "sat") > sum(g.length for g, s in src if s == "osm") else "osm"
                ta, tb = sorted((main.project(Point(pc.coords[0])), main.project(Point(pc.coords[-1]))))
                ends = []
                for t_end, t_far in ((ta, 0.0), (tb, main.length)):
                    near_pt = main.interpolate(t_end)
                    stub = substring(main, t_end, t_far) if abs(t_far - t_end) > 1 else None
                    if stub is not None and stub.length > 1:
                        cs = list(stub.coords); heading = _unit(cs[-2], cs[-1]); start = cs[-1]
                    else:                                         # the frontage runs to the end of the line: head away from the site
                        other = main.interpolate(tb if t_end == ta else ta)
                        heading = _unit((other.x, other.y), (near_pt.x, near_pt.y)); start = (near_pt.x, near_pt.y); cs = [start]
                    more, joined = _trace(start, heading, net, named, TRACE_M)
                    path = LineString(cs + list(more.coords)[1:]) if more is not None and len(cs) > 1 else (more or (LineString(cs) if len(cs) > 1 else None))
                    text = _where(path, joined, P, b)
                    draw = substring(path, 0, min(DRAW_M, path.length)) if path is not None else None
                    tip = path.interpolate(min(250, path.length)) if path is not None else near_pt
                    ends.append({"text": text, "at": to4326(near_pt)["coordinates"], "tip": to4326(tip)["coordinates"],
                                 "draw": to4326(draw) if draw is not None else None})
                short = [x["text"].split(" ", 1)[-1] for x in ends]
                base = "Unnamed road" if kind == "osm" else SAT_LABEL
                unnamed.append({"label": f"{base} ({short[0]} - {short[1]})", "m": round(pc.length), "geom": to4326(pc), "kind": kind,
                                "road": to4326(substring(main, max(0, ta - 50), min(main.length, tb + 50))), "ends": ends, "_seg": pc})
            # one entry per road: pieces of the same road (same two ends) are added up
            merged = {}
            for u in unnamed:
                if u["label"] in merged:
                    m = merged[u["label"]]; m["m"] += u["m"]; m["_seg"] = unary_union([m["_seg"], u["_seg"]]); m["geom"] = to4326(m["_seg"])
                else:
                    merged[u["label"]] = u
            unnamed = list(merged.values())
    fronts = sorted(fronts + unnamed, key=lambda f: -f["m"])
    for f in fronts:
        f.pop("_seg", None)
    if unnamed:                                                   # traced centrelines for checking in QGIS (working file, not a deliverable)
        feats = []
        for u in unnamed:
            feats.append({"type": "Feature", "properties": {"label": u["label"], "part": "road at the site", "frontage_m": u["m"]}, "geometry": u["road"]})
            for x in u["ends"]:
                if x["draw"]:
                    feats.append({"type": "Feature", "properties": {"label": u["label"], "part": x["text"], "frontage_m": u["m"]}, "geometry": x["draw"]})
        import json
        (site.work / "frontage_roads.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    c = b.centroid
    pts4326 = lambda pts: [list(p.coords[0]) for p in gpd.GeoSeries([Point(x, y) for x, y in pts], crs=U).to_crs(4326)]

    # dimension lines through the centroid, parallel to the rectangle sides, clipped to the site
    def through(edge):
        (x1, y1), (x2, y2) = edge; dx, dy = x2 - x1, y2 - y1; n = math.hypot(dx, dy); dx, dy = dx / n, dy / n
        full = LineString([(c.x - dx * 1e5, c.y - dy * 1e5), (c.x + dx * 1e5, c.y + dy * 1e5)])
        inside = full.intersection(b)          # the span across the site itself (an irregular site is shorter than its rectangle)
        parts = [g for g in getattr(inside, "geoms", [inside]) if g.geom_type == "LineString" and not g.is_empty]
        ln = max(parts, key=lambda g: g.length) if parts else full.intersection(mrr)
        return pts4326([ln.coords[0], ln.coords[-1]]), ln.length
    long_line, long_span = through(long_e); short_line, short_span = through(short_e)
    long_m, short_m = L(long_e), L(short_e)
    area_m2, per = b.area, ring.length
    data = {"length_m": round(long_m), "width_m": round(short_m), "long_span_m": round(long_span), "short_span_m": round(short_span), "perimeter_m": round(per), "compactness": round(4 * math.pi * area_m2 / per ** 2, 2),
            "long_line": long_line, "short_line": short_line, "fronts": fronts[:5]}
    db.save_summary(site.site_id, {"dimensions": data})
    return (f"length {long_m / 1000:.2f} km, width {short_m / 1000:.2f} km, perimeter {per / 1000:.2f} km; frontage: "
            + (", ".join(f"{f['label']} {f['m']} m" for f in fronts[:4]) or "none along any road"))

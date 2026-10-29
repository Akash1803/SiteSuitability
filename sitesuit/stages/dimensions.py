"""Stage - boundary dimensions and road / rail frontage, drawn on the existing Boundary slide (no extra slide):
overall length and width (minimum rotated rectangle), perimeter, compactness, and the length of boundary that runs
along each named road or the railway (within 40 m)."""
import math

import geopandas as gpd
from shapely.geometry import LineString, mapping
from shapely.ops import linemerge, unary_union

from .. import db

NAME, TITLE = "dimensions", "Boundary dimensions + frontage"
NEAR_M, MIN_FRONT_M = 40, 50
HW = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified"}


def run(site, ctx):
    U = db.get_summary(site.site_id).get("utm", 32644)
    b = gpd.read_file(site.boundary).to_crs(U).geometry.iloc[0]
    ring = unary_union([p.exterior for p in getattr(b, "geoms", [b])])
    mrr = b.minimum_rotated_rectangle
    xs, ys = mrr.exterior.coords.xy
    e = [((xs[i], ys[i]), (xs[i + 1], ys[i + 1])) for i in range(4)]
    L = lambda s: math.dist(*s)
    long_e = max(e[:2], key=L); short_e = min(e[:2], key=L)
    conn = site.work / "conn.gpkg"
    fronts = []
    if conn.exists():
        roads = gpd.read_file(conn, layer="roads").to_crs(U)
        roads = roads[roads.highway.isin(HW)].copy()
        roads["label"] = [(f"{n} ({r})" if isinstance(n, str) and isinstance(r, str) else (n if isinstance(n, str) else (r if isinstance(r, str) else None)))
                          for n, r in zip(roads.name, roads.ref)]
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
            fronts.append({"label": lab, "m": round(seg.length), "geom": mapping(gpd.GeoSeries([seg], crs=U).to_crs(4326).iloc[0])})
        fronts.sort(key=lambda f: -f["m"])
    to4326 = lambda pts: [list(p.coords[0]) for p in gpd.GeoSeries([gpd.points_from_xy([x], [y])[0] for x, y in pts], crs=U).to_crs(4326)]
    c = b.centroid
    # dimension lines through the centroid, parallel to the rectangle sides, clipped to the site
    def through(edge):
        (x1, y1), (x2, y2) = edge; dx, dy = x2 - x1, y2 - y1; n = math.hypot(dx, dy); dx, dy = dx / n, dy / n
        full = LineString([(c.x - dx * 1e5, c.y - dy * 1e5), (c.x + dx * 1e5, c.y + dy * 1e5)])
        inside = full.intersection(b)          # the span across the site itself (an irregular site is shorter than its rectangle)
        parts = [g for g in getattr(inside, "geoms", [inside]) if g.geom_type == "LineString" and not g.is_empty]
        ln = max(parts, key=lambda g: g.length) if parts else full.intersection(mrr)
        return to4326([ln.coords[0], ln.coords[-1]]), ln.length
    long_line, long_span = through(long_e); short_line, short_span = through(short_e)
    long_m, short_m = L(long_e), L(short_e)
    area_m2, per = b.area, ring.length
    data = {"length_m": round(long_m), "width_m": round(short_m), "long_span_m": round(long_span), "short_span_m": round(short_span), "perimeter_m": round(per), "compactness": round(4 * math.pi * area_m2 / per ** 2, 2),
            "long_line": long_line, "short_line": short_line, "fronts": fronts[:5]}
    db.save_summary(site.site_id, {"dimensions": data})
    return (f"length {long_m / 1000:.2f} km, width {short_m / 1000:.2f} km, perimeter {per / 1000:.2f} km; frontage: "
            + (", ".join(f"{f['label']} {f['m']} m" for f in fronts[:4]) or "none along a named road"))

"""Polygon helpers for giving every A-register subdivision its own polygon (strip cuts by A-register extent)."""
import numpy as np
from shapely.affinity import rotate
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union


def clean(g):
    """keep only polygon parts (None when nothing is left)"""
    if g is None or g.is_empty:
        return None
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    polys = [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon) and p.area > 0.5]
    return None if not polys else (polys[0] if len(polys) == 1 else MultiPolygon(polys))


def _weights(weights):
    w = np.array(weights, dtype=float)
    return np.where(np.isnan(w) | (w <= 0), np.nanmean(w[w > 0]) if (w > 0).any() else 1.0, w)


def strip_split(poly, weights):
    """Cut poly into len(weights) pieces with areas proportional to weights, by lines perpendicular to its longest axis."""
    w = _weights(weights)
    if len(w) == 1:
        return [poly]
    mrr = poly.minimum_rotated_rectangle
    xs, ys = mrr.exterior.coords.xy
    e = [(xs[i], ys[i], xs[i + 1], ys[i + 1]) for i in range(4)]
    L = max(e, key=lambda s: (s[2] - s[0]) ** 2 + (s[3] - s[1]) ** 2)
    ang = np.degrees(np.arctan2(L[3] - L[1], L[2] - L[0]))
    c = poly.centroid
    p = rotate(poly, -ang, origin=c)
    x0, y0, x1, y1 = p.bounds
    targets = np.cumsum(w / w.sum())[:-1] * p.area
    pieces, rest, lo = [], p, x0
    for t in targets:
        a, b = lo, x1
        done = sum(q.area for q in pieces)
        for _ in range(40):
            mid = (a + b) / 2
            if rest.intersection(box(x0 - 1, y0 - 1, mid, y1 + 1)).area < t - done:
                a = mid
            else:
                b = mid
        cut = (a + b) / 2
        piece = clean(rest.intersection(box(x0 - 1, y0 - 1, cut, y1 + 1)))
        rest = clean(rest.difference(box(x0 - 1, y0 - 1, cut, y1 + 1))) or Polygon()
        pieces.append(piece if piece is not None else Polygon())
        lo = cut
    pieces.append(rest)
    return [rotate(q, ang, origin=c) if not q.is_empty else q for q in pieces]


def split_components(region, weights):
    """Split a possibly fragmented region among records without giving one record disconnected pieces."""
    parts = sorted([g for g in getattr(region, "geoms", [region]) if g.area > 0.5], key=lambda g: -g.area)
    w = _weights(weights)
    n = len(w)
    if len(parts) <= 1:
        return strip_split(parts[0] if parts else region, w)
    scale = sum(g.area for g in parts) / w.sum()
    alloc = {i: [] for i in range(len(parts))}
    cap = [g.area for g in parts]
    for i in np.argsort(-w):
        k = max(range(len(parts)), key=lambda j: cap[j])
        alloc[k].append(i); cap[k] -= w[i] * scale
    out = [None] * n
    for k, idxs in alloc.items():
        if idxs:
            for i, g in zip(idxs, strip_split(parts[k], [w[i] for i in idxs])):
                out[i] = g
    for k, idxs in alloc.items():
        if not idxs:
            best = max(range(n), key=lambda i: out[i].boundary.intersection(parts[k].boundary).length if out[i] is not None else -1)
            out[best] = unary_union([out[best], parts[k]])
    return out


def fix_multipart(df, idxs):
    """Within one group of records keep each record's largest part and hand small detached parts to the touching neighbour."""
    for _ in range(3):
        changed = False
        for i in idxs:
            g = df.at[i, "geometry"]
            if g is None or g.geom_type != "MultiPolygon":
                continue
            parts = sorted(g.geoms, key=lambda q: -q.area)
            df.at[i, "geometry"] = parts[0]
            for small in parts[1:]:
                nb = [j for j in idxs if j != i and df.at[j, "geometry"] is not None and df.at[j, "geometry"].intersects(small)]
                if nb:
                    j = max(nb, key=lambda j: df.at[j, "geometry"].boundary.intersection(small.boundary).length)
                    df.at[j, "geometry"] = unary_union([df.at[j, "geometry"], small])
                else:
                    df.at[i, "geometry"] = unary_union([df.at[i, "geometry"], small])
                changed = True
        if not changed:
            break

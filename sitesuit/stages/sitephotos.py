"""Stage - site photos slide: your field / drone photos from 07_PPT_Maps/site_photos, placed on the boundary map from the
GPS position stored in each photo (EXIF). Photos without a position are shown too, without a pointer.
No photos in the folder = no slide."""
from pathlib import Path

from PIL import Image

from .. import db

NAME, TITLE = "sitephotos", "Site photos slide"
EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")
MAX = 8


def _deg(v):
    try:
        d, m, s = (float(x) for x in v)
        return d + m / 60 + s / 3600
    except Exception:
        return None


def gps(path):
    try:
        ex = Image.open(path).getexif()
        g = ex.get_ifd(0x8825)
        if not g or 2 not in g or 4 not in g:
            return None
        lat, lon = _deg(g[2]), _deg(g[4])
        if lat is None or lon is None:
            return None
        if g.get(1) in ("S", b"S"):
            lat = -lat
        if g.get(3) in ("W", b"W"):
            lon = -lon
        return lat, lon
    except Exception:
        return None


def run(site, ctx):
    folder = site.maps_dir / "site_photos"; folder.mkdir(exist_ok=True)
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in EXT)[:MAX]
    photos = [{"n": i, "file": str(p), "name": p.stem, "pos": gps(p)} for i, p in enumerate(files, 1)]
    db.save_summary(site.site_id, {"sitephotos": {"photos": photos}})
    if not photos:
        return f"no photos in {folder} - the slide is left out (add field / drone photos with GPS and run again)"
    located = sum(1 for p in photos if p["pos"])
    return f"{len(photos)} photos, {located} with a GPS position" + ("" if located == len(photos) else f"; {len(photos) - located} shown without a pointer")

"""Stage - executive summary slide (placed after the title): the site's key numbers from every finished stage on one slide."""
from .. import db

NAME, TITLE = "summary", "Executive summary slide"


def run(site, ctx):
    s = db.get_summary(site.site_id)
    m = s.get("master", {})
    if not m:
        raise RuntimeError("run the master stage first")
    return f"summary of {m['site_acre']:.2f} ac ready (built into the PPT)"

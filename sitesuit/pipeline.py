"""Runs the stages in order, records status in site.stage_run, resumes where it stopped."""
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from . import db
from .config import SETTINGS
from .site import Site, slug
from .stages import STAGES, BY_NAME

REVIEW_AFTER = ("areg",)      # the app pauses here so the user checks the A-register before GLV / costs


@dataclass
class Ctx:
    options: dict = field(default_factory=dict)
    log: callable = print
    progress_cb: callable = None
    stop_flag: callable = None

    def progress(self, i, n, msg=""):
        if self.progress_cb:
            self.progress_cb(i, n, msg)
        elif msg and (i == n or i % 25 == 0):
            self.log(f"  {i}/{n} {msg}")

    def stopped(self):
        return bool(self.stop_flag and self.stop_flag())


def open_site(name, project_dir=None):
    known = {n: (i, d) for i, n, d, _ in db.list_sites()}
    if project_dir:
        root = Path(project_dir)
    elif name in known:
        root = Path(known[name][1])
    else:
        root = SETTINGS.projects_root / slug(name)
    s = Site(name, root)
    s.site_id = known.get(name, (None,))[0]
    return s


def run(site, stages=None, ctx=None, force=False, pause_at_review=False):
    """stages: list of stage names (default all). Stages already 'done' are skipped unless force. Returns the last status."""
    ctx = ctx or Ctx()
    names = stages or [s.NAME for s in STAGES]
    for nm in names:
        st = BY_NAME[nm]
        if site.site_id is None and nm != "parcels":
            raise RuntimeError("run the parcels stage first (it registers the site)")
        if site.site_id and not force and db.stage_status(site.site_id).get(nm, ("",))[0] == "done":
            ctx.log(f"[{nm}] already done - skipped"); continue
        if ctx.stopped():
            return "stopped"
        ctx.log(f"[{nm}] {st.TITLE} ...")
        if site.site_id:
            db.set_stage(site.site_id, nm, "running")
        try:
            msg = st.run(site, ctx)
            db.set_stage(site.site_id, nm, "done", msg); ctx.log(f"[{nm}] done - {msg}")
        except Exception as e:
            kind = type(e).__name__
            status = "waiting" if kind in ("Waiting", "NeedsReview") else "failed"
            if site.site_id:
                db.set_stage(site.site_id, nm, status, str(e)[:1000])
            ctx.log(f"[{nm}] {status.upper()} - {e}")
            if status == "failed":
                ctx.log(traceback.format_exc(limit=4))
            return status
        if pause_at_review and nm in REVIEW_AFTER and nm != names[-1]:
            ctx.log(f"[{nm}] review point - check the A-register Excel, then continue")
            return "review"
    return "done"

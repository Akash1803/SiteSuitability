"""Runs the stages in order, records status in site.stage_run, resumes where it stopped."""
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from . import db
from .config import SETTINGS
from .site import Site, slug
from .stages import STAGES, BY_NAME

REVIEW_AFTER = ("areg",)     # the app pauses here so the user checks the A-register before GLV / costs
NON_BLOCKING = ("crop",)     # a missing crop workbook does not stop the cost, maps and PPT


@dataclass
class Ctx:
    options: dict = field(default_factory=dict)
    log: callable = print
    progress_cb: callable = None
    stop_flag: callable = None
    selected: callable = None      # current tick selection (set by run)
    include: callable = None       # stages whose results go into the outputs (default = the selection)

    def is_on(self, stage):
        """stage ticked (an unticked stage is also left out of the master Excel / PPT)"""
        f = self.include or self.selected
        return f is None or stage in f()

    def progress(self, i, n, msg=""):
        if self.progress_cb:
            self.progress_cb(i, n, msg)
        elif msg and (i == n or i % 25 == 0):
            self.log(f"  {i}/{n} {msg}")

    def stopped(self):
        return bool(self.stop_flag and self.stop_flag())


# inputs each stage needs (crop is optional for the PPT: without it the crop slide shows "No Survey Data")
REQUIRES = {"clip": ("parcels",), "areg": ("clip",), "glv": ("parcels",), "master": ("areg",), "crop": ("master",),
            "landcost": ("master", "glv"), "fmb": ("parcels",), "maps": ("master",), "streetview": ("maps",), "soil": ("master", "maps"), "sensitive": ("master", "maps"), "govtland": ("master", "maps"), "ppt": ("master",)}
# what goes stale when a stage re-runs (optional inputs included)
USES = {**REQUIRES, "master": ("areg", "glv"), "maps": ("master", "crop"), "govtland": ("master", "maps", "soil"), "ppt": ("master", "landcost", "maps", "crop", "streetview", "soil", "sensitive", "govtland")}


def dependents(stage):
    out, todo = set(), [stage]
    while todo:
        s = todo.pop()
        for k, v in USES.items():
            if s in v and k not in out:
                out.add(k); todo.append(k)
    return out


def reset_after(sid, stage):
    later = sorted(dependents(stage))
    with db.connect() as c:
        c.execute("UPDATE site.stage_run SET status = 'pending', message = %s WHERE site_id = %s AND stage = ANY(%s) AND status <> 'pending'",
                  (f"to run again after '{stage}' was re-run", sid, later))


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
    """stages: list of stage names, or a callable returning the CURRENT selection (re-read before every stage, so the user
    can tick / untick while a run is going). Done stages are skipped unless force. Unticked stages are left out, and a stage
    whose required input stage is neither done nor about to run is left out too. Returns the last status."""
    ctx = ctx or Ctx()
    selected = stages if callable(stages) else (lambda s=list(stages or [x.NAME for x in STAGES]): s)
    ctx.selected = selected
    for st in STAGES:
        nm = st.NAME
        chosen = selected()
        if nm not in chosen:
            continue
        if ctx.stopped():
            return "stopped"
        if site.site_id is None and nm != "parcels":
            raise RuntimeError("run the parcels stage first (it registers the site)")
        status_now = db.stage_status(site.site_id) if site.site_id else {}
        if not force and status_now.get(nm, ("",))[0] == "done":
            if hasattr(st, "stale") and st.stale(site, ctx):
                ctx.log(f"[{nm}] ticks changed since it was built - building it again")
            else:
                ctx.log(f"[{nm}] already done - skipped"); continue
        missing = [d for d in REQUIRES.get(nm, ()) if status_now.get(d, ("",))[0] != "done"]
        if missing:
            ctx.log(f"[{nm}] left out - it needs {', '.join(BY_NAME[d].TITLE for d in missing)} first")
            continue
        ctx.log(f"[{nm}] {st.TITLE} ...")
        if site.site_id:
            db.set_stage(site.site_id, nm, "running")
        try:
            msg = st.run(site, ctx)
            db.set_stage(site.site_id, nm, "done", msg); ctx.log(f"[{nm}] done - {msg}")
            reset_after(site.site_id, nm)   # everything that uses this stage's new output must be rebuilt
        except Exception as e:
            kind = type(e).__name__
            status = "waiting" if kind in ("Waiting", "NeedsReview") else "failed"
            if site.site_id:
                db.set_stage(site.site_id, nm, status, str(e)[:1000])
                if status == "failed":
                    reset_after(site.site_id, nm)
            ctx.log(f"[{nm}] {status.upper()} - {e}")
            if status == "failed":
                ctx.log(traceback.format_exc(limit=4))
            if status == "waiting" and nm in NON_BLOCKING:
                ctx.log(f"[{nm}] continuing with the other stages; run it again when its input is ready"); continue
            return status
        later = [x.NAME for x in STAGES][[x.NAME for x in STAGES].index(nm) + 1:]
        if pause_at_review and nm in REVIEW_AFTER and any(x in selected() for x in later):
            ctx.log(f"[{nm}] review point - check the A-register Excel, then continue")
            return "review"
    return "done"

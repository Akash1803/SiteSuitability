"""Stage 8 - latest FMB sketches (collabland FMB portal) for every survey, via the team's FMB downloader script.
Saved as 09_FMB_Latest/<vcode>/<survey>/<survey>.pdf. Already-downloaded sheets are skipped."""
import csv
import subprocess
import sys

import geopandas as gpd
import pandas as pd

from .. import db
from ..config import SETTINGS
from ..util import split_vcode

NAME, TITLE = "fmb", "Latest FMB sheets"


def run(site, ctx):
    sv = gpd.read_file(site.parcels); sv["survey_no"] = sv.survey_no.astype(str)
    keys = sorted({(v, s) for v, s in zip(sv.village_code, sv.survey_no)})
    todo = [(v, s) for v, s in keys if not (site.fmb_dir / v / s / f"{s}.pdf").exists()]
    ctx.log(f"FMB sheets: {len(keys)} surveys, {len(keys) - len(todo)} already downloaded, {len(todo)} to fetch")
    if todo:
        if not SETTINGS.fmb_downloader.exists():
            raise RuntimeError(f"FMB downloader not found: {SETTINGS.fmb_downloader} (set FMB_DOWNLOADER in .env)")
        inp = site.fmb_dir / "FMB_Download_Input.xlsx"
        pd.DataFrame([{"district_id": v.split("_")[0], "taluk_id": v.split("_")[1], "village_id": v.split("_")[2], "survey_no": s} for v, s in todo]).to_excel(inp, index=False)
        cmd = [sys.executable, "-u", str(SETTINGS.fmb_downloader), "--mode", "excel", "--input", str(inp), "--output", str(site.fmb_dir),
               "--download-empty", "True", "--auto-explore", "False", "--delay", "1"]
        if SETTINGS.fmb_cookie:
            cmd += ["--cookie", SETTINGS.fmb_cookie]
        p = subprocess.Popen(cmd, cwd=str(site.fmb_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                             env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        n = 0
        for line in p.stdout:
            if ctx.stopped():
                p.kill(); raise RuntimeError("stopped by user")
            if "saved" in line or "error" in line.lower():
                n += 1; ctx.progress(min(n, len(todo)), len(todo), line.strip()[:120])
        p.wait()
    got = [(v, s) for v, s in keys if (site.fmb_dir / v / s / f"{s}.pdf").exists()]
    errs = []
    log = site.fmb_dir / "download_log.csv"
    if log.exists():
        with open(log, encoding="utf-8", errors="replace") as f:
            errs = [r for r in csv.DictReader(f) if r.get("status") == "error"]
    missing = [f"{v} {s}" for v, s in keys if (v, s) not in set(got)]
    db.save_summary(site.site_id, {"fmb_sheets": {"downloaded": len(got), "missing": missing}})
    for v, s in got:
        db.register_document(site.site_id, "fmb_sheet", site.fmb_dir / v / s / f"{s}.pdf")
    note = "; ".join(sorted({(e.get("api_error") or e.get("message") or "")[:60] for e in errs})) if errs else ""
    return f"{len(got)} of {len(keys)} sheets" + (f"; not available: {', '.join(missing[:8])} ({note})" if missing else "")

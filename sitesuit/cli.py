"""Command line.
  python -m sitesuit.cli init-db                         create schemas + load TN revenue villages
  python -m sitesuit.cli run <site> --boundary <file> [--stages parcels,clip,...] [--force] [--dir <project dir>]
  python -m sitesuit.cli status <site>
  python -m sitesuit.cli load-crop <workbook.xlsx>       add a crop-survey workbook to the statewide crop table
  python -m sitesuit.cli seed-cache <project dir>        import an earlier site's CLIP / A-register / GLV outputs into the cache
  python -m sitesuit.cli pdf <site>                      PDF of the PPT (only after it is confirmed)"""
import argparse
import glob
import sys

from . import db, loaders, pipeline


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sitesuit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    r = sub.add_parser("run"); r.add_argument("site"); r.add_argument("--boundary"); r.add_argument("--stages"); r.add_argument("--force", action="store_true")
    r.add_argument("--dir"); r.add_argument("--show-browser", action="store_true")
    s = sub.add_parser("status"); s.add_argument("site")
    c = sub.add_parser("load-crop"); c.add_argument("workbook")
    k = sub.add_parser("seed-cache"); k.add_argument("project_dir")
    p = sub.add_parser("pdf"); p.add_argument("site")
    a = ap.parse_args(argv)
    if a.cmd == "init-db":
        db.init_schema(); loaders.load_revenue_villages(); return
    if a.cmd == "run":
        site = pipeline.open_site(a.site, a.dir)
        opts = {"boundary_file": a.boundary, "show_browser": a.show_browser}
        stages = a.stages.split(",") if a.stages else None
        if (stages is None or "parcels" in stages) and not a.boundary:
            sys.exit("--boundary is needed for the parcels stage")
        print(pipeline.run(site, stages, pipeline.Ctx(options=opts), force=a.force)); return
    if a.cmd == "status":
        sid = db.site_id(a.site)
        for k_, (st, m) in db.stage_status(sid).items():
            print(f"{k_:10s} {st:8s} {m or ''}")
        return
    if a.cmd == "load-crop":
        print(loaders.load_crop_workbook(a.workbook)); return
    if a.cmd == "seed-cache":
        for f in glob.glob(a.project_dir + "/03_CLIP/Clip_Output*.xlsx"):
            loaders.import_clip_output(f)
        for f in glob.glob(a.project_dir + "/04_Tamilnilam/Tamilnilam_Raw*.xlsx") + glob.glob(a.project_dir + "/04_Tamilnilam/Tamilnilam_AReg*_raw.xlsx"):
            loaders.import_areg_raw(f)
        for f in glob.glob(a.project_dir + "/05_GLV/GLV_Output*.xlsx"):
            loaders.import_glv_output(f)
        return
    if a.cmd == "pdf":
        from .stages.ppt import export_pdf
        print(export_pdf(pipeline.open_site(a.site)))


if __name__ == "__main__":
    main()

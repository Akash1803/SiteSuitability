"""Stage 6 - crop survey. Reads crop.survey_record (statewide table) for the site's LGD villages; a teammate's workbook dropped in
06_Crop (*crop_survey_data*.xlsx) is loaded into the table first. With no crop data yet, it writes the crop input file and waits."""
import glob

import geopandas as gpd
import pandas as pd

from .. import db, loaders
from ..util import child_of

NAME, TITLE = "crop", "Crop data"
CULT = {"Seasonal", "Perennial", "Annual"}


class Waiting(Exception):
    pass


def write_input(site, summ):
    sv = gpd.read_file(site.parcels); sv["survey_no"] = sv.survey_no.astype(str)
    lgd = {v["vcode"]: v["lgd"] for v in summ.get("villages", [])}
    s = sv.groupby(["village_code", "village", "taluk", "district", "survey_no"], as_index=False).agg(puvi_acre=("puvi_acre", "sum"), inside_acre=("inside_acre", "sum"), split=("split", "max"))
    s["lgd_village_code"] = s.village_code.map(lgd)
    s["parcel_status"] = s.split.map({True: "Split by boundary (inside part only)", False: "Full parcel"})
    sm = pd.read_excel(site.master, sheet_name="Subdivision_Master", dtype=str)
    sd = sm[sm.in_site.str.lower() == "true"][["village", "survey_no", "subdiv_no", "unique_id"]]
    with pd.ExcelWriter(site.crop_input, engine="openpyxl") as w:
        s.drop(columns="split").to_excel(w, sheet_name="Survey_Level", index=False); sd.to_excel(w, sheet_name="Subdivision_Level", index=False)
        s.drop_duplicates("village_code")[["district", "taluk", "village", "village_code", "lgd_village_code"]].to_excel(w, sheet_name="Village_IDs", index=False)


def run(site, ctx):
    summ = db.get_summary(site.site_id)
    lgd = {v["vcode"]: str(v["lgd"]) for v in summ.get("villages", []) if v.get("lgd")}
    for f in sorted(glob.glob(str(site.root / "06_Crop" / "*crop_survey_data*.xlsx"))):
        ctx.log(f"loading crop workbook {f}"); loaders.load_crop_workbook(f, ctx.log)
    with db.connect() as c:
        rows = c.execute("""SELECT season, crop_survey_id, lgd_village_code, survey_number, coalesce(sub_division_number, '-'), crop_season_type_name, crop_name, crop_area_acres
                            FROM crop.survey_record WHERE lgd_village_code = ANY(%s)""", (list(lgd.values()),)).fetchall()
    if not rows:
        write_input(site, summ)
        db.register_document(site.site_id, "crop_input", site.crop_input)
        raise Waiting(f"no crop data for these villages yet - send {site.crop_input.name} to the crop team, put their workbook in 06_Crop and run this stage again")
    inv = {v: k for k, v in lgd.items()}
    sheets = pd.read_excel(site.master, sheet_name=None)
    sm = sheets["Subdivision_Master"]; sm["survey_no"] = sm.survey_no.astype(str); sm["subdiv_no"] = sm.subdiv_no.astype(str)
    sm["vc"] = sm.unique_id.str[:9]
    subs_of = sm.groupby(["vc", "survey_no"]).subdiv_no.apply(list).to_dict()

    def targets(vc, sn, sd):
        subs = subs_of.get((vc, sn), [])
        if sd in subs: return [sd], "Exact"
        if sd in ("-", "") and subs: return subs, "Crop row for the whole survey - applied to all its A-reg subdivisions"
        kids = [s for s in subs if child_of(s, sd)]
        if kids: return kids, "Crop subdivision coarser - applied to its A-reg children"
        pars = [s for s in subs if child_of(sd, s)]
        if pars: return [max(pars, key=len)], "Crop subdivision finer - rolled up to its A-reg parent"
        return [], "No A-reg match"
    att, um = [], []
    seasons = sorted({r[0] for r in rows})
    for season, cid, l, sn, sd, typ, name, area in rows:
        vc = inv.get(l); sn = (sn or "").strip(); sd = (sd or "-").strip() or "-"
        tg, how = targets(vc, sn, sd)
        if not tg:
            um.append({"season": season, "village_code": vc, "survey_no": sn, "sub_division": sd, "crop_survey_id": cid, "type": typ, "crop": name, "crop_area_acres": area}); continue
        for t in tg:
            att.append({"unique_id": f"{vc}_{sn}/{t}", "season": season, "match": how, "crop_subdivision": f"{sn}/{sd}", "crop_survey_id": cid,
                        "crop_season_type_name": typ, "crop_name": name, "crop_area_acres": area or 0.0})
    cr = pd.DataFrame(att); um = pd.DataFrame(um)
    tag = {s: "s" + "".join(ch for ch in s.lower() if ch.isalnum()) for s in seasons}
    grp = dict(tuple(cr.groupby("unique_id"))) if len(cr) else {}
    out = []
    for u in sm.unique_id:
        rec = {"unique_id": u}; ga = grp.get(u, cr.iloc[0:0] if len(cr) else pd.DataFrame(columns=["season", "crop_season_type_name", "crop_name", "crop_area_acres", "match"]))
        sts, crops = [], set()
        for s in seasons:
            g = ga[ga.season == s]; t = tag[s]
            if len(g):
                types = set(g.crop_season_type_name.dropna()); cult = g[g.crop_season_type_name.isin(CULT)]
                st = "Cultivated" if types & CULT else ("Fallow" if "Fallow" in types else ("Non-Agricultural" if "Non-Agricultural" in types else "Recorded, type blank"))
                cs = sorted(set(cult.crop_name.dropna())); crops |= set(cs)
                rec.update({f"{t}_status": st, f"{t}_crops": ", ".join(cs), f"{t}_crop_area_ac": round(cult.crop_area_acres.sum(), 4)})
            else:
                st = "No crop survey"; rec.update({f"{t}_status": st, f"{t}_crops": "", f"{t}_crop_area_ac": 0.0})
            sts.append(st)
        rec["crop_status"] = ("Cultivated (" + ", ".join(sorted(crops)) + ")" if "Cultivated" in sts else "Fallow (no crop in surveyed seasons)" if "Fallow" in sts else
                              "Non-Agricultural (crop survey)" if "Non-Agricultural" in sts else "Recorded, type blank" if any(x != "No crop survey" for x in sts) else "No crop survey record")
        rec["crop_group"] = rec["crop_status"].split(" (")[0]; rec["crops_all_seasons"] = ", ".join(sorted(crops))
        out.append(rec)
    cs = pd.DataFrame(out)
    old = [c for c in sm.columns if c.startswith("s") and c.endswith(("_status", "_crops", "_crop_area_ac")) and c != "areg_status"] + [c for c in ("crop_status", "crop_group", "crops_all_seasons") if c in sm.columns]
    sm = sm.drop(columns=old + ["vc"]).merge(cs, on="unique_id", how="left")
    ins = sm[sm.in_site.astype(str).str.lower() == "true"]
    res = ins.groupby("crop_group").agg(subdivisions=("unique_id", "size"), site_acre=("site_acre", "sum")).round(2).reset_index().sort_values("site_acre", ascending=False)
    res["share_pct"] = (res.site_acre / res.site_acre.sum() * 100).round(2)
    crops_t = cr[cr.crop_season_type_name.isin(CULT)].drop_duplicates(["season", "crop_survey_id"]).groupby(["crop_name", "season"]).agg(entries=("crop_survey_id", "size"), crop_area_ac=("crop_area_acres", "sum")).round(2).reset_index() if len(cr) else pd.DataFrame()
    va = ins.pivot_table(index="village", columns="crop_group", values="site_acre", aggfunc="sum", fill_value=0).round(2).reset_index()
    cult = ins[ins.crop_group == "Cultivated"]
    txt = (f"Cultivated {cult.site_acre.sum():.2f} ac ({cult.site_acre.sum() / max(ins.site_acre.sum(), 1e-9) * 100:.2f}%) in {len(cult)} subdivisions; "
           + ", ".join(f"{r.crop_group} {r.site_acre:.2f} ac" for r in res.itertuples() if r.crop_group != "Cultivated")
           + "; crops: " + ", ".join(sorted(set(c for x in cult.crops_all_seasons for c in str(x).split(", ") if c and c != "nan"))) + f" (seasons: {', '.join(seasons)})")
    cons = sheets["Consolidated_Result"]; cons.loc[cons.Item == "Crop data", "Value"] = txt
    sheets.update({"Consolidated_Result": cons, "Subdivision_Master": sm, "Crop_Status_Summary": res, "Crop_Village": va, "Crops_Grown": crops_t, "Crop_Entries": cr, "Crop_Unmatched": um})
    with pd.ExcelWriter(site.master, engine="openpyxl") as w:
        for n, d in sheets.items():
            d.to_excel(w, sheet_name=n, index=False)
    g = gpd.read_file(site.subdivisions)
    g = g.drop(columns=[c for c in g.columns if c in cs.columns and c != "unique_id"]).merge(cs, on="unique_id", how="left")
    from .master import write_geojson
    write_geojson(g[[c for c in g.columns if c != "geometry"] + ["geometry"]], site.subdivisions)
    db.save_parcels(site.site_id, g)
    cg = res.set_index("crop_group").site_acre
    total = float(ins.site_acre.sum())
    data = {"crop_acre": float(cg.get("Cultivated", 0)), "no_survey_acre": float(cg.get("No crop survey record", 0))}
    data["noncrop_acre"] = total - data["crop_acre"] - data["no_survey_acre"]; data["seasons"] = seasons
    db.save_summary(site.site_id, {"crop": data})
    return f"{len(cr)} crop entries attached ({len(um)} unmatched); crop {data['crop_acre']:.2f} ac, non-crop {data['noncrop_acre']:.2f}, no survey {data['no_survey_acre']:.2f}"

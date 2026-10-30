"""Summary slides (3240 x 2250 PNG) in the look of the SIPCOT preliminary-analysis deck, built as HTML and screenshotted with headless Chrome.
Usage: python -m sitesuit.slides_html <dir with data.json and map_*.png>"""
import json
import os
import sys
import time

D = sys.argv[1]
d = json.load(open(f"{D}/data.json", encoding="utf-8"))
A = d["total"]
f2 = lambda v: f"{v:,.2f}"
pct = lambda v: f"{v:.2f}%"
dash = lambda v: f2(v) if v and v > 0 else "-"

BASE = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Noto+Sans+Tamil:wght@400;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:3240px;height:2250px;background:#fff;font-family:Arial,"Liberation Sans","Noto Sans Tamil",sans-serif;color:#222;overflow:hidden}
.slide{position:relative;width:3240px;height:2250px;padding:50px 65px 50px 65px}
.title{height:190px;background:#0f3b5a;color:#ffff00;font-weight:700;font-size:102px;text-align:center;line-height:190px;letter-spacing:1px}
.title.navy{background:#0b2e6b;color:#fff;font-size:96px}
.body{display:flex;gap:30px;margin-top:40px;height:1560px}
.map{width:2120px;height:1555px;border:3px solid #cfd8e3;overflow:hidden;background:#000}
.map img{width:100%;height:100%;object-fit:cover;display:block}
.panel{flex:1;border:3px solid #cfd8e3;background:#fff;display:flex;flex-direction:column}
.panel h3{background:#0f3b5a;color:#fff;font-size:50px;font-weight:700;padding:34px 50px;line-height:1.1}
.cov{display:flex;height:320px;margin-top:38px;border:3px solid #cfd8e3}
.cov .lab{width:650px;background:#0f3b5a;color:#fff;font-size:52px;font-weight:700;text-align:center;display:flex;align-items:center;justify-content:center;line-height:1.2}
.cov .stats{flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 60px}
.cov .row{display:flex;justify-content:space-between}
.cov .big{font-size:72px;font-weight:700;color:#0f3b5a;line-height:1}
.cov .big small{font-size:36px;color:#555;font-weight:700}
.cov .sub{font-size:36px;color:#555;font-weight:700;margin-top:10px}
.bar{display:flex;height:46px;margin-top:30px;border-radius:8px;overflow:hidden}
.bar div{height:100%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:30px}
</style></head><body><div class="slide">"""
END = "</div></body></html>"


def shot(html, name):
    open(f"{D}/{name}.html", "w", encoding="utf-8").write(html)


# ---------------- 1. LAND SUMMARY ----------------
def tbl(title, head, rows, total, base_total):
    h = f'<div class="sec">{title}</div><table><tr><th style="width:190px">S. No.</th><th>{head}</th><th style="width:520px">Area (Acres)</th><th style="width:470px">Percentage (%)</th></tr>'
    for i, (name, v) in enumerate(rows, 1):
        h += f'<tr><td class="c">{i}</td><td>{name}</td><td class="c">{f2(v["total"])}</td><td class="c">{pct(v["total"] / base_total * 100)}</td></tr>'
    h += f'<tr class="tot"><td colspan="2" class="c">TOTAL</td><td class="c">{f2(total)}</td><td class="c">100.00%</td></tr></table>'
    return h


def dc_land_html(x):
    def t(title, head, rows, total):
        h = (f'<div class="sec">{title}</div><table><tr><th rowspan="2" style="width:190px">S. No.</th><th rowspan="2">{head}</th><th colspan="3">Area (Acres)</th>'
             '<th rowspan="2" style="width:470px">Percentage (%)</th></tr><tr><th class="sub">Non-DC Land</th><th class="sub">DC Land</th><th class="sub">Total</th></tr>')
        for i, (name, v) in enumerate(rows, 1):
            tam = ' class="tam"' if any("஀" <= ch <= "௿" for ch in name) else ""
            h += (f'<tr><td class="c">{i}</td><td{tam}>{name}</td><td class="c">{dash(v["non_dc"])}</td><td class="c dc">{dash(v["dc"])}</td>'
                  f'<td class="c">{f2(v["total"])}</td><td class="c">{pct(v["pct"])}</td></tr>')
        return h + (f'<tr class="tot"><td colspan="2" class="c">TOTAL</td><td class="c">{f2(total["non_dc"])}</td><td class="c dc">{f2(total["dc"])}</td>'
                    f'<td class="c">{f2(total["total"])}</td><td class="c">100.00%</td></tr></table>')
    css = """<style>
.sec{background:#0b2e6b;color:#fff;font-size:46px;font-weight:700;text-align:center;padding:20px 0;margin-top:24px}
table{width:100%;border-collapse:collapse;font-size:40px}
th{background:#0b2e6b;color:#fff;font-weight:700;padding:15px 10px;border:2px solid #fff}
th.sub{background:#2f5aa6;font-size:36px}
td{padding:13px 32px;border:2px solid #d6dde8;background:#fff}
td.c{text-align:center}
td.dc{background:#fff2cc}
tr.tot td{background:#dfe9f8;color:#1a1ae6;font-weight:700}
tr.tot td.dc{background:#ffe08a}
td.tam{font-family:"Noto Sans Tamil",Arial,sans-serif;font-size:31px;line-height:1.25}
</style>"""
    h = BASE + css + '<div class="title navy">LAND SUMMARY</div>'
    h += t("OWNERSHIP CLASSIFICATION (ACRES)", "Ownership Classification", x["own"], x["total"])
    h += t("LAND CLASSIFICATION (ACRES)", "Land Classification", x["lclass"], x["total"])
    if x["rem"]:
        h += t("PORAMBOKE LAND REMARKS (ACRES)", "Remarks", x["rem"], x["gov_total"])
    return h


own_rows = list(d["own"].items())
cls_rows = list(d["lclass"].items())
rem_rows = list(d["rem"].items())
css1 = """<style>
.sec{background:#0b2e6b;color:#fff;font-size:46px;font-weight:700;text-align:center;padding:20px 0;margin-top:24px}
table{width:100%;border-collapse:collapse;font-size:40px}
th{background:#0b2e6b;color:#fff;font-weight:700;padding:15px 10px;border:2px solid #fff}
th.sub{background:#2f5aa6;font-size:36px}
td{padding:13px 32px;border:2px solid #d6dde8;background:#fff}
td.c{text-align:center}
td.dc{background:#fff2cc}
tr.tot td{background:#dfe9f8;color:#1a1ae6;font-weight:700}
tr.tot td.dc{background:#ffe08a}
td.tam{font-family:"Noto Sans Tamil",Arial,sans-serif;font-size:31px;line-height:1.25}
.foot{margin-top:26px;font-size:32px;color:#555;text-align:center}
</style>"""
ab = d["abstract"]; GT_, PT_ = ab["govt_types"], ab["patta_types"]
UNK_ = ab["total"].get("unknown", 0) > 0     # a column only when some surveys have no A-register record
css1b = """<style>.abs th,.abs td{font-size:42px;padding:22px 12px;text-align:center}.abs td.v{text-align:left;padding-left:30px}
.abs th.g{background:#1e6e36}.abs th.p{background:#1d53a8}.pies{display:flex;gap:60px;justify-content:center;margin-top:60px}
.pie{width:1480px;border:3px solid #d6dde8;padding:36px 40px;display:flex;align-items:center;gap:50px}
.pie h4{font-size:48px;color:#0b2e6b;margin-bottom:20px}.pie .lg{font-size:40px;line-height:1.7;color:#333}</style>"""
html = BASE + css1 + css1b + '<div class="title navy">LAND ABSTRACT</div><div class="sec">OVERALL AREA SUMMARY (ACRES)</div><table class="abs">'
html += f'<tr><th rowspan="2">Village</th><th class="g" colspan="{len(GT_) + 1}">Government Land</th><th class="p" colspan="{len(PT_) + 1}">Patta Land</th>' + ('<th rowspan="2">No A-reg record</th>' if UNK_ else '') + '<th rowspan="2">TOTAL</th></tr><tr>'
html += "".join(f'<th class="g sub">{t}</th>' for t in GT_) + '<th class="g sub">Total Govt</th>' + "".join(f'<th class="p sub">{t}</th>' for t in PT_) + '<th class="p sub">Total Patta</th></tr>'
for r in ab["rows"] + [ab["total"]]:
    tot = r is ab["total"]
    html += f'<tr{" class=tot" if tot else ""}><td class="v">{r["village"]}</td>' + "".join(f'<td>{dash(r["govt"].get(t, 0))}</td>' for t in GT_) + f'<td><b>{f2(sum(r["govt"].values()))}</b></td>'
    un = r.get("unknown", 0)
    html += "".join(f'<td>{dash(r["patta"].get(t, 0))}</td>' for t in PT_) + f'<td><b>{f2(sum(r["patta"].values()))}</b></td>'
    html += (f'<td>{dash(un)}</td>' if UNK_ else '') + f'<td><b>{f2(sum(r["govt"].values()) + sum(r["patta"].values()) + un)}</b></td></tr>'
html += '</table>'
def _pie(parts, title):
    tot = sum(v for _, _, v in parts) or 1; stops, acc = [], 0
    for c, _, v in parts:
        a = v / tot * 100; stops.append(f"{c} {acc:.2f}% {acc + a:.2f}%"); acc += a
    lg = "".join(f'<div><span style="display:inline-block;width:30px;height:30px;background:{c};margin-right:16px;vertical-align:middle"></span>{n}: <b>{f2(v)}</b> ac ({v / tot * 100:.2f}%)</div>' for c, n, v in parts)
    return (f'<div class="pie"><div style="width:480px;height:480px;border-radius:50%;background:conic-gradient({",".join(stops)});flex:none"></div>'
            f'<div><h4>{title}</h4><div class="lg">{lg}</div></div></div>')
PC = ["#1d53a8", "#64b5f6", "#ff9800", "#9575cd"]
html += '<div class="pies">' + _pie([("#1d53a8", "Patta Land", d["patta_total"]), ("#81c784", "Government Land", d["gov_total"])]
                                    + ([("#9e9e9e", "No A-register record", d["unknown_total"])] if d.get("unknown_total") else []), f"Land distribution (total {f2(A)} acres)")
if len(PT_) > 1:
    html += _pie([(PC[k % len(PC)], t, ab["total"]["patta"].get(t, 0)) for k, t in enumerate(PT_)], f"Patta land type (total {f2(d['patta_total'])} acres)") + '</div>'
else:   # one patta type only: show the land classification of the whole site instead
    html += _pie([(PC[k % len(PC)], n.split(" (")[0], v["total"]) for k, (n, v) in enumerate(d["lclass"].items())], f"Land classification (total {f2(A)} acres)") + '</div>'
_sp = d.get("split_surveys", 0)
html += f'<div class="foot">Area = A-register extent' + (f'; {_sp} split edge survey{"s are" if _sp != 1 else " is"} counted at the area inside the boundary' if _sp else '') + '.</div>'
if d.get("dc_land"):   # the site has a DC-land list: the land summary is the Non-DC / DC / Total tables (as the Perungalathur deck)
    html = dc_land_html(d["dc_land"])
shot(html + END, "s06_land_summary")

# ---------------- 2. GLV SUMMARY ----------------
GLV_STYLE = {"dc": ("#f6d3ad", "#7a3a00", "#fbe4cc", "#fff8f0", "#f9dfc1", "#f0b67a"),        # header, text, sub-header, cell, total, bar
             "nd": ("#d8ccf1", "#4a2a8e", "#e8e0f8", "#f8f5fe", "#e3d9f6", "#b9a5e6"),
             "st": ("#c9dbf5", "#173f8a", "#e1ebf9", "#f7faff", "#d5e3f7", "#7fa6e0")}


def dc_glv_html(x, A):
    """GLV summary split into DC land / Non-DC land (only when the user gave a DC-land list)"""
    foot = f'DC land: {x["surveys_text"]} ({x["n_surveys"]} surveys)'
    return glv_cards_html(x["split"], x["units"], [("dc", "DC LAND", "dc"), ("non_dc", "NON-DC LAND", "nd")], foot, "GLV SUMMARY – DC LAND vs NON-DC LAND")


def glv_cards_html(sp, units, groups, foot_extra, title):
    """THE GLV summary template (Akash, 30-Oct-2026) for every site: GLV unit card + one card per condition, each column group
    (DC / Non-DC, or the whole site) with area, compensation as per Act / by negotiation and cost-per-acre boxes"""
    cr = lambda v: f2(v / 1e7)
    lk = lambda v: f2(v / 1e5)
    css = """<style>
html,body{font-family:Poppins,Arial,sans-serif}
.slide{padding:44px 60px}
.ttl{height:150px;border-radius:30px;background:#1d4ea0;color:#fff;font-size:84px;font-weight:700;display:flex;align-items:center;justify-content:center;gap:44px}
.ttl .dot{width:22px;height:22px;border-radius:50%;background:#4caf50}
.ttl .ln{width:330px;height:3px;background:rgba(255,255,255,.55)}
.card{border:3px solid #dbe5f2;border-radius:30px;background:#f6f9fd;padding:26px 34px;margin-top:26px;display:flex;gap:30px}
.card.g{background:#f3faf5;border-color:#d4ebdb}
.main{flex:1}
.hd{display:flex;align-items:center;gap:22px;font-size:40px;font-weight:700;color:#173f8a;margin-bottom:20px;letter-spacing:.5px}
.g .hd{color:#1e5e2e}
.hd .ic{width:70px;height:70px;border-radius:50%;background:#173f8a;color:#fff;display:flex;align-items:center;justify-content:center;font-size:36px}
.g .hd .ic{background:#1e5e2e}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:34px;border:3px solid #d5deea;border-radius:18px;overflow:hidden}
th,td{padding:16px 12px;text-align:center;border-bottom:2px solid #e4e9f1}
th.lt{background:#dbe5f3;color:#173f8a;font-weight:700;font-size:36px}
.g th.lt{background:#d7ecdd;color:#1e5e2e}
td{background:#fff;color:#1f2a3a}
td.l{text-align:left;padding-left:28px;font-weight:600}
tr.tot td{font-weight:700;background:#edf2f9}
.side{width:720px;border-radius:24px;background:#e9f0fa;padding:24px;display:flex;flex-direction:column;gap:16px}
.g .side{background:#e2f3e7}
.side .t{font-size:32px;font-weight:700;color:#173f8a;text-align:center;letter-spacing:.5px}
.g .side .t{color:#1e5e2e}
.pair{display:flex;gap:16px}
.chip{flex:1;text-align:center;font-size:27px;font-weight:700;border-radius:12px;padding:8px 0}
.box{flex:1;background:#fff;border-radius:18px;padding:18px 8px;text-align:center;border-left:8px solid #ccc}
.box .l{font-size:26px;font-weight:600;color:#33415c}
.box .v{font-size:74px;font-weight:700;line-height:1.15}
.box .u{font-size:24px;color:#6b7280}
.split{display:flex;flex-direction:column;justify-content:center}
.sbar{display:flex;height:30px;border-radius:15px;overflow:hidden;margin-top:8px}
.foot{margin-top:20px;text-align:center;font-size:27px;color:#475569;line-height:1.35}
</style>"""
    for _, _, st in groups:
        hd, tx, sub, cell, tot, _ = GLV_STYLE[st]
        css += (f"<style>th.{st}{{background:{hd};color:{tx};font-size:40px;font-weight:700}}th.{st}s{{background:{sub};color:{tx};font-weight:600;font-size:31px}}"
                f"td.{st}{{background:{cell}}}tr.tot td.{st}{{background:{tot};color:{tx}}}.chip.{st}{{background:{hd};color:{tx}}}"
                f".box.{st}{{border-left-color:{hd}}}.box.{st} .v{{color:{tx}}}</style>")
    one = len(groups) == 1
    h = BASE + css + f'<div class="ttl"><span class="ln"></span><span class="dot"></span>{title}<span class="dot"></span><span class="ln"></span></div>'
    # 1. GLV units (patta land)
    h += '<div class="card"><div class="main"><div class="hd"><div class="ic">&#9733;</div>GLV UNIT SUMMARY (PATTA LAND)</div><table>'
    h += '<tr><th class="lt" rowspan="2">GLV Unit</th>' + "".join(f'<th class="{st}" colspan="2">{lab}</th>' for _, lab, st in groups) + '</tr><tr>'
    h += "".join(f'<th class="{st}s">GLV Range</th><th class="{st}s">Area (Acres)</th>' for _, _, st in groups) + '</tr>'
    for name, u in units.items():
        h += f'<tr><td class="l">{name}</td>' + "".join(f'<td class="{st}">{u["range"][k]}</td><td class="{st}">{dash(u[k])}</td>' for k, _, st in groups) + '</tr>'
    pa = {k: sum(u[k] for u in units.values()) for k, _, _ in groups}
    h += '<tr class="tot"><td class="l">TOTAL PATTA</td>' + "".join(f'<td class="{st}">–</td><td class="{st}">{f2(pa[k])}</td>' for k, _, st in groups) + '</tr></table></div>'
    if one:    # whole site: patta land by GLV unit
        k = groups[0][0]; st = groups[0][2]; pt = pa[k] or 1
        parts = [(n, u[k]) for n, u in units.items()]
        h += ('<div class="side split"><div class="t">PATTA AREA BY GLV UNIT</div><div class="pair">'
              + "".join(f'<div class="box {st}"><div class="l">{n.upper()}</div><div class="v">{f2(v)}</div><div class="u">acres · {v / pt * 100:.1f}%</div></div>' for n, v in parts[:2])
              + '</div><div class="sbar">' + "".join(f'<div style="width:{v / pt * 100:.2f}%;background:{c}"></div>' for (n, v), c in zip(parts, ("#7fa6e0", "#f0b67a", "#bdbdbd")))
              + f'</div><div style="text-align:center;font-size:26px;color:#33415c;font-weight:600">Total patta {f2(pa[k])} acres</div></div></div>')
    else:      # DC / Non-DC split of the patta land
        pt = sum(pa.values()) or 1
        h += ('<div class="side split"><div class="t">PATTA AREA SPLIT</div><div class="pair">'
              + "".join(f'<div class="box {st}"><div class="l">{lab}</div><div class="v">{f2(pa[k])}</div><div class="u">acres · {pa[k] / pt * 100:.1f}%</div></div>' for k, lab, st in groups)
              + '</div><div class="sbar">' + "".join(f'<div style="width:{pa[k] / pt * 100:.2f}%;background:{GLV_STYLE[st][5]}"></div>' for k, _, st in groups)
              + f'</div><div style="text-align:center;font-size:26px;color:#33415c;font-weight:600">Total patta {f2(sum(pa.values()))} acres</div></div></div>')
    # 2 + 3. the two conditions
    for key, ctitle, cls in (("C1", "LAND ALLOTMENT AT 110% OF MARKET VALUE WITH 12% ADDITIONAL MARKET VALUE PER ANNUM", ""),
                             ("C2", "LAND ALLOTMENT AT 150% OF MARKET VALUE WITH 12% ADDITIONAL MARKET VALUE FOR 2 YEARS", "g")):
        c = sp[key]
        h += f'<div class="card {cls}"><div class="main"><div class="hd"><div class="ic">&#9878;</div>{ctitle}</div><table>'
        h += '<tr><th class="lt" rowspan="2">Land Type</th>' + "".join(f'<th class="{st}" colspan="3">{lab}</th>' for _, lab, st in groups) + '</tr><tr>'
        h += "".join(f'<th class="{st}s">Area (acres)</th><th class="{st}s">As per Act (₹ Cr)</th><th class="{st}s">Negotiation (₹ Cr)</th>' for _, _, st in groups) + '</tr>'
        for kk, name in (("gov", "Government Land"), ("patta", "Patta Land")):
            h += f'<tr><td class="l">{name}</td>' + "".join(
                f'<td class="{st}">{f2(c[k][kk]["acre"])}</td><td class="{st}">{cr(c[k][kk]["act"])}</td><td class="{st}">{cr(c[k][kk]["neg"])}</td>' for k, _, st in groups) + '</tr>'
        h += '<tr class="tot"><td class="l">TOTAL</td>' + "".join(
            f'<td class="{st}">{f2(c[k]["total"]["acre"])}</td><td class="{st}">{cr(c[k]["total"]["act"])}</td><td class="{st}">{cr(c[k]["total"]["neg"])}</td>' for k, _, st in groups) + '</tr></table></div>'
        h += '<div class="side"><div class="t">ESTIMATED COST PER ACRE (₹ LAKH)</div>'
        if one:
            k, _, st = groups[0]
            h += (f'<div class="pair"><div class="box {st}"><div class="l">As per Act</div><div class="v">{lk(c[k]["total"]["act_per_acre"])}</div></div></div>'
                  f'<div class="pair"><div class="box {st}"><div class="l">As per Negotiation</div><div class="v">{lk(c[k]["total"]["neg_per_acre"])}</div></div></div></div></div>')
        else:
            h += '<div class="pair">' + "".join(f'<div class="chip {st}">{lab}</div>' for _, lab, st in groups) + '</div>'
            for f, lab_ in (("act_per_acre", "As per Act"), ("neg_per_acre", "As per Negotiation")):
                h += '<div class="pair">' + "".join(f'<div class="box {st}"><div class="l">{lab_}</div><div class="v">{lk(c[k]["total"][f])}</div></div>' for k, _, st in groups) + '</div>'
            h += '</div></div>'
    tk = "total" if "total" in sp["C1"] else groups[0][0]
    t1, t2 = sp["C1"][tk]["total"], sp["C2"][tk]["total"]
    h += (f'<div class="foot">' + (f'Whole site {f2(t1["acre"])} acres: 110% – ₹{cr(t1["act"])} Cr as per Act / ₹{cr(t1["neg"])} Cr by negotiation; '
          f'150% – ₹{cr(t2["act"])} Cr / ₹{cr(t2["neg"])} Cr<br>' if not one else f'Proposed area {f2(t1["acre"])} acres &nbsp;|&nbsp; ')
          + (f'{foot_extra} &nbsp;|&nbsp; ' if foot_extra else '') + 'Government land at 50% of the weighted-average patta compensation per acre</div>')
    return h


g = d["glv_unit"]; c1, c2 = d["c1"], d["c2"]
tot = g["total"]
css2 = """<style>
html,body{font-family:Poppins,Arial,sans-serif}
.slide{padding:60px 65px}
.card{border:3px solid #dbe6f3;border-radius:34px;padding:28px 40px;margin-top:30px;background:#f7fbff}
.card.green{background:#f4fbf6;border-color:#d7ecdc}
.hd{display:flex;align-items:center;gap:26px;font-size:40px;font-weight:600;color:#0b2e6b;margin-bottom:26px}
.hd .ic{width:84px;height:84px;border-radius:50%;background:#0b2e6b;color:#fff;display:flex;align-items:center;justify-content:center;font-size:46px}
.green .hd{color:#1e5e2e}.green .hd .ic{background:#1e5e2e}
table{width:100%;border-collapse:collapse;font-size:34px}
th{background:#1d53a8;color:#fff;font-weight:600;padding:22px 10px;border:2px solid #fff}
.green th{background:#1e6e36}
td{padding:19px 10px;text-align:center;border-bottom:2px solid #e3eaf2;background:#fff;font-weight:600;color:#0b2e6b}
.green td{color:#1e5e2e}
tr.tot td{background:#e3ecf9;font-weight:700}.green tr.tot td{background:#e2f2e6}
.pill{display:inline-block;background:#e3ecf9;border-radius:30px;padding:4px 20px;font-size:26px;margin-left:18px;color:#0b2e6b}
.two{display:flex;gap:30px}
.two .left{flex:1}
.est{width:800px;background:#e8f0fb;border-radius:26px;padding:28px;display:flex;flex-direction:column;align-items:center}
.green .est{background:#e3f2e7}
.est .t{font-size:30px;font-weight:600;color:#0b2e6b;margin-bottom:20px}.green .est .t{color:#1e5e2e}
.est .boxes{display:flex;gap:22px;width:100%}
.est .box{flex:1;background:#fff;border-radius:22px;padding:26px 10px;text-align:center}
.est .box .l{font-size:30px;font-weight:600;color:#0b2e6b}.green .est .box .l{color:#1e5e2e}
.est .box .v{font-size:84px;font-weight:700;color:#0b2e6b;line-height:1.1;margin-top:40px}.green .est .box .v{color:#1e5e2e}
.est .box .u{font-size:30px;color:#444}
.foot{margin-top:30px;text-align:center;font-size:28px;color:#334;line-height:1.3}
.ttl{height:150px;border-radius:40px;background:#0b2e6b;color:#fff;font-size:88px;font-weight:700;display:flex;align-items:center;justify-content:center;gap:40px}
.ttl .dot{width:26px;height:26px;border-radius:50%;background:#4caf50;display:inline-block}
</style>"""


def cond_card(c, title, cls):
    h = f'<div class="card {cls}"><div class="hd"><div class="ic">&#9878;</div>{title}</div><div class="two"><div class="left"><table>'
    h += '<tr><th>Land Type</th><th>Area (acres)</th><th>Area (%)</th><th>Compensation as per act (₹ Crores)</th><th>Compensation as per negotiation (₹ Crores)</th></tr>'
    for k, name in (("gov", "Government Land"), ("patta", "Patta Land")):
        v = c[k]; h += f'<tr><td>{name}</td><td>{f2(v["acre"])}</td><td>{v["pct"]:.1f}%</td><td>{f2(v["act"])}</td><td>{f2(v["neg"])}</td></tr>'
    t = c["total"]; h += f'<tr class="tot"><td>TOTAL</td><td>{f2(t["acre"])}</td><td>100.0%</td><td>{f2(t["act"])}</td><td>{f2(t["neg"])}</td></tr></table></div>'
    h += f'<div class="est"><div class="t">ESTIMATED COST PER ACRE</div><div class="boxes"><div class="box"><div class="l">As per Act</div><div class="v">{c["per_acre_act_lakh"]:.2f}</div><div class="u">(Lakh)</div></div>'
    h += f'<div class="box"><div class="l">As per Negotiation</div><div class="v">{c["per_acre_neg_lakh"]:.2f}</div><div class="u">(Lakh)</div></div></div></div></div></div>'
    return h


html = BASE + css2 + '<div class="ttl"><span class="dot"></span>GLV SUMMARY<span class="dot"></span></div>'
html += '<div class="card"><div class="hd"><div class="ic">&#9733;</div>GLV UNIT SUMMARY</div><table><tr><th>GLV Unit</th><th>GLV Range</th><th>Area (Acres)</th></tr>'
for name, k in (("Acres", "acres"), ("Square feet", "sqft"), ("No data", "nodata")):
    v = g[k]; p = v["area"] / tot * 100 if tot else 0
    html += f'<tr><td>{name}</td><td>{v["range"]}</td><td>{f2(v["area"])}<span class="pill">{p:.0f}%</span></td></tr>'
html += f'<tr class="tot"><td>TOTAL</td><td>–</td><td>{f2(tot)}</td></tr></table></div>'
html += cond_card(c1, "LAND ALLOTMENT AT 110% OF MARKET VALUE WITH 12% ADDITIONAL MARKET VALUE PER ANNUM", "")
html += cond_card(c2, "LAND ALLOTMENT AT 150% OF MARKET VALUE WITH 12% ADDITIONAL MARKET VALUE FOR 2 YEARS", "green")
html += f'<div class="foot">Proposed area: {f2(d.get("glv_area") or A)} acres &nbsp;|&nbsp; All areas are in Acres &nbsp;|&nbsp; Amounts are in ₹ Crores</div>'
if d.get("dc_glv"):   # DC / Non-DC classification only when the user gave a DC-land list
    html = dc_glv_html(d["dc_glv"], A)
elif d.get("glv_site"):  # every other site: the same template with one column group for the whole site
    html = glv_cards_html(d["glv_site"]["split"], d["glv_site"]["units"], [("total", "PROPOSED SITE", "st")], d["glv_site"].get("note", ""), "GLV SUMMARY")
shot(html + END, "s07_glv_summary")

# ---------------- 3. VILLAGEWISE ----------------
COL = d["village_colors"]
css3 = """<style>
.vrow{padding:34px 50px 0 50px}
.vrow .nm{display:flex;justify-content:space-between;align-items:center;font-size:52px;font-weight:700;color:#0f3b5a}
.vrow .nm .l{display:flex;align-items:center;gap:24px}
.vrow .dot{width:40px;height:40px;border-radius:50%;display:inline-block}
.vrow .tr{height:22px;background:#e3e8ee;border-radius:11px;margin-top:22px;overflow:hidden}
.vrow .tr div{height:100%;border-radius:11px}
.vrow .p{font-size:30px;color:#555;font-weight:700;margin-top:14px}
.hdr{display:flex;justify-content:space-between;padding:30px 50px 20px 50px;font-size:34px;color:#555;font-weight:700;border-bottom:3px solid #e3e8ee}
</style>"""
vs = d["villages"]; order = sorted(d["villages"], key=lambda v: -d["villages"][v]["acre"])
html = BASE + css3 + '<div class="title">VILLAGEWISE CLASSIFICATION</div><div class="body"><div class="map"><img src="map_village.png"></div><div class="panel"><h3>VILLAGE-WISE AREA (ACRES)</h3><div class="hdr"><span>Village</span><span>Area (acres)</span></div>'
for v in order:
    if v not in vs: continue
    x = vs[v]; html += f'<div class="vrow"><div class="nm"><span class="l"><span class="dot" style="background:{COL[v]}"></span>{v}</span><span>{f2(x["acre"])}</span></div><div class="tr"><div style="width:{x["pct"]:.1f}%;background:{COL[v]}"></div></div><div class="p">{pct(x["pct"])} of total area</div></div>'
html += '</div></div>'
largest = max(vs.items(), key=lambda kv: kv[1]["acre"]); _o = sorted(vs.items(), key=lambda kv: -kv[1]["acre"]); second = _o[1] if len(_o) > 1 else _o[0]
html += f'<div class="cov"><div class="lab">VILLAGE<br>COVERAGE</div><div class="stats"><div class="row">'
for big, small, sub in ((f2(A), "acres", "Total Area"), (str(len(vs)), "", "Villages"), (f2(largest[1]["acre"]), f"acres · {largest[1]['pct']:.2f}%", f"{largest[0]} (largest)"), (f2(second[1]["acre"]), f"acres · {second[1]['pct']:.2f}%", second[0])):
    html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
html += '</div><div class="bar">' + "".join(f'<div style="width:{vs[v]["pct"]:.2f}%;background:{COL[v]}"></div>' for v in order if v in vs) + '</div></div></div>'
shot(html + END, "s08_villagewise")

# ---------------- 4. OWNERSHIP ----------------
def donut(parts, total, label):
    """conic-gradient donut: parts = [(color, value)]"""
    stops, acc = [], 0
    for col, v in parts:
        a = v / total * 100; stops.append(f"{col} {acc:.2f}% {acc + a:.2f}%"); acc += a
    return (f'<div style="width:420px;height:420px;border-radius:50%;background:conic-gradient({",".join(stops)});margin:30px auto;position:relative">'
            f'<div style="position:absolute;inset:95px;border-radius:50%;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center">'
            f'<div style="font-size:66px;font-weight:700;color:#0f3b5a;line-height:1">{f2(total)}</div><div style="font-size:26px;color:#555;font-weight:700">{label}</div></div></div>')


def legend_rows(items):
    h = ""
    for col, name, v, p in items:
        h += (f'<div class="vrow"><div class="nm"><span class="l"><span class="dot" style="background:{col}"></span>{name}</span><span>{f2(v)}</span></div>'
              f'<div class="tr"><div style="width:{p:.1f}%;background:{col}"></div></div><div class="p">{pct(p)} of total area</div></div>')
    return h


gv, pv = d["gov_total"], d["patta_total"]; oc = d["own_classes"]
html = BASE + css3 + '<div class="title">OWNERSHIP CLASSIFICATION</div><div class="body"><div class="map"><img src="map_owner.png"></div><div class="panel"><h3>OWNERSHIP-WISE AREA (ACRES)</h3><div class="hdr"><span>Ownership · land type</span><span>Area (acres)</span></div>'
html += donut([(c, v) for _, v, c in oc], A, "acres total")
html += legend_rows([(c, n, v, v / A * 100) for n, v, c in oc])
html += '</div></div>'
html += f'<div class="cov"><div class="lab">OWNERSHIP<br>COVERAGE</div><div class="stats"><div class="row">'
for big, small, sub in [(f2(A), "acres", "Total Area")] + [(f2(v), f"acres · {v / A * 100:.2f}%", n) for n, v, c in oc[:3]]:
    html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
html += '</div><div class="bar">' + "".join(f'<div style="width:{v / A * 100:.2f}%;background:{c};color:#111">{n.replace("Patta - ", "")} {v / A * 100:.1f}%</div>' for n, v, c in oc) + '</div></div></div>'
shot(html + END, "s09_ownership")

# ---------------- 5. CROP ----------------
cr = d["crop"]; ns, nc, cl = cr["nosurvey"], cr["noncrop"], cr["crop"]
html = BASE + css3 + '<div class="title">CROP DATA CLASSIFICATION</div><div class="body"><div class="map"><img src="map_crop.png"></div><div class="panel"><h3>CROP DATA – AREA (ACRES)</h3><div class="hdr"><span>Land Type</span><span>Area (acres)</span></div>'
html += legend_rows([("#bdbdbd", "No Survey Data", ns, ns / A * 100), ("#f5c242", "Non-crop Land", nc, nc / A * 100), ("#2ecc71", "Crop Land", cl, cl / A * 100)])
crops = d.get("crops") or []
cats = sorted(d.get("crop_cats") or [], key=lambda c: -c["acre"])
if cats:     # crop land split by what is grown - the same colours as the map
    html += ('<div style="padding:22px 40px 0 40px"><div style="font-size:32px;font-weight:700;color:#0f3b5a;margin-bottom:8px">Crop categories (crop land on the map)</div>'
             '<table style="width:100%;border-collapse:collapse;font-size:30px"><tr><th style="background:#0f3b5a;color:#fff;padding:12px;text-align:left">Crop</th>'
             '<th style="background:#0f3b5a;color:#fff;padding:12px">Area (ac)</th><th style="background:#0f3b5a;color:#fff;padding:12px">% of site</th></tr>')
    for c_ in cats[:8]:
        html += (f'<tr><td style="padding:10px 12px;border-bottom:2px solid #e3e8ee"><span style="display:inline-block;width:28px;height:28px;border-radius:6px;'
                 f'background:{c_["color"]};margin-right:14px;vertical-align:middle"></span>{c_["name"]}</td>'
                 f'<td style="text-align:center;border-bottom:2px solid #e3e8ee">{f2(c_["acre"])}</td><td style="text-align:center;border-bottom:2px solid #e3e8ee">{c_["acre"] / A * 100:.2f}%</td></tr>')
    html += '</table></div>'
elif crops:
    html += ('<div style="padding:26px 40px 0 40px"><table style="width:100%;border-collapse:collapse;font-size:30px"><tr>'
             '<th style="background:#0f3b5a;color:#fff;padding:12px;text-align:left">Crop</th><th style="background:#0f3b5a;color:#fff;padding:12px">Crop area (ac)</th>'
             '<th style="background:#0f3b5a;color:#fff;padding:12px">% of site</th></tr>')
    for c_ in crops[:6]:
        html += (f'<tr><td style="padding:10px 12px;border-bottom:2px solid #e3e8ee">{c_["crop"]}<div style="font-size:22px;color:#777">{c_["seasons"]}</div></td>'
                 f'<td style="text-align:center;border-bottom:2px solid #e3e8ee">{f2(c_["acre"])}</td><td style="text-align:center;border-bottom:2px solid #e3e8ee">{c_["acre"] / A * 100:.2f}%</td></tr>')
    html += '</table><div style="font-size:22px;color:#666;margin-top:10px">Crop area = largest sown area of the crop in any surveyed season.</div></div>'
html += '</div></div>'
html += f'<div class="cov"><div class="lab">CROP DATA<br>COVERAGE</div><div class="stats"><div class="row">'
for big, small, sub in ((f2(A), "acres", "Total Area"), (f2(ns), f"acres · {ns/A*100:.2f}%", "No Survey Data"), (f2(cl), f"acres · {cl/A*100:.2f}%", "Crop Land"), (f2(nc), f"acres · {nc/A*100:.2f}%", "Non-crop Land")):
    html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
html += f'</div><div class="bar"><div style="width:{ns/A*100:.2f}%;background:#bdbdbd;color:#333">No Survey Data {ns/A*100:.2f}%</div><div style="width:{nc/A*100:.2f}%;background:#f5c242;color:#333">Non-crop {nc/A*100:.2f}%</div><div style="width:{cl/A*100:.2f}%;background:#2ecc71;color:#fff">Crop {cl/A*100:.2f}%</div></div></div></div>'
shot(html + END, "s10_crop")

# ---------------- 6. SOIL + LAND QUALITY (A-register) ----------------
EXTRA = []
if d.get("soil"):
    so = d["soil"]; cols = d.get("tharam_colors", {})
    html = BASE + css3 + '<div class="title">SOIL &amp; LAND QUALITY (A-REGISTER)</div><div class="body"><div class="map"><img src="map_soil.png"></div><div class="panel"><h3>LAND GRADE (THARAM) – AREA (ACRES)</h3><div class="hdr"><span>Tharam · assessment</span><span>Area (acres)</span></div>'
    rows_ = so["tharam"][:5]
    if len(so["tharam"]) > 5:   # fold the small grades into one row
        rest = so["tharam"][5:]
        rows_ = rows_ + [{"label": "Other grades", "acre": sum(t["acre"] for t in rest), "n": sum(t["n"] for t in rest), "rate": "-"}]
    for t in rows_:
        p_ = t["acre"] / A * 100; c_ = cols.get(t["label"], "#9e9e9e")
        html += (f'<div class="vrow" style="padding-top:18px"><div class="nm" style="font-size:42px"><span class="l"><span class="dot" style="background:{c_}"></span>{t["label"]}</span><span>{f2(t["acre"])}</span></div>'
                 f'<div class="tr"><div style="width:{p_:.1f}%;background:{c_}"></div></div><div class="p">{pct(p_)} of total area · assessment {t["rate"]} · {t["n"]} subdivisions</div></div>')
    html += '<div style="margin-top:auto;padding:22px 50px;font-size:26px;color:#555;line-height:1.3;border-top:2px solid #e3e8ee">Tharam = settlement grade recorded in the A-register; assessment = land revenue rate per hectare fixed at settlement (higher = land rated more productive).</div></div></div>'
    irr = so.get("irrigation", {}); irr_txt = ", ".join(f"{k} {f2(v)}" for k, v in sorted(irr.items(), key=lambda kv: -kv[1])[:2])
    html += '<div class="cov"><div class="lab">LAND QUALITY<br>SUMMARY</div><div class="stats"><div class="row">'
    top = so["tharam"][0] if so["tharam"] else {"label": "-", "acre": 0}
    for big, small, sub in ((f2(A), "acres", "Total Area"), (f"{so['assessment_wavg']:.2f}", "Rs / ha", "Mean assessment (patta land)"),
                            (f2(top["acre"]), f"acres · {top['acre'] / A * 100:.1f}%", f"{top['label']} (largest)"), (str(so["classes"]), "codes", "Soil class-sort codes")):
        html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
    html += '</div><div class="bar">' + "".join(f'<div style="width:{t["acre"] / A * 100:.2f}%;background:{cols.get(t["label"], "#9e9e9e")}"></div>' for t in so["tharam"]) + '</div>'
    if [k for k in irr if k != "Not recorded"]:
        html += f'<div class="sub" style="margin-top:12px">Irrigation source (A-register): {irr_txt}</div>'
    html += '</div></div>'
    shot(html + END, "s11_soil"); EXTRA.append("s11_soil")

# ---------------- 7. SENSITIVE LAND ----------------
SENS_C = {"Water body": "#1e88e5", "Channel": "#00acc1", "Temple/Church/Mosque": "#8e24aa", "Burial": "#5d4037", "Village site": "#f4511e", "Forest": "#2e7d32",
          "NH land": "#fdd835", "Well": "#4fc3f7", "Other government poramboke": "#9e9e9e"}
if d.get("sensitive"):
    se = d["sensitive"]; rows = se["rows"]; tot = se["sensitive_acre"]
    html = BASE + css3 + '<div class="title">SENSITIVE LAND INSIDE THE SITE</div><div class="body"><div class="map"><img src="map_sensitive.png"></div><div class="panel"><h3>SENSITIVE LAND – AREA (ACRES)</h3><div class="hdr"><span>Category (A-register remarks)</span><span>Area (acres)</span></div>'
    for r in rows:
        p_ = r["acre"] / A * 100; c_ = SENS_C.get(r["category"], "#9e9e9e")
        html += (f'<div class="vrow" style="padding-top:24px"><div class="nm" style="font-size:44px"><span class="l"><span class="dot" style="background:{c_}"></span>{r["category"]}</span><span>{f2(r["acre"])}</span></div>'
                 f'<div class="tr"><div style="width:{max(p_, 0.6):.1f}%;background:{c_}"></div></div><div class="p">{pct(p_)} · {r["subdivisions"]} subdivisions · survey {r["surveys"]}</div></div>')
    if not rows:
        html += '<div style="padding:50px;font-size:40px">No sensitive remarks in the A-register for this site.</div>'
    html += '</div></div><div class="cov"><div class="lab">SENSITIVE<br>LAND</div><div class="stats"><div class="row">'
    big_r = max(rows, key=lambda r: r["acre"]) if rows else {"category": "-", "acre": 0}
    for big, small, sub in ((f2(A), "acres", "Total Area"), (f2(tot), f"acres · {tot / A * 100:.2f}%", "Flagged land"), (str(len(rows)), "", "Categories"),
                            (f2(big_r["acre"]), "acres", f"{big_r['category']} (largest)")):
        html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
    html += f'</div><div class="bar"><div style="width:{100 - tot / A * 100:.2f}%;background:#b0bec5;color:#0f3b5a">Rest of site {100 - tot / A * 100:.2f}%</div>' + "".join(
        f'<div style="width:{r["acre"] / A * 100:.2f}%;background:{SENS_C.get(r["category"], "#9e9e9e")}"></div>' for r in rows) + '</div></div></div>'
    shot(html + END, "s12_sensitive"); EXTRA.append("s12_sensitive")

# ---------------- GOVERNMENT LAND CLASSIFICATION (after ownership) ----------------
if d.get("govtland"):
    gl = d["govtland"]; GT = gl["govt_acre"]; rows = gl["rows"]
    show = rows[:5]
    if len(rows) > 5:
        rest = rows[5:]
        show = show + [{"category": "Other categories", "acre": sum(r["acre"] for r in rest), "subdivisions": sum(r["subdivisions"] for r in rest), "color": "#9e9e9e",
                        "surveys": "", "note": f"{len(rest)} smaller categories (Govt_Land_Classification sheet)"}]
    html = BASE + css3 + '<div class="title">GOVERNMENT LAND CLASSIFICATION</div><div class="body"><div class="map"><img src="map_govt.png"></div><div class="panel"><h3>GOVERNMENT LAND – AREA (ACRES)</h3><div class="hdr"><span>Classification (A-register)</span><span>Area (acres)</span></div>'
    for r in show:
        p_ = r["acre"] / GT * 100 if GT else 0
        html += (f'<div class="vrow" style="padding-top:18px"><div class="nm" style="font-size:40px"><span class="l"><span class="dot" style="background:{r["color"]}"></span>{r["category"]}</span><span>{f2(r["acre"])}</span></div>'
                 f'<div class="tr"><div style="width:{max(p_, 0.6):.1f}%;background:{r["color"]}"></div></div><div class="p">{pct(p_)} of govt land · {r["subdivisions"]} subdiv. · ' + (r.get("note") or f'survey {r["surveys"]}') + '</div></div>')
    if not gl.get("codes_named"):
        html += '<div style="margin-top:auto;padding:20px 50px;font-size:25px;color:#555;border-top:2px solid #e3e8ee">Poramboke codes are shown as recorded in the A-register; names appear once the code list (Poramboke_Codes.xlsx) is filled in.</div>'
    html += '</div></div>'
    lt = gl["by_land_type"]; vv = gl["by_village"]; th = gl.get("by_tharam", {})
    top = rows[0] if rows else {"category": "-", "acre": 0}
    html += '<div class="cov"><div class="lab">GOVERNMENT<br>LAND MIS</div><div class="stats"><div class="row">'
    for big, small, sub in ((f2(GT), f"acres · {GT / A * 100:.2f}%", "Government land of the site"),
                            (f2(lt.get("Poramboke", 0)), "acres", "Poramboke"),
                            (f2(sum(v for k, v in lt.items() if k != "Poramboke")), "acres", "Assessed govt land (" + ", ".join(k for k in lt if k != "Poramboke") + ")" if len(lt) > 1 else "Assessed govt land"),
                            (f2(top["acre"]), "acres", f"{top['category']} (largest)")):
        html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
    html += '</div><div class="bar">' + "".join(f'<div style="width:{r["acre"] / GT * 100:.2f}%;background:{r["color"]}"></div>' for r in rows) + '</div>'
    line = "Village-wise: " + ", ".join(f"{k} {f2(v)}" for k, v in list(vv.items())[:4])
    if th:
        line += " &nbsp;|&nbsp; Soil grade: " + ", ".join(f"{k} {f2(v)}" for k, v in list(th.items())[:3])
    html += f'<div class="sub" style="margin-top:12px;font-size:30px">{line}</div></div></div>'
    shot(html + END, "s09b_govt"); EXTRA.append("s09b_govt")


# ---------------- EXECUTIVE SUMMARY (after title) ----------------
if d.get("exec"):
    ex = d["exec"]
    css_ex = """<style>.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:40px;margin-top:50px}
.card{border:3px solid #d6dde8;border-radius:30px;padding:46px 44px;background:#f7fbff;min-height:600px}
.card .k{font-size:46px;color:#555;font-weight:700}.card .v{font-size:112px;font-weight:700;color:#0f3b5a;margin-top:30px;line-height:1.05}
.card .v small{font-size:50px;color:#555}.card .s{font-size:40px;color:#333;margin-top:28px;line-height:1.4}
.card.g{background:#f1f8f3}.card.o{background:#fff8ee}</style>"""
    html = BASE + css_ex + '<div class="title">EXECUTIVE SUMMARY</div><div class="grid">'
    for c_ in ex["cards"]:
        html += f'<div class="card {c_.get("cls", "")}"><div class="k">{c_["k"]}</div><div class="v">{c_["v"]}</div><div class="s">{c_["s"]}</div></div>'
    html += '</div>'
    if ex.get("notes"):
        html += ('<div style="margin-top:50px;border:3px solid #d6dde8;border-radius:30px;padding:36px 50px;font-size:42px;color:#333;line-height:1.55;'
                 'columns:2;column-gap:80px"><div style="font-weight:700;color:#0f3b5a">Connectivity</div>' + "".join(f"<div>• {n}</div>" for n in ex["notes"]) + '</div>')
    shot(html + END, "s01b_summary"); EXTRA.append("s01b_summary")

# ---------------- GLV MAP (after GLV summary) ----------------
if d.get("glvmap"):
    gm = d["glvmap"]
    html = BASE + css3 + '<div class="title">GUIDELINE LAND VALUE (GLV) MAP</div><div class="body"><div class="map"><img src="map_glv.png"></div><div class="panel"><h3>GLV BAND – AREA (ACRES)</h3><div class="hdr"><span>GLV band (as quoted)</span><span>Area (acres)</span></div>'
    for r in gm["rows"]:
        p_ = r["acre"] / A * 100
        rr = "" if r["lo"] <= 0 else (f' · Rs {r["lo"]:,.0f}' + (f' - {r["hi"]:,.0f}' if r["hi"] != r["lo"] else ""))
        html += (f'<div class="vrow" style="padding-top:20px"><div class="nm" style="font-size:40px"><span class="l"><span class="dot" style="background:{r["color"]}"></span>{r["band"]}</span><span>{f2(r["acre"])}</span></div>'
                 f'<div class="tr"><div style="width:{max(p_, 0.6):.1f}%;background:{r["color"]}"></div></div><div class="p">{pct(p_)} · {r["n"]} subdivisions{rr}</div></div>')
    html += '</div></div><div class="cov"><div class="lab">GLV<br>RANGE</div><div class="stats"><div class="row">'
    ar, sr = gm.get("acre_range"), gm.get("sqft_range")
    items = [(f2(A), "acres", "Total Area"), ((f"{ar[0] / 1e5:.1f} - {ar[1] / 1e5:.1f}" if ar else "-"), "lakh / acre", "Per acre (land)"),
             ((f"{sr[0]:,.0f} - {sr[1]:,.0f}" if sr else "-"), "Rs / sq ft", "Per sq ft (layout plots)"),
             (f2(sum(r["acre"] for r in gm["rows"] if r["band"] == "Govt / value 0")), "acres", "Govt land (value 0)")]
    for big, small, sub in items:
        html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
    html += '</div><div class="bar">' + "".join(f'<div style="width:{r["acre"] / A * 100:.2f}%;background:{r["color"]}"></div>' for r in gm["rows"]) + '</div></div></div>'
    shot(html + END, "s07b_glvmap"); EXTRA.append("s07b_glvmap")

# ---------------- PATTA HOLDINGS (after government land) ----------------
if d.get("owners"):
    ow = d["owners"]
    html = BASE + css3 + '<div class="title">PATTA HOLDINGS – OWNER DISTRIBUTION</div><div class="body"><div class="map"><img src="map_holding.png"></div><div class="panel"><h3>PATTAS BY HOLDING SIZE</h3><div class="hdr"><span>Area inside the site</span><span>Pattas · acres</span></div>'
    for b in ow["by_range"]:
        p_ = b["pattas"] / max(ow["pattas"], 1) * 100
        html += (f'<div class="vrow" style="padding-top:18px"><div class="nm" style="font-size:38px"><span class="l"><span class="dot" style="background:{b["color"]}"></span>{b["range"]}</span><span>{b["pattas"]} · {f2(b["acre"])}</span></div>'
                 f'<div class="tr"><div style="width:{max(p_, 0.6):.1f}%;background:{b["color"]}"></div></div><div class="p">{p_:.1f}% of pattas · {b["acre"] / max(ow["patta_acre"], 1e-9) * 100:.1f}% of patta land</div></div>')
    html += '<div style="padding:24px 40px 0 40px;font-size:30px;font-weight:700;color:#0f3b5a">Largest pattas</div><div style="padding:6px 40px 0 40px">'
    for t in ow["top"][:4]:
        html += (f'<div style="font-size:27px;padding:8px 0;border-bottom:2px solid #e3e8ee"><b>Patta {t["patta"]}</b> ({t["village"]}) · {f2(t["acre"])} ac · {t["owner_count"]} owners'
                 f'<div class="tam" style="font-family:\'Noto Sans Tamil\',Arial;font-size:24px;color:#444">{t["owners"]}</div></div>')
    html += '</div></div></div><div class="cov"><div class="lab">OWNER<br>DISTRIBUTION</div><div class="stats"><div class="row">'
    small = next((b for b in ow["by_range"] if b["range"] == "2 acres or less"), {"pattas": 0})
    for big, smalltxt, sub in ((str(ow["pattas"]), "pattas", "Patta numbers in the site"), (f2(ow["patta_acre"]), "acres", "Patta land"),
                               (str(small["pattas"]), f"pattas · {small['pattas'] / max(ow['pattas'], 1) * 100:.0f}%", "Holdings of 2 acres or less"),
                               (str(ow["companies"]), f"pattas · {f2(ow['company_acre'])} ac", "Held by companies")):
        html += f'<div><div class="big">{big} <small>{smalltxt}</small></div><div class="sub">{sub}</div></div>'
    html += '</div><div class="bar">' + "".join(f'<div style="width:{b["pattas"] / max(ow["pattas"], 1) * 100:.2f}%;background:{b["color"]}"></div>' for b in ow["by_range"]) + '</div></div></div>'
    shot(html + END, "s09c_owners"); EXTRA.append("s09c_owners")


# ---------------- COMPANY / INSTITUTION OWNERSHIP (after patta holdings) ----------------
if d.get("companies") and d["companies"]["n"]:
    co = d["companies"]
    html = BASE + css3 + '<div class="title">COMPANY &amp; INSTITUTION OWNERSHIP</div><div class="body"><div class="map"><img src="map_company.png"></div><div class="panel"><h3>LAND HELD BY COMPANIES / INSTITUTIONS</h3><div class="hdr"><span>Owner (as in the A-register)</span><span>Area (acres)</span></div>'
    for r in co["rows"][:7]:
        p_ = r["acre"] / A * 100
        html += (f'<div class="vrow" style="padding-top:16px"><div class="nm" style="font-size:31px;font-family:\'Noto Sans Tamil\',Arial"><span class="l"><span class="dot" style="background:{r["color"]};flex:none"></span>{r["name"][:46]}</span><span>{f2(r["acre"])}</span></div>'
                 f'<div class="p">{r["type"]} · {r["pattas"]} patta{"s" if r["pattas"] != 1 else ""} · {r["villages"]} · {pct(p_)} of site</div></div>')
    if len(co["rows"]) > 7:
        html += f'<div style="padding:18px 50px;font-size:28px;color:#555">+{len(co["rows"]) - 7} more in the Company_Ownership sheet</div>'
    html += '</div></div><div class="cov"><div class="lab">COMPANY<br>HOLDINGS</div><div class="stats"><div class="row">'
    rg = co["ranges"]
    for big, small, sub in ((str(co["n"]), "owners", "Companies / institutions"), (f2(co["acre"]), f"acres · {co['acre'] / A * 100:.2f}%", "Land they hold"),
                            (str(rg["More than 10 acres"]), "owners", "More than 10 acres"), (str(rg["More than 5 acres"] + rg["5 acres or less"]), "owners", "10 acres or less")):
        html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
    html += '</div><div class="bar">' + "".join(f'<div style="width:{r["acre"] / co["acre"] * 100:.2f}%;background:{r["color"]}"></div>' for r in co["rows"]) + '</div></div></div>'
    shot(html + END, "s09d_company"); EXTRA.append("s09d_company")

# ---------------- screenshots ----------------
from selenium import webdriver
o = webdriver.ChromeOptions(); o.add_argument("--headless=new"); o.add_argument("--window-size=3240,2250"); o.add_argument("--force-device-scale-factor=1"); o.add_argument("--hide-scrollbars")
drv = webdriver.Chrome(options=o)
for n in ("s06_land_summary", "s07_glv_summary", "s08_villagewise", "s09_ownership", "s10_crop", *EXTRA):
    drv.get("file:///" + os.path.abspath(f"{D}/{n}.html").replace("\\", "/")); time.sleep(2.5)
    iw, ih = drv.execute_script("return [window.innerWidth, window.innerHeight]")
    if (iw, ih) != (3240, 2250):
        drv.set_window_size(3240 + (3240 - iw), 2250 + (2250 - ih)); time.sleep(0.5)
    drv.save_screenshot(f"{D}/{n}.png")
    print("shot", n)
drv.quit()

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


own_rows = [("Government Land", d["own"]["Government Land"]), ("Patta Land", d["own"]["Patta Land"])]
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
html = BASE + css1 + '<div class="title navy">LAND SUMMARY</div>'
html += tbl("OWNERSHIP CLASSIFICATION (ACRES)", "Ownership Classification", own_rows, A, A)
html += tbl("LAND CLASSIFICATION (ACRES)", "Land Classification", cls_rows, A, A)
import re as _re
html += _re.sub("<td>([஀-௿])", lambda m: '<td class="tam">' + m.group(1), tbl("GOVERNMENT LAND REMARKS (ACRES)", "Remarks", rem_rows, d["gov_total"], d["gov_total"]))
html += f'<div class="foot">Area = A-register extent; {d.get("split_surveys", 0)} split edge surveys are counted at the area inside the boundary.</div>'
shot(html + END, "s06_land_summary")

# ---------------- 2. GLV SUMMARY ----------------
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
html += f'<div class="foot">Proposed area: {f2(A)} acres &nbsp;|&nbsp; All areas are in Acres &nbsp;|&nbsp; Amounts are in ₹ Crores</div>'
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


gv, pv = d["gov_total"], d["patta_total"]
html = BASE + css3 + '<div class="title">OWNERSHIP CLASSIFICATION</div><div class="body"><div class="map"><img src="map_owner.png"></div><div class="panel"><h3>OWNERSHIP-WISE AREA (ACRES)</h3><div class="hdr"><span>Ownership</span><span>Area (acres)</span></div>'
html += donut([("#f5c242", pv), ("#2ecc71", gv)], A, "acres total")
html += legend_rows([("#f5c242", "Patta Land", pv, pv / A * 100), ("#2ecc71", "Government Land", gv, gv / A * 100), ("#9e9e9e", "No Survey Data", 0.0, 0.0)])
html += '</div></div>'
html += f'<div class="cov"><div class="lab">OWNERSHIP<br>COVERAGE</div><div class="stats"><div class="row">'
for big, small, sub in ((f2(A), "acres", "Total Area"), (f2(pv), f"acres · {pv/A*100:.2f}%", "Patta Land"), (f2(gv), f"acres · {gv/A*100:.2f}%", "Government Land"), ("0.00", "acres", "No Survey Data")):
    html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
html += f'</div><div class="bar"><div style="width:{pv/A*100:.2f}%;background:#f5c242;color:#333">Patta {pv/A*100:.2f}%</div><div style="width:{gv/A*100:.2f}%;background:#2ecc71;color:#fff">Govt {gv/A*100:.2f}%</div></div></div></div>'
shot(html + END, "s09_ownership")

# ---------------- 5. CROP ----------------
cr = d["crop"]; ns, nc, cl = cr["nosurvey"], cr["noncrop"], cr["crop"]
html = BASE + css3 + '<div class="title">CROP DATA CLASSIFICATION</div><div class="body"><div class="map"><img src="map_crop.png"></div><div class="panel"><h3>CROP DATA – AREA (ACRES)</h3><div class="hdr"><span>Land Type</span><span>Area (acres)</span></div>'
html += donut([("#bdbdbd", ns), ("#f5c242", nc), ("#2ecc71", cl)], A, "acres total")
html += legend_rows([("#bdbdbd", "No Survey Data", ns, ns / A * 100), ("#f5c242", "Non-crop Land", nc, nc / A * 100), ("#2ecc71", "Crop Land", cl, cl / A * 100)])
html += '</div></div>'
html += f'<div class="cov"><div class="lab">CROP DATA<br>COVERAGE</div><div class="stats"><div class="row">'
for big, small, sub in ((f2(A), "acres", "Total Area"), (f2(ns), f"acres · {ns/A*100:.2f}%", "No Survey Data"), (f2(cl), f"acres · {cl/A*100:.2f}%", "Crop Land"), (f2(nc), f"acres · {nc/A*100:.2f}%", "Non-crop Land")):
    html += f'<div><div class="big">{big} <small>{small}</small></div><div class="sub">{sub}</div></div>'
html += f'</div><div class="bar"><div style="width:{ns/A*100:.2f}%;background:#bdbdbd;color:#333">No Survey Data {ns/A*100:.2f}%</div><div style="width:{nc/A*100:.2f}%;background:#f5c242;color:#333">Non-crop {nc/A*100:.2f}%</div><div style="width:{cl/A*100:.2f}%;background:#2ecc71;color:#fff">Crop {cl/A*100:.2f}%</div></div></div></div>'
shot(html + END, "s10_crop")

# ---------------- screenshots ----------------
from selenium import webdriver
o = webdriver.ChromeOptions(); o.add_argument("--headless=new"); o.add_argument("--window-size=3240,2250"); o.add_argument("--force-device-scale-factor=1"); o.add_argument("--hide-scrollbars")
drv = webdriver.Chrome(options=o)
for n in ("s06_land_summary", "s07_glv_summary", "s08_villagewise", "s09_ownership", "s10_crop"):
    drv.get("file:///" + os.path.abspath(f"{D}/{n}.html").replace("\\", "/")); time.sleep(2.5)
    iw, ih = drv.execute_script("return [window.innerWidth, window.innerHeight]")
    if (iw, ih) != (3240, 2250):
        drv.set_window_size(3240 + (3240 - iw), 2250 + (2250 - ih)); time.sleep(0.5)
    drv.save_screenshot(f"{D}/{n}.png")
    print("shot", n)
drv.quit()

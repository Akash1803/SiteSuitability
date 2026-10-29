"""Standalone PyQGIS renderer (run with QGIS's python-qgis-ltr.bat): satellite base maps for the PPT.
Usage: python-qgis-ltr.bat qgis_render.py <params.json>
params: out_dir, boundary, parcels, conn (gpkg), admin (gpkg), road_ids, village_road_ids, station_names, village_colors"""
import json
import sys
import warnings
warnings.filterwarnings('ignore')

from qgis.core import (Qgis, QgsApplication, QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature,
                       QgsField, QgsFillSymbol, QgsGeometry, QgsLineSymbol, QgsMapRendererCustomPainterJob, QgsMapSettings, QgsMarkerSymbol,
                       QgsPalLayerSettings, QgsProject, QgsRasterLayer, QgsRectangle, QgsRendererCategory, QgsSimpleLineSymbolLayer,
                       QgsSingleSymbolRenderer, QgsTextBufferSettings, QgsTextFormat, QgsVectorLayer, QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtCore import QSize, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QImage, QPainter

app = QgsApplication([], False); app.initQgis()
A = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = A["out_dir"]; P = QgsProject.instance()
WEB = QgsCoordinateReferenceSystem("EPSG:3857"); W, H = 2160, 1374
sat = QgsRasterLayer("type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D{x}%26y%3D{y}%26z%3D{z}&zmax=20&zmin=0", "sat", "wms")
bd = QgsVectorLayer(A["boundary"], "bd", "ogr")
g = QgsGeometry.unaryUnion([f.geometry() for f in bd.getFeatures()]); g.transform(QgsCoordinateTransform(bd.crs(), WEB, P)); bb = g.boundingBox()


def nofill(l, col, w):
    s = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": col, "outline_width": str(w)}); s.symbolLayer(0).setBrushStyle(Qt.NoBrush)
    l.setRenderer(QgsSingleSymbolRenderer(s)); l.setLabelsEnabled(False); return l


def lab(layer, expr, size, color, curved=True, buf="#000000"):
    s = QgsPalLayerSettings(); s.fieldName = expr; s.isExpression = True
    if curved:
        s.placement = Qgis.LabelPlacement.Curved
    f = QgsTextFormat(); fn = QFont("Arial"); fn.setBold(True); f.setFont(fn); f.setSize(size); f.setColor(QColor(color))
    b = QgsTextBufferSettings(); b.setEnabled(True); b.setSize(1.0); b.setColor(QColor(buf)); f.setBuffer(b); s.setFormat(f)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s)); layer.setLabelsEnabled(True)


def fit(box, pad, w_=W, h_=H):
    cx, cy = box.center().x(), box.center().y(); w = box.width() * pad; h = box.height() * pad
    if w / h < w_ / h_: w = h * w_ / h_
    else: h = w * h_ / w_
    return QgsRectangle(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def render(layers, ext, name, dpi=130, ss=1, w_=W, h_=H, dest=WEB):
    ms = QgsMapSettings(); ms.setLayers(layers); ms.setDestinationCrs(dest); ms.setOutputSize(QSize(w_ * ss, h_ * ss)); ms.setExtent(ext)
    ms.setOutputDpi(dpi * ss); ms.setFlag(QgsMapSettings.DrawLabeling, True); ms.setFlag(QgsMapSettings.Antialiasing, True)
    img = QImage(QSize(w_ * ss, h_ * ss), QImage.Format_ARGB32); img.fill(0); p = QPainter(img)
    j = QgsMapRendererCustomPainterJob(ms, p); j.start(); j.waitForFinished(); p.end()
    (img if ss == 1 else img.scaled(w_, h_, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)).save(OUT + "/" + name)
    return [ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum()]


def idlist(ids):
    return ",".join(str(int(i)) for i in ids) or "-1"


info = {}
ONLY = set(A.get("only") or [])
if not ONLY:
    bw = nofill(QgsVectorLayer(A["boundary"], "b", "ogr"), "#ffffff", 0.8)
    info["boundary"] = render([bw, sat], fit(bb, 1.30), "boundary_raw.png")
    # road connectivity
    C = A["conn"]
    rail = QgsVectorLayer(C + "|layername=rail", "rail", "ogr")
    rs = QgsLineSymbol.createSimple({"color": "#ffffff", "width": "1.3"})
    rs.appendSymbolLayer(QgsSimpleLineSymbolLayer.create({"color": "#222222", "width": "0.8", "customdash": "6;6", "use_custom_dash": "1"}))
    rail.setRenderer(QgsSingleSymbolRenderer(rs))
    mdr = QgsVectorLayer(C + "|layername=roads", "mdr", "ogr"); mdr.setSubsetString(f"osm_id IN ({idlist(A['road_ids'])})")
    mdr.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#d4ff00", "width": "1.4"}))); lab(mdr, '"name"', 11, "#ffffff")
    vr = QgsVectorLayer(C + "|layername=roads", "vr", "ogr"); vr.setSubsetString(f"osm_id IN ({idlist(A['village_road_ids'])})")
    vr.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#ff1a1a", "width": "1.1"}))); lab(vr, '"name"', 11, "#ffff00")
    rb = QgsRectangle(bb); rb.grow(max(1500, bb.width() * 0.4)); info["road"] = render([bw, vr, mdr, rail, sat], fit(rb, 1.0), "road_connectivity_raw.png")
    pole = g.poleOfInaccessibility(5)[0].asPoint(); sc = g.centroid().asPoint()
    info.update(site_c=[sc.x(), sc.y()], site_pole=[pole.x(), pole.y()])
    # region / location
    tal = nofill(QgsVectorLayer(A["admin"] + "|layername=taluk", "t", "ogr"), "#ffffff", 0.45)
    dist = nofill(QgsVectorLayer(A["admin"] + "|layername=district", "d", "ogr"), "#3fb6ff", 1.3)
    rg = QgsRectangle(bb); rg.grow(14000); ext = fit(rg, 1.0)
    render([dist, tal, sat], ext, "region_raw.png", 120, 2)
    lbl = {}
    for f in dist.getFeatures():
        gg = QgsGeometry(f.geometry()); gg.transform(QgsCoordinateTransform(dist.crs(), WEB, P)); vis = gg.intersection(QgsGeometry.fromRect(ext))
        if vis.isEmpty() or vis.area() < ext.width() * ext.height() * 0.03:
            continue
        pt = vis.poleOfInaccessibility(200)[0].asPoint(); lbl[f["district"]] = [pt.x(), pt.y()]
    info["region"] = {"ext": [ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum()], "site_c": [sc.x(), sc.y()], "dlab": lbl}
# thematic maps for the HTML slides (UTM, 2120 x 1555)
MW, MH = 2120, 1555
utm = QgsCoordinateReferenceSystem(f"EPSG:{A['utm']}")
mext = fit(QgsCoordinateTransform(bd.crs(), utm, P).transformBoundingBox(bd.extent()), 1.08, MW, MH)
rgba = lambda h, a: f"{int(h[1:3], 16)},{int(h[3:5], 16)},{int(h[5:7], 16)},{a}"
red = lambda: nofill(QgsVectorLayer(A["boundary"], "b", "ogr"), "#e00000", 0.9)
PAR = A["parcels"]
pv = QgsVectorLayer(PAR, "p", "ogr")
pv.setRenderer(QgsCategorizedSymbolRenderer("village", [QgsRendererCategory(v, QgsFillSymbol.createSimple({"color": rgba(c, 204), "outline_color": "#1a3a5c", "outline_width": "0.25"}), v)
                                                        for v, c in A["village_colors"].items()]))
svm = QgsVectorLayer("Polygon?crs=EPSG:4326&field=survey_no:string", "svs", "memory"); spr = svm.dataProvider(); sg = {}
for f in pv.getFeatures():
    sg.setdefault((f["village"], f["survey_no"]), []).append(f.geometry())
for (v, s), gs in sg.items():
    ft = QgsFeature(svm.fields()); ft.setAttribute("survey_no", s); ft.setGeometry(QgsGeometry.unaryUnion(gs)); spr.addFeature(ft)
svm.updateExtents(); svm.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#1a3a5c", "outline_width": "0.5"})))
lab(svm, '"survey_no"', 6.5, "#ffffff", False, "#1a3a5c")
if not ONLY or "map_village" in ONLY:
    render([svm, pv, red(), sat], mext, "map_village.png", 150, 1, MW, MH, utm)
po = QgsVectorLayer(PAR, "po", "ogr")
po.addExpressionField("CASE WHEN \"ownership\" = 'Govt' THEN 'Government' WHEN \"land_type_english\" IN ('Dry', 'Wet') THEN 'Patta - ' || \"land_type_english\" ELSE 'Patta - Other' END",
                      QgsField("own_class", QVariant.String))
OWN = {"Patta - Dry": "#f5c242", "Patta - Wet": "#4a8df0", "Patta - Other": "#ff9800", "Government": "#2ecc71"}
po.setRenderer(QgsCategorizedSymbolRenderer("own_class", [QgsRendererCategory(k, QgsFillSymbol.createSimple({"color": rgba(c, 208), "outline_color": "#555555", "outline_width": "0.2"}), k) for k, c in OWN.items()]))
if not ONLY or "map_owner" in ONLY:
    render([po, red(), sat], mext, "map_owner.png", 150, 1, MW, MH, utm)
pc = QgsVectorLayer(PAR, "pc", "ogr")
if pc.fields().indexOf("crop_group") >= 0:
    pc.addExpressionField("CASE WHEN \"crop_group\" = 'Cultivated' THEN 'Crop Land' WHEN \"crop_group\" = 'No crop survey record' THEN 'No Survey Data' ELSE 'Non-crop Land' END", QgsField("crop_cls", QVariant.String))
else:
    pc.addExpressionField("'No Survey Data'", QgsField("crop_cls", QVariant.String))
pc.setRenderer(QgsCategorizedSymbolRenderer("crop_cls", [
    QgsRendererCategory("Crop Land", QgsFillSymbol.createSimple({"color": "46,204,113,208", "outline_color": "#555555", "outline_width": "0.2"}), "Crop Land"),
    QgsRendererCategory("Non-crop Land", QgsFillSymbol.createSimple({"color": "245,194,66,208", "outline_color": "#555555", "outline_width": "0.2"}), "Non-crop Land"),
    QgsRendererCategory("No Survey Data", QgsFillSymbol.createSimple({"color": "224,224,224,208", "outline_color": "#555555", "outline_width": "0.2"}), "No Survey Data")]))
if not ONLY or "map_crop" in ONLY:
    render([pc, red(), sat], mext, "map_crop.png", 150, 1, MW, MH, utm)
SOIL_COLORS = ["#1b5e20", "#43a047", "#9ccc65", "#d4e157", "#ffee58", "#ffca28", "#ffa726", "#ff7043", "#e53935", "#8d6e63", "#90a4ae"]
if "map_soil" in ONLY:
    ps = QgsVectorLayer(PAR, "ps", "ogr")
    vals = sorted({f["tharam_label"] for f in ps.getFeatures() if f["tharam_label"]}, key=lambda v: (not v.startswith("Tharam"), int(v.split()[-1]) if v.split()[-1].isdigit() else 99))
    cats = [QgsRendererCategory(v, QgsFillSymbol.createSimple({"color": rgba("#bdbdbd" if not v.startswith("Tharam") else SOIL_COLORS[k % len(SOIL_COLORS)], 210), "outline_color": "#444444", "outline_width": "0.2"}), v)
            for k, v in enumerate(vals)]
    ps.setRenderer(QgsCategorizedSymbolRenderer("tharam_label", cats))
    render([ps, red(), sat], mext, "map_soil.png", 150, 1, MW, MH, utm)
    json.dump({"tharam_colors": {v: ("#bdbdbd" if not v.startswith("Tharam") else SOIL_COLORS[k % len(SOIL_COLORS)]) for k, v in enumerate(vals)}}, open(OUT + "/_soil_colors.json", "w"))
SENS = {"Water body": "#1e88e5", "Channel": "#00acc1", "Temple/Church/Mosque": "#8e24aa", "Burial": "#5d4037", "Village site": "#f4511e", "Forest": "#2e7d32",
        "NH land": "#fdd835", "Well": "#4fc3f7", "Other government poramboke": "#9e9e9e"}
if "map_sensitive" in ONLY:
    base = QgsVectorLayer(PAR, "base", "ogr")
    base.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": "255,255,255,40", "outline_color": "#ffffff", "outline_width": "0.15"})))
    se = QgsVectorLayer(PAR, "se", "ogr"); se.setSubsetString("\"sensitive_cat\" <> ''")
    se.setRenderer(QgsCategorizedSymbolRenderer("sensitive_cat", [QgsRendererCategory(k, QgsFillSymbol.createSimple({"color": rgba(c, 225), "outline_color": "#000000", "outline_width": "0.3"}), k) for k, c in SENS.items()]))
    render([se, base, red(), sat], mext, "map_sensitive.png", 150, 1, MW, MH, utm)
if "map_govt" in ONLY:
    GC = json.load(open(A["govt_colors"], encoding="utf-8"))
    base = QgsVectorLayer(PAR, "base", "ogr")
    base.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": "255,255,255,35", "outline_color": "#ffffff", "outline_width": "0.12"})))
    gv = QgsVectorLayer(PAR, "gv", "ogr"); gv.setSubsetString("\"ownership\" = 'Govt'")
    gv.setRenderer(QgsCategorizedSymbolRenderer("govt_cat", [QgsRendererCategory(k, QgsFillSymbol.createSimple({"color": rgba(c, 225), "outline_color": "#000000", "outline_width": "0.3"}), k) for k, c in GC.items()]))
    render([gv, base, red(), sat], mext, "map_govt.png", 150, 1, MW, MH, utm)
GLVC = {"Up to Rs 3 lakh / acre": "#c8e6c9", "Rs 3 - 5 lakh / acre": "#81c784", "Rs 5 - 10 lakh / acre": "#388e3c", "Above Rs 10 lakh / acre": "#1b5e20",
        "Up to Rs 100 / sq ft": "#ffcdd2", "Rs 100 - 300 / sq ft": "#e57373", "Above Rs 300 / sq ft": "#b71c1c", "Govt / value 0": "#90a4ae", "No GLV data": "#eeeeee"}
if "map_glv" in ONLY:
    pg = QgsVectorLayer(PAR, "pg", "ogr")
    pg.setRenderer(QgsCategorizedSymbolRenderer("glv_band", [QgsRendererCategory(k, QgsFillSymbol.createSimple({"color": rgba(c, 215), "outline_color": "#444444", "outline_width": "0.2"}), k) for k, c in GLVC.items()]))
    render([pg, red(), sat], mext, "map_glv.png", 150, 1, MW, MH, utm)
HOLD = {"2 acres or less": "#fff59d", "More than 2 up to 5 acres": "#ffb74d", "More than 5 up to 10 acres": "#f4511e", "More than 10 acres": "#b71c1c", "Government land": "#90a4ae"}
if "map_holding" in ONLY:
    ph = QgsVectorLayer(PAR, "ph", "ogr")
    ph.setRenderer(QgsCategorizedSymbolRenderer("holding_class", [QgsRendererCategory(k, QgsFillSymbol.createSimple({"color": rgba(c, 215), "outline_color": "#444444", "outline_width": "0.2"}), k) for k, c in HOLD.items()]))
    render([ph, red(), sat], mext, "map_holding.png", 150, 1, MW, MH, utm)
if ONLY:
    json.dump({"only": sorted(ONLY)}, open(OUT + "/_render_only.json", "w"))
else:
    json.dump(info, open(OUT + "/_render_info.json", "w"))
print("rendered", sorted(ONLY) or "all")
app.exitQgis()

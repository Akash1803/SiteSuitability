"""Edge review dialog: Full / Part / Exclude for every survey the boundary cuts, and for the cut subdivisions of a Part survey,
with a picture of each survey (red = your boundary, yellow = subdivisions with their numbers)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from sitesuit.stages import edges

STYLE = "QFrame#card{border:1px solid #888;border-radius:6px} QLabel.h{font-weight:600}"


class EdgeReview(QDialog):
    def __init__(self, site, parent=None):
        super().__init__(parent)
        self.site = site
        self.setWindowTitle(f"Edge review - {site.name}")
        self.resize(1250, 860)
        sv, sub = edges.candidates(site)
        self.sv, self.sub = sv, sub
        dec = edges.decisions(site.site_id)
        _, full_pct = edges.review_state(site.site_id)
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(f"{len(sv)} surveys are cut by your boundary. Choose for each: Full = whole survey at its A-register area, "
                             "Part = only the area inside the line, Exclude = leave it out."))
        v.addLayout(top)
        row = QHBoxLayout()
        row.addWidget(QLabel("Default: Full when at least"))
        self.pct = QSpinBox(); self.pct.setRange(50, 100); self.pct.setValue(int(full_pct)); self.pct.setSuffix(" % inside")
        row.addWidget(self.pct)
        b = QPushButton("Apply this default to all surveys"); b.clicked.connect(self.apply_default); row.addWidget(b); row.addStretch(1)
        self.total = QLabel(); row.addWidget(self.total)
        v.addLayout(row)
        area = QScrollArea(); area.setWidgetResizable(True); inner = QWidget(); self.lay = QVBoxLayout(inner); area.setWidget(inner); v.addWidget(area, 1)
        self.rows = []
        for r in sv.itertuples():
            card = QFrame(); card.setObjectName("card"); card.setStyleSheet(STYLE); g = QGridLayout(card)
            pic = QLabel(); pm = QPixmap(str(site.work / "edges" / f"{r.key}.png"))
            if not pm.isNull():
                pic.setPixmap(pm.scaled(400, 275, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                pic.setText("(no picture)")
            g.addWidget(pic, 0, 0, 3, 1)
            g.addWidget(QLabel(f"<b>{r.village} - survey {r.survey_no}</b>"), 0, 1)
            g.addWidget(QLabel(f"{r.inside_pct:.1f}% inside · {r.inside_acre:.2f} ac inside of {r.puvi_acre:.2f} ac (map)"), 1, 1)
            cb = QComboBox(); cb.addItems(edges.DEC); cb.setCurrentText(dec.get(("survey", r.key), ("Part", None))[0])
            g.addWidget(cb, 0, 2)
            s_ = sub[sub.skey == r.key].sort_values("kide")
            t = QTableWidget(len(s_), 6); t.setHorizontalHeaderLabels(["Subdivision", "Inside %", "Inside ac", "A-reg ac", "Decision", "Typed ac (optional)"])
            t.verticalHeader().hide(); t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); t.setMinimumHeight(min(60 + 30 * len(s_), 260))
            subrows = []
            for k, x in enumerate(s_.itertuples()):
                t.setItem(k, 0, QTableWidgetItem(str(x.kide) + ("" if str(x.geometry_quality).startswith("Exact") else "  (approx. shape)")))
                t.setItem(k, 1, QTableWidgetItem(f"{x.inside_pct:.0f}")); t.setItem(k, 2, QTableWidgetItem(f"{x.parcel_acre:.3f}"))
                t.setItem(k, 3, QTableWidgetItem(f"{x.areg_acre:.3f}" if x.areg_acre == x.areg_acre else "-"))
                c2 = QComboBox(); c2.addItems(edges.DEC); d0, t0 = dec.get(("subdiv", x.unique_id), ("Part", None)); c2.setCurrentText(d0)
                sp = QDoubleSpinBox(); sp.setDecimals(4); sp.setRange(0, 10000); sp.setSpecialValueText("-"); sp.setValue(float(t0 or 0))
                t.setCellWidget(k, 4, c2); t.setCellWidget(k, 5, sp)
                c2.currentTextChanged.connect(self.update_total); sp.valueChanged.connect(self.update_total)
                subrows.append((x.unique_id, c2, sp, x))
            g.addWidget(t, 1, 2, 2, 1)
            t.setEnabled(cb.currentText() == "Part")
            cb.currentTextChanged.connect(lambda txt, tt=t: (tt.setEnabled(txt == "Part"), self.update_total()))
            self.rows.append((r, cb, t, subrows))
            self.lay.addWidget(card)
        self.lay.addStretch(1)
        bt = QHBoxLayout(); bt.addStretch(1)
        ok = QPushButton("Save and continue"); ok.clicked.connect(self.save_ok); bt.addWidget(ok)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject); bt.addWidget(cancel)
        v.addLayout(bt)
        self.update_total()

    def apply_default(self):
        for r, cb, t, subrows in self.rows:
            cb.setCurrentText("Full" if r.inside_pct >= self.pct.value() else "Part")

    def update_total(self, *_):
        acres = 0.0
        for r, cb, t, subrows in self.rows:
            for uid, c2, sp, x in subrows:
                d = cb.currentText() if cb.currentText() != "Part" else c2.currentText()
                if d == "Full":
                    acres += float(x.areg_acre or 0)
                elif d == "Part":
                    acres += float(sp.value() or x.parcel_acre or 0)
        self.total.setText(f"Cut surveys counted: {acres:,.2f} acres")

    def save_ok(self):
        out = {}
        for r, cb, t, subrows in self.rows:
            out[("survey", r.key)] = (cb.currentText(), None, None)
            for uid, c2, sp, x in subrows:
                out[("subdiv", uid)] = (c2.currentText(), (sp.value() or None) if c2.currentText() == "Part" else None, None)
        edges.save(self.site.site_id, out, confirmed=True, full_pct=float(self.pct.value()))
        self.accept()

"""Site Suitability desktop app (PySide6).
Pick the site boundary, press Run: parcels -> CLIP -> A-register (review) -> GLV -> master Excel -> crop -> land cost -> FMB sheets -> maps -> PPT.
Run: python -m gui.app   (or run_app.bat)"""
import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sitesuit import db, loaders, pipeline                     # noqa: E402
from sitesuit.config import SETTINGS                            # noqa: E402
from sitesuit.site import slug                                  # noqa: E402
from sitesuit.stages import STAGES                              # noqa: E402

COLORS = {"done": "#43a047", "running": "#1e88e5", "failed": "#e53935", "waiting": "#fb8c00", "review": "#8e24aa", "pending": "#9e9e9e", "skipped": "#9e9e9e"}


class Worker(QObject):
    log = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal(str)

    def __init__(self, site, stages, options, force, pause):
        super().__init__()
        self.site, self.stages, self.options, self.force, self.pause, self._stop = site, stages, options, force, pause, False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            ctx = pipeline.Ctx(options=self.options, log=self.log.emit, progress_cb=lambda i, n, m: self.progress.emit(i, n, m), stop_flag=lambda: self._stop)
            res = pipeline.run(self.site, self.stages, ctx, force=self.force, pause_at_review=self.pause)
        except Exception as e:
            self.log.emit(traceback.format_exc()); res = f"error: {e}"
        self.finished.emit(res)


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Site Suitability - SIPCOT")
        self.resize(1250, 860)
        self.thread = self.worker = None
        w = QWidget(); self.setCentralWidget(w); v = QVBoxLayout(w)

        # ---- site box ----
        box = QGroupBox("Site"); g = QGridLayout(box)
        self.name = QComboBox(); self.name.setEditable(True); self.name.setMinimumWidth(320)
        self.name.currentTextChanged.connect(self.site_changed)
        self.boundary = QLineEdit(); b1 = QPushButton("Browse..."); b1.clicked.connect(self.pick_boundary)
        self.folder = QLineEdit(); b2 = QPushButton("Browse..."); b2.clicked.connect(self.pick_folder)
        self.show_browser = QCheckBox("Show the browser while fetching from the portals")
        g.addWidget(QLabel("Site name"), 0, 0); g.addWidget(self.name, 0, 1, 1, 2)
        g.addWidget(QLabel("Boundary file (GeoJSON / KML / SHP / GPKG)"), 1, 0); g.addWidget(self.boundary, 1, 1); g.addWidget(b1, 1, 2)
        g.addWidget(QLabel("Project folder"), 2, 0); g.addWidget(self.folder, 2, 1); g.addWidget(b2, 2, 2)
        g.addWidget(self.show_browser, 3, 1)
        v.addWidget(box)

        # ---- review / waiting banner ----
        # fixed colours on every child so the text stays readable in both the light and the dark Windows theme
        self.banner = QFrame(); self.banner.setObjectName("banner")
        self.banner.setStyleSheet("#banner{background:#fff3e0;border:2px solid #ef6c00;border-radius:6px}"
                                  "#banner QLabel{color:#3e2723;background:transparent;font-size:10pt;font-weight:600;padding:4px}"
                                  "#banner QPushButton{color:#ffffff;background:#e65100;border:none;border-radius:4px;padding:8px 16px;font-weight:600}"
                                  "#banner QPushButton:hover{background:#bf360c}")
        bl = QHBoxLayout(self.banner); self.banner_text = QLabel(); self.banner_text.setWordWrap(True)
        self.banner_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.banner_btn = QPushButton(); self.banner_btn.clicked.connect(self.banner_action)
        bl.addWidget(self.banner_text, 1); bl.addWidget(self.banner_btn); self.banner.hide(); self.banner_kind = None
        v.addWidget(self.banner)

        split = QSplitter(Qt.Vertical); v.addWidget(split, 1)
        top = QWidget(); tl = QVBoxLayout(top); tl.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(len(STAGES), 4); self.table.setHorizontalHeaderLabels(["Run", "Stage", "Status", "Result / message"])
        self.table.verticalHeader().hide(); self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 40); self.table.setColumnWidth(1, 230); self.table.setColumnWidth(2, 90)
        for i, s in enumerate(STAGES):
            c = QTableWidgetItem(); c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled); c.setCheckState(Qt.Checked)
            self.table.setItem(i, 0, c); self.table.setItem(i, 1, QTableWidgetItem(f"{i + 1}. {s.TITLE}"))
            self.table.setItem(i, 2, QTableWidgetItem("pending")); self.table.setItem(i, 3, QTableWidgetItem(""))
        self.selected = {s.NAME for s in STAGES}
        self.table.itemChanged.connect(self.tick_changed)
        tl.addWidget(self.table)
        row = QHBoxLayout()
        self.b_run = QPushButton("Run (resume)"); self.b_run.clicked.connect(lambda: self.start(force=False))
        self.b_force = QPushButton("Re-run ticked stages"); self.b_force.clicked.connect(lambda: self.start(force=True))
        self.b_stop = QPushButton("Stop"); self.b_stop.clicked.connect(self.stop); self.b_stop.setEnabled(False)
        self.bar = QProgressBar(); self.bar.setFormat("%v / %m"); self.bar.setValue(0)
        for b in (self.b_run, self.b_force, self.b_stop):
            row.addWidget(b)
        row.addWidget(self.bar, 1); tl.addLayout(row)
        split.addWidget(top)
        self.logbox = QPlainTextEdit(); self.logbox.setReadOnly(True); self.logbox.setFont(QFont("Consolas", 9)); split.addWidget(self.logbox)
        split.setSizes([520, 220])

        # ---- outputs ----
        out = QHBoxLayout()
        for label, fn in (("Open project folder", lambda: self.open_path(self.site().root)), ("Open master Excel", lambda: self.open_path(self.site().master)),
                          ("Open A-register Excel", lambda: self.open_path(self.site().areg_excel)), ("Open land cost", lambda: self.open_path(self.site().landcost)),
                          ("Open PPT", lambda: self.open_path(self.site().ppt)), ("Make PDF (after PPT is confirmed)", self.make_pdf),
                          ("Load crop workbook into the database", self.load_crop)):
            b = QPushButton(label); b.clicked.connect(fn); out.addWidget(b)
        v.addLayout(out)
        self.status = QLabel(); v.addWidget(self.status)
        self.boot()

    # ---------- setup ----------
    def boot(self):
        if not db.ensure_server(self.say):
            QMessageBox.critical(self, "Database", f"Cannot reach PostgreSQL ({SETTINGS.database_url.split('@')[-1]}). Check .env / PG_DATA.")
            return
        db.init_schema()
        with db.connect() as c:
            n = c.execute("SELECT count(*) FROM ref.village").fetchone()[0]
        if not n:
            self.say("first start: loading the Tamil Nadu revenue villages into the database (about a minute) ...")
            QApplication.processEvents(); loaders.load_revenue_villages(self.say)
        self.name.blockSignals(True)
        for _, nm, _, _ in db.list_sites():
            self.name.addItem(nm)
        self.name.setCurrentText(""); self.name.blockSignals(False)
        self.status.setText(f"Database: {SETTINGS.database_url.split('@')[-1]}   |   Projects root: {SETTINGS.projects_root}")

    def say(self, msg):
        self.logbox.appendPlainText(str(msg))

    def site(self):
        nm = self.name.currentText().strip()
        if not nm:
            raise ValueError("enter a site name")
        return pipeline.open_site(nm, self.folder.text().strip() or None)

    def site_changed(self, nm):
        nm = nm.strip()
        known = {n: d for _, n, d, _ in db.list_sites()}
        self.folder.setText(known.get(nm, str(SETTINGS.projects_root / slug(nm)) if nm else ""))
        if nm in known:
            b = Path(known[nm]) / "02_GIS_Data" / f"{slug(nm)}_Outer_Boundary.geojson"
            self.boundary.setText(str(b) if b.exists() else "")
        self.refresh()

    def refresh(self):
        try:
            sid = db.site_id(self.name.currentText().strip())
        except Exception:
            sid = None
        st = db.stage_status(sid) if sid else {}
        for i, s in enumerate(STAGES):
            status, msg = st.get(s.NAME, ("pending", ""))
            it = self.table.item(i, 2); it.setText(status); it.setForeground(QColor(COLORS.get(status, "#000")))
            self.table.item(i, 3).setText(msg or "")
        self.banner.hide()
        for s in STAGES:
            status, msg = st.get(s.NAME, ("pending", ""))
            if status == "waiting":
                self.show_banner(s.NAME, f"{s.TITLE}: {msg}"); break

    def show_banner(self, kind, text):
        self.banner_kind = kind; self.banner_text.setText(text)
        self.banner_btn.setText({"glv": "Open village map Excel", "crop": "Open 06_Crop folder", "review": "Continue to GLV and costs"}.get(kind, "OK"))
        self.banner.show()

    def banner_action(self):
        s = self.site()
        if self.banner_kind == "glv":
            self.open_path(s.glv_map)
        elif self.banner_kind == "crop":
            self.open_path(s.root / "06_Crop")
        elif self.banner_kind == "review":
            self.banner.hide(); self.start(force=False, pause=False)

    # ---------- actions ----------
    def pick_boundary(self):
        f, _ = QFileDialog.getOpenFileName(self, "Site boundary", str(SETTINGS.projects_root), "Vector (*.geojson *.json *.kml *.shp *.gpkg)")
        if f:
            self.boundary.setText(f)
            if not self.name.currentText().strip():
                self.name.setCurrentText(Path(f).stem.replace("_Outer_Boundary", "").replace("_Boundary", ""))

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Project folder", str(SETTINGS.projects_root))
        if d:
            self.folder.setText(d)

    def ticked(self):
        return [s.NAME for i, s in enumerate(STAGES) if self.table.item(i, 0).checkState() == Qt.Checked]

    def tick_changed(self, item):
        if item.column() != 0:
            return
        self.selected = set(self.ticked())          # the running worker reads this before each stage
        nm = STAGES[item.row()].NAME
        if self.thread and self.thread.isRunning():
            self.say(f"[{nm}] {'added to' if nm in self.selected else 'removed from'} this run")

    def start(self, force=False, pause=True):
        try:
            site = self.site()
        except ValueError as e:
            QMessageBox.warning(self, "Site", str(e)); return
        stages = self.ticked()
        if "parcels" in stages and not self.boundary.text().strip():
            QMessageBox.warning(self, "Boundary", "choose the boundary file"); return
        if site.site_id is None and "parcels" not in stages:
            QMessageBox.warning(self, "Site", "this site is new - tick stage 1 (parcels)"); return
        if force and not QMessageBox.question(self, "Re-run", f"Re-run these stages from scratch?\n{', '.join(stages)}") == QMessageBox.Yes:
            return
        # an existing site with a different boundary file: rebuild from stage 1 (otherwise the old boundary would be reused)
        if site.site_id and "parcels" in stages and not force and self.boundary.text().strip():
            new_b = Path(self.boundary.text().strip()).resolve()
            if new_b != Path(site.boundary).resolve():
                if QMessageBox.question(self, "Site already exists",
                                        f"'{site.name}' already exists with another boundary.\n\nUse the new boundary and rebuild every stage?\n"
                                        f"(Choose No and type a new site name to keep the old one.)") != QMessageBox.Yes:
                    return
                db.set_stage(site.site_id, "parcels", "pending", "new boundary chosen")
        opts = {"boundary_file": self.boundary.text().strip(), "show_browser": self.show_browser.isChecked()}
        self.selected = set(stages)
        self.worker = Worker(site, lambda: self.selected, opts, force, pause); self.thread = QThread()
        self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.on_log); self.worker.progress.connect(self.on_progress); self.worker.finished.connect(self.on_done)
        self.worker.finished.connect(self.thread.quit)
        for b in (self.b_run, self.b_force):
            b.setEnabled(False)
        self.b_stop.setEnabled(True); self.banner.hide()
        self.thread.start()

    def stop(self):
        if self.worker:
            self.worker.stop(); self.say("stopping after the current item ...")

    def on_log(self, m):
        self.say(m)
        if m.startswith("[") and ("] done" in m or "] FAILED" in m or "] WAITING" in m or "..." in m):
            self.refresh()

    def on_progress(self, i, n, m):
        self.bar.setMaximum(max(n, 1)); self.bar.setValue(i)
        if m:
            self.statusBar().showMessage(m)

    def on_done(self, res):
        for b in (self.b_run, self.b_force):
            b.setEnabled(True)
        self.b_stop.setEnabled(False); self.refresh()
        if self.name.findText(self.name.currentText()) < 0:
            self.name.addItem(self.name.currentText())
        if res == "review":
            s = self.site(); a = db.get_summary(s.site_id).get("areg", {})
            sens = a.get("sensitive_surveys", [])
            self.show_banner("review", f"A-register done: {a.get('found', 0)} of {a.get('records', 0)} subdivisions found, site {a.get('site_acre', 0):.2f} ac "
                                       f"(patta {a.get('patta_acre', 0):.2f}, govt {a.get('govt_acre', 0):.2f}). {len(sens)} surveys carry sensitive remarks "
                                       f"(see Sensitive_Flags in the A-register Excel). Check it, then continue.")
        elif res == "done":
            self.say("ALL TICKED STAGES DONE")

    def open_path(self, p):
        try:
            p = Path(p)
        except Exception:
            return
        if not p.exists():
            QMessageBox.information(self, "Not there yet", f"{p} does not exist yet"); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def make_pdf(self):
        s = self.site()
        if not s.ppt.exists():
            QMessageBox.information(self, "PDF", "build the PPT first"); return
        if QMessageBox.question(self, "PDF", "Have you reviewed and confirmed the PPT? The PDF is the final hand-off.") != QMessageBox.Yes:
            return
        from sitesuit.stages.ppt import export_pdf
        self.say(f"PDF: {export_pdf(s)}")

    def load_crop(self):
        f, _ = QFileDialog.getOpenFileName(self, "Crop survey workbook (one sheet per season)", str(SETTINGS.projects_root), "Excel (*.xlsx)")
        if f:
            self.say(f"loaded {loaders.load_crop_workbook(f, self.say)} crop entries into crop.survey_record")


def main():
    app = QApplication(sys.argv)
    m = Main(); m.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

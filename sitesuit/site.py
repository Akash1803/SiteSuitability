"""A site's project folder (same layout as Perungalathur / Kattupakkam) and file names."""
import re
from dataclasses import dataclass
from pathlib import Path

FOLDERS = ["01_Source", "02_GIS_Data", "03_CLIP", "04_Tamilnilam", "05_GLV", "06_Crop", "07_PPT_Maps", "08_Output", "09_FMB_Latest", "10_Excel"]


def slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


@dataclass
class Site:
    name: str
    root: Path
    site_id: int = None

    def __post_init__(self):
        self.root = Path(self.root)
        self.s = slug(self.name)

    def make_dirs(self):
        for f in FOLDERS:
            (self.root / f).mkdir(parents=True, exist_ok=True)
        (self.root / "_work").mkdir(exist_ok=True)

    def p(self, folder, fname):
        return self.root / folder / fname

    # ---- fixed file names ----
    @property
    def boundary(self): return self.p("02_GIS_Data", f"{self.s}_Outer_Boundary.geojson")
    @property
    def parcels(self): return self.p("02_GIS_Data", f"{self.s}_Survey_Parcels.geojson")
    @property
    def puvi_fmb(self): return self.p("02_GIS_Data", f"{self.s}_Puvi_FMB.geojson")
    @property
    def subdivisions(self): return self.p("02_GIS_Data", f"{self.s}_Subdivision_Parcels.geojson")
    @property
    def clip_input(self): return self.p("03_CLIP", f"Clip_Input_{self.s}.xlsx")
    @property
    def clip_output(self): return self.p("03_CLIP", f"Clip_Output_{self.s}.xlsx")
    @property
    def areg_raw(self): return self.p("04_Tamilnilam", f"Tamilnilam_Raw_{self.s}.xlsx")
    @property
    def areg_excel(self): return self.p("04_Tamilnilam", f"Tamilnilam_AReg_{self.s}.xlsx")
    @property
    def glv_map(self): return self.p("05_GLV", f"GLV_Village_Map_{self.s}.xlsx")
    @property
    def glv_input(self): return self.p("05_GLV", f"GLV_Input_{self.s}.xlsx")
    @property
    def glv_output(self): return self.p("05_GLV", f"GLV_Output_{self.s}.xlsx")
    @property
    def crop_input(self): return self.p("06_Crop", f"Crop_Input_{self.s}.xlsx")
    @property
    def master(self): return self.p("10_Excel", f"Master_Excel_{self.s}.xlsx")
    @property
    def landcost(self): return self.p("10_Excel", f"{self.s}_Tentative_Land_Cost_GLV.xlsx")
    @property
    def fmb_dir(self): return self.root / "09_FMB_Latest"
    @property
    def maps_dir(self): return self.root / "07_PPT_Maps"
    @property
    def ppt(self): return self.p("08_Output", f"{self.s}_Preliminary_Site_Analysis_PPT.pptx")
    @property
    def work(self): return self.root / "_work"

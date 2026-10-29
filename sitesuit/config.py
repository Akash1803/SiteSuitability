"""Settings from the .env file next to the repo (never committed)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
load_dotenv(REPO / ".env")


def _get(name, default=""):
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    database_url: str = _get("DATABASE_URL")
    puvi_root: Path = Path(_get("PUVI_ROOT", r"D:\Data\Puvi_data\vector"))
    revenue_village_shp: Path = Path(_get("REVENUE_VILLAGE_SHP", r"D:\Data\Puvi_data\village thaluk district BOUNDARIES\TN_Village\revenue_village.shp"))
    sipcot_parks_dir: Path = Path(_get("SIPCOT_PARKS_DIR", r"D:\Projects\Sipcot_Projects\SIPCOT_Park_Layers"))
    projects_root: Path = Path(_get("PROJECTS_ROOT", r"D:\Projects\Sipcot_Projects"))
    ppt_template: Path = Path(_get("PPT_TEMPLATE", r"D:\Data\SiteSuitability_Templates\Preliminary_Site_Analysis_Template.pptx"))
    landcost_template: Path = Path(_get("LANDCOST_TEMPLATE", r"D:\Data\Tentative_allotment_Template.xlsx"))
    qgis_python: Path = Path(_get("QGIS_PYTHON", r"C:\Program Files\QGIS 3.40.10\bin\python-qgis-ltr.bat"))
    fmb_downloader: Path = Path(_get("FMB_DOWNLOADER", r"D:\code\FMB_Downloader\fetch_fmb_gui (1).py"))
    fmb_cookie: str = _get("FMB_COOKIE")
    overpass_url: str = _get("OVERPASS_URL", "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
    pg_bin: Path = Path(_get("PG_BIN", r"D:\Akash\pg17\bin"))
    pg_data: Path = Path(_get("PG_DATA", r"D:\Akash\pg17\data_sitesuit"))


SETTINGS = Settings()

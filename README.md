# Site Suitability (SIPCOT) – end-to-end desktop app

Pick a site boundary, press **Run**, get the full preliminary site analysis:

| # | Stage | Source | Output (site project folder) |
|---|-------|--------|------------------------------|
| 1 | Survey parcels | Puvi vector + FMB (local archive), TN revenue villages | `02_GIS_Data/*_Survey_Parcels.geojson`, `*_Puvi_FMB.geojson`, `03_CLIP/Clip_Input_*.xlsx` |
| 2 | CLIP subdivision list | clip.tn.gov.in (Selenium) | `03_CLIP/Clip_Output_*.xlsx` |
| 3 | A-register | Tamilnilam / tnagrisnet API | `04_Tamilnilam/Tamilnilam_AReg_*.xlsx` – **review point** |
| 4 | Guideline value | TNReginet survey-wise search (Selenium) | `05_GLV/GLV_Output_*.xlsx`, `GLV_Village_Map_*.xlsx` |
| 5 | Master Excel + subdivision parcels | stages 1-4 | `10_Excel/Master_Excel_*.xlsx`, `02_GIS_Data/*_Subdivision_Parcels.geojson` |
| 6 | Crop data | `crop.survey_record` (statewide table) | crop columns in the master + layer; `06_Crop/Crop_Input_*.xlsx` when no data yet |
| 7 | Tentative land cost | team template (RFCTLARR conditions 1 / 2) | `10_Excel/*_Tentative_Land_Cost_GLV.xlsx` |
| 8 | Latest FMB sheets | collabland FMB portal (team downloader) | `09_FMB_Latest/<village>/<survey>/<survey>.pdf` |
| 9 | Connectivity + maps | OpenStreetMap (Overpass), PyQGIS | `_work/render/*` |
| 10 | Slides + PPT | deck template | `07_PPT_Maps/*.png`, `08_Output/*_Preliminary_Site_Analysis_PPT.pptx` |

The PDF is made only after the PPT is confirmed (button in the app / `cli pdf`).

## Rules built in
- **Area**: full surveys use the A-register extent; surveys the boundary cuts use only the area inside the boundary (CLIP and A-register still run on the whole survey).
- **GLV** exactly as TNReginet quotes it (per Square Feet for layouts, per acre for land). Unlisted subdivisions take the lowest sq-ft rate of their survey (layout plots ≤ 500 m²) or else the lowest acre rate; government / poramboke land 0; surveys with no entry take the lowest same-class rate of the village (indicative).
- **Geometry**: exact Puvi FMB plots where the subdivision matches; the rest are approximate strip cuts by A-register extent (column `geometry_quality`).
- Every portal answer is cached in PostgreSQL, so a later site that shares villages / surveys reuses it.

## Setup (this PC)
1. PostgreSQL 17 + PostGIS cluster: `D:\Akash\pg17\data_sitesuit`, port 5433 (the app starts it if it is down).
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in the password and paths (never committed).
4. `python -m sitesuit.cli init-db` (schemas + 17,855 TN revenue villages).
5. Start the app: `run_app.bat` (or `python -m gui.app`).

Command line: `python -m sitesuit.cli run "<site>" --boundary <file>`; `status`, `load-crop <workbook>`, `seed-cache <old project folder>`, `pdf`.

## Database (PostGIS, all EPSG:4326)
`ref.village` · `cadastral.puvi_survey / puvi_fmb / loaded_village` (Puvi loaded per village on first use) · `portal.clip_* / areg / glv / reginet_*` (cache) ·
`crop.survey_record` (statewide crop survey, keyed on LGD village code) · `site.site / stage_run / parcel / summary / document`.
Files (PPT, Excel, FMB PDFs) stay in the site folders; `site.document` records their path, size and checksum.

## Not in the repo
Data, outputs, templates, `.env`, owner names – see `.gitignore`. Templates live in `D:\Data\SiteSuitability_Templates`.

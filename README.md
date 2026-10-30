# Site Suitability (SIPCOT) – end-to-end desktop app

Pick a site boundary, press **Run**, get the full preliminary site analysis:

| # | Stage | Source | Output (site project folder) |
|---|-------|--------|------------------------------|
| 1 | Survey parcels | Puvi vector + FMB (local archive), TN revenue villages | `02_GIS_Data/*_Survey_Parcels.geojson`, `*_Puvi_FMB.geojson`, `03_CLIP/Clip_Input_*.xlsx` |
| 2 | CLIP subdivision list | clip.tn.gov.in (Selenium) | `03_CLIP/Clip_Output_*.xlsx` |
| 3 | A-register | Tamilnilam / tnagrisnet API | `04_Tamilnilam/Tamilnilam_AReg_*.xlsx` – **review point** |
| 4 | Guideline value | TNReginet survey-wise search (Selenium) | `05_GLV/GLV_Output_*.xlsx`, `GLV_Village_Map_*.xlsx` |
| 5 | Master Excel + subdivision parcels | stages 1-4 | `10_Excel/Master_Excel_*.xlsx`, `02_GIS_Data/*_Subdivision_Parcels.geojson` |
| 5b | Edge review | surveys the boundary cuts: Full / Part / Exclude per survey, and per subdivision of a Part survey (optional typed area) - in the app, with a picture of each survey | decisions in `site.edge_decision`; applied to the master Excel + layer (`area_basis`) |
| 6 | Crop data | `crop.survey_record` (statewide table) | crop columns in the master + layer; `06_Crop/Crop_Input_*.xlsx` when no data yet |
| 7 | Tentative land cost | team template (RFCTLARR conditions 1 / 2) | `10_Excel/*_Tentative_Land_Cost_GLV.xlsx` |
| 8 | Latest FMB sheets | collabland FMB portal (team downloader) | `09_FMB_Latest/<village>/<survey>/<survey>.pdf` |
| 9 | Connectivity + maps | OpenStreetMap (Overpass), PyQGIS | `_work/render/*` |
| 10 | Street view points | road network + Google Maps links (photos: your pin_<n>.png or Static API with a company key) | Street View slide + hidden photo slides |
| 11 | Soil + land quality slide | A-register settlement fields (soil class / sort / tharam, assessment Rs/ha, irrigation source) | `Soil_Land_Quality` sheet, soil map + slide |
| 12 | Sensitive land slide | A-register remarks (water body, channel, temple, burial, village site, forest, NH land, well) + govt poramboke | sensitive-land map + slide |
| 13 | Government land classification slide | A-register remarks (odai, railway, pathway, tank ...) or land type + poramboke code; names from `Poramboke_Codes.xlsx` in the templates folder | `Govt_Land_Classification` sheet, map + MIS slide after ownership |
| 14 | GLV map slide | GLV as quoted, banded per acre / per sq ft | map + band table after the GLV summary |
| 15 | Patta holdings slide | A-register patta number + owners | `Patta_Holdings` sheet, holding-size map, largest pattas |
| 16 | Company ownership slide | A-register owners that are companies (Pvt Ltd, realtors, promoters, builders ...) or institutions (trust, diocese, mutt ...) | `Company_Ownership` sheet, map + slide after patta holdings (only when there are such owners) |
| 17 | Boundary dimensions + frontage | boundary + OSM roads / railway | drawn on the Boundary slide: spans, overall extent, perimeter, frontage per road |
| 18 | Regional context slide | major seaports / airport (built-in list), nearest SIPCOT parks, OSM NH network, OSRM road distance + drive time | wide map after the location map |
| 19 | Site photos slide | your photos in `07_PPT_Maps/site_photos`, placed by their GPS (EXIF) | map with numbered thumbnails after street view (only when photos exist) |
| 20 | Executive summary slide | every finished stage | one KPI slide after the title |
| 21 | Slides + PPT | deck template | `07_PPT_Maps/*.png`, `08_Output/*_Preliminary_Site_Analysis_PPT.pptx` |

The PDF is made only after the PPT is confirmed (button in the app / `cli pdf`).
Land Summary is now a village-wise Land Abstract, Ownership splits patta Dry / Wet, Crop lists the area per crop.
Every parcel map carries small survey/subdivision labels. Panels are placed away from the site, the Google Maps link and the slide-show buttons.
Untick a stage and its slides leave the PPT; changing ticks after a run rebuilds only what depends on them.

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

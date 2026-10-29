# Design notes (2026-10-29)

**Why**: the Perungalathur and Kattupakkam site-suitability runs took a day each of hand-run scripts. Akash asked for one desktop app that does the whole
task from a fixed boundary, with PostgreSQL holding all datasets (crop data statewide later, Puvi data, layers, boundaries, PPT records) on his PC and
the code in his GitHub repo.

**Decided by Akash**: desktop app (not a QGIS plugin); no map viewer (the boundary is fixed); government portals fetched live; statewide crop data
will be appended to the database later and the app reads it from there; database on his PC; repo on his GitHub.

**Builder's calls** (change freely):
- Python + PySide6 front end, psycopg 3 + plain SQL, PostGIS on a separate local cluster (port 5433) so the geoapi database is untouched.
- Engine = ten stages with status in `site.stage_run`; each stage is idempotent and resumes; portal answers cached.
- Review point after the A-register; GLV village matching (revenue village -> TNReginet SRO / village id) by name with a score; anything below
  0.8 or ambiguous stops the stage and asks for the ids in `GLV_Village_Map_<site>.xlsx`.
- Map renders through QGIS's own Python (standalone, no running QGIS needed); summary slides via HTML + headless Chrome; PPT from the
  Perungalathur v2 deck layout, dropping the street-view, DC-land and hidden photo slides (no Google Street View use).
- Files stay on disk; the database records documents (path, size, sha256).

**Known limits**
- Approximate subdivision geometry where Puvi FMB is outdated; vectorising the 2026 FMB sheets is a later stage.
- Portals can change; the Selenium code mirrors the scripts that worked in October 2026.
- Nearest SIPCOT park distance is straight-line; road distance needs a manual figure.

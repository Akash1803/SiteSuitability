-- Site suitability store. All geometry EPSG:4326. Safe to run repeatedly.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS cadastral;
CREATE SCHEMA IF NOT EXISTS portal;
CREATE SCHEMA IF NOT EXISTS crop;
CREATE SCHEMA IF NOT EXISTS site;

-- ---------- reference: TN revenue villages (district / taluk / village + LGD codes) ----------
CREATE TABLE IF NOT EXISTS ref.village (
    vcode        text PRIMARY KEY,              -- 'dd_tt_vvv' (district_c _ taluk_code _ village_co)
    district_c   int  NOT NULL,
    taluk_code   int  NOT NULL,
    village_co   text NOT NULL,
    district     text,
    taluk        text,
    village      text,
    lgd_village  text,                          -- LGD village code (crop survey key)
    geom         geometry(MultiPolygon, 4326)
);
CREATE INDEX IF NOT EXISTS village_geom_gix ON ref.village USING gist (geom);
CREATE INDEX IF NOT EXISTS village_lgd_ix ON ref.village (lgd_village);

-- ---------- cadastral: Puvi vector (survey polygons) and Puvi FMB (subdivision plots), loaded per village ----------
CREATE TABLE IF NOT EXISTS cadastral.loaded_village (
    vcode        text PRIMARY KEY,
    vector_file  text,
    fmb_file     text,
    surveys      int,
    fmb_plots    int,
    loaded_at    timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cadastral.puvi_survey (
    id           bigserial PRIMARY KEY,
    vcode        text NOT NULL,
    survey_no    text NOT NULL,
    kide         text,
    geom         geometry(MultiPolygon, 4326)
);
CREATE INDEX IF NOT EXISTS puvi_survey_gix ON cadastral.puvi_survey USING gist (geom);
CREATE INDEX IF NOT EXISTS puvi_survey_key ON cadastral.puvi_survey (vcode, survey_no);
CREATE TABLE IF NOT EXISTS cadastral.puvi_fmb (
    id           bigserial PRIMARY KEY,
    vcode        text NOT NULL,
    kide         text NOT NULL,
    survey_no    text NOT NULL,
    subdiv_no    text,
    geom         geometry(Geometry, 4326)
);
CREATE INDEX IF NOT EXISTS puvi_fmb_gix ON cadastral.puvi_fmb USING gist (geom);
CREATE INDEX IF NOT EXISTS puvi_fmb_key ON cadastral.puvi_fmb (vcode, survey_no);

-- ---------- portal cache: every live fetch is kept, so later sites reuse it ----------
CREATE TABLE IF NOT EXISTS portal.clip_subdivision (
    vcode        text NOT NULL,
    survey_no    text NOT NULL,
    sub_division text NOT NULL,
    status       text,
    fetched_at   timestamptz DEFAULT now(),
    PRIMARY KEY (vcode, survey_no, sub_division)
);
CREATE TABLE IF NOT EXISTS portal.clip_survey_done (   -- a survey whose CLIP list is complete
    vcode        text NOT NULL,
    survey_no    text NOT NULL,
    status       text,
    fetched_at   timestamptz DEFAULT now(),
    PRIMARY KEY (vcode, survey_no)
);
CREATE TABLE IF NOT EXISTS portal.areg (
    vcode        text NOT NULL,
    survey_no    text NOT NULL,
    sub_division text NOT NULL,
    status       text,
    record       jsonb,                         -- all A-register / chitta fields as fetched
    fetched_at   timestamptz DEFAULT now(),
    PRIMARY KEY (vcode, survey_no, sub_division)
);
CREATE TABLE IF NOT EXISTS portal.reginet_village (    -- revenue village -> TNReginet GLV dropdown ids
    vcode           text PRIMARY KEY,
    zone_list_id    text,
    sro_list_id     text,
    sro_name        text,
    village_list_id text,
    reginet_name    text,
    match_score     real,
    confirmed       boolean DEFAULT false,
    updated_at      timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS portal.reginet_option (     -- dropdown listing per district (cache for matching)
    zone_list_id    text NOT NULL,
    sro_list_id     text NOT NULL,
    sro_name        text,
    village_list_id text NOT NULL,
    village_name    text,
    fetched_at      timestamptz DEFAULT now(),
    PRIMARY KEY (zone_list_id, sro_list_id, village_list_id)
);
CREATE TABLE IF NOT EXISTS portal.glv (
    vcode           text NOT NULL,
    survey_no       text NOT NULL,
    row_no          int  NOT NULL,
    subdivision     text,
    value_british   text,
    value_metric    text,
    classification  text,
    effective_date  text,
    status          text,
    fetched_at      timestamptz DEFAULT now(),
    PRIMARY KEY (vcode, survey_no, row_no)
);

-- ---------- crop survey (statewide over time; keyed on LGD village code) ----------
CREATE TABLE IF NOT EXISTS crop.survey_record (
    season                text NOT NULL,        -- 'Rabi 2024', 'Kharif 2024', 'Summer 2025', ...
    crop_survey_id        text NOT NULL,
    lgd_village_code      text NOT NULL,
    survey_number         text,
    sub_division_number   text,
    patta_number          text,
    land_type             text,
    crop_season_type_name text,
    crop_name             text,
    crop_classification   text,
    crop_area_acres       double precision,
    sown_date             text,
    tree_count            text,
    source_file           text,
    loaded_at             timestamptz DEFAULT now(),
    PRIMARY KEY (season, crop_survey_id)
);
CREATE INDEX IF NOT EXISTS crop_key ON crop.survey_record (lgd_village_code, survey_number);

-- ---------- sites, runs, results, documents ----------
CREATE TABLE IF NOT EXISTS site.site (
    id           serial PRIMARY KEY,
    name         text UNIQUE NOT NULL,
    project_dir  text NOT NULL,
    boundary     geometry(MultiPolygon, 4326),
    created_at   timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS site.stage_run (
    site_id      int REFERENCES site.site(id) ON DELETE CASCADE,
    stage        text NOT NULL,
    status       text NOT NULL,                 -- pending / running / done / failed / skipped / waiting
    message      text,
    started_at   timestamptz,
    finished_at  timestamptz,
    PRIMARY KEY (site_id, stage)
);
CREATE TABLE IF NOT EXISTS site.parcel (
    site_id      int REFERENCES site.site(id) ON DELETE CASCADE,
    unique_id    text NOT NULL,
    attrs        jsonb,
    geom         geometry(Geometry, 4326),
    PRIMARY KEY (site_id, unique_id)
);
CREATE INDEX IF NOT EXISTS parcel_gix ON site.parcel USING gist (geom);
CREATE TABLE IF NOT EXISTS site.summary (
    site_id      int PRIMARY KEY REFERENCES site.site(id) ON DELETE CASCADE,
    data         jsonb,
    updated_at   timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS site.document (
    id           serial PRIMARY KEY,
    site_id      int REFERENCES site.site(id) ON DELETE CASCADE,
    kind         text NOT NULL,                 -- ppt / master_excel / landcost / areg_excel / parcels / fmb_sheet ...
    path         text NOT NULL,
    sha256       text,
    bytes        bigint,
    created_at   timestamptz DEFAULT now(),
    UNIQUE (site_id, path)
);

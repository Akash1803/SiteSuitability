"""PostgreSQL / PostGIS access (psycopg 3, plain SQL)."""
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .config import SETTINGS

SCHEMA = Path(__file__).with_name("schema.sql")


@contextmanager
def connect(url=None):
    conn = psycopg.connect(url or SETTINGS.database_url, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_server(log=print):
    """start the local cluster if nobody answers on the configured port"""
    import subprocess, time
    try:
        psycopg.connect(SETTINGS.database_url, connect_timeout=3).close(); return True
    except Exception:
        pass
    ctl = SETTINGS.pg_bin / "pg_ctl.exe"
    if not ctl.exists():
        return False
    log("starting the local PostgreSQL ...")
    subprocess.Popen([str(ctl), "-D", str(SETTINGS.pg_data), "-l", str(SETTINGS.pg_data / "server.log"), "start"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(20):
        time.sleep(1)
        try:
            psycopg.connect(SETTINGS.database_url, connect_timeout=3).close(); return True
        except Exception:
            pass
    return False


def init_schema(url=None):
    with connect(url) as c:
        c.execute(SCHEMA.read_text(encoding="utf-8"))


# ---------- sites / stages ----------
def upsert_site(name, project_dir, boundary_wkt):
    with connect() as c:
        r = c.execute("""INSERT INTO site.site (name, project_dir, boundary) VALUES (%s, %s, ST_Multi(ST_Force2D(ST_GeomFromText(%s, 4326))))
                         ON CONFLICT (name) DO UPDATE SET project_dir = EXCLUDED.project_dir, boundary = EXCLUDED.boundary
                         RETURNING id""", (name, str(project_dir), boundary_wkt)).fetchone()
        return r[0]


def site_id(name):
    with connect() as c:
        r = c.execute("SELECT id FROM site.site WHERE name = %s", (name,)).fetchone()
        return r[0] if r else None


def list_sites():
    with connect() as c:
        return c.execute("SELECT id, name, project_dir, created_at FROM site.site ORDER BY created_at DESC").fetchall()


def set_stage(sid, stage, status, message=None):
    with connect() as c:
        c.execute("""INSERT INTO site.stage_run (site_id, stage, status, message, started_at, finished_at)
                     VALUES (%s, %s, %s, %s, CASE WHEN %s = 'running' THEN now() END, CASE WHEN %s IN ('done','failed','skipped','waiting') THEN now() END)
                     ON CONFLICT (site_id, stage) DO UPDATE SET status = EXCLUDED.status, message = EXCLUDED.message,
                       started_at = COALESCE(CASE WHEN EXCLUDED.status = 'running' THEN now() END, site.stage_run.started_at),
                       finished_at = CASE WHEN EXCLUDED.status IN ('done','failed','skipped','waiting') THEN now() END""",
                  (sid, stage, status, message, status, status))


def stage_status(sid):
    with connect() as c:
        return {s: (st, m) for s, st, m in c.execute("SELECT stage, status, message FROM site.stage_run WHERE site_id = %s", (sid,))}


def save_summary(sid, data):
    with connect() as c:
        c.execute("""INSERT INTO site.summary (site_id, data) VALUES (%s, %s)
                     ON CONFLICT (site_id) DO UPDATE SET data = site.summary.data || EXCLUDED.data, updated_at = now()""", (sid, Jsonb(data)))


def get_summary(sid):
    with connect() as c:
        r = c.execute("SELECT data FROM site.summary WHERE site_id = %s", (sid,)).fetchone()
        return r[0] if r else {}


def register_document(sid, kind, path):
    p = Path(path)
    h = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    with connect() as c:
        c.execute("""INSERT INTO site.document (site_id, kind, path, sha256, bytes) VALUES (%s, %s, %s, %s, %s)
                     ON CONFLICT (site_id, path) DO UPDATE SET kind = EXCLUDED.kind, sha256 = EXCLUDED.sha256, bytes = EXCLUDED.bytes, created_at = now()""",
                  (sid, kind, str(p), h, p.stat().st_size if p.is_file() else None))


def documents(sid):
    with connect() as c:
        return c.execute("SELECT kind, path, created_at FROM site.document WHERE site_id = %s ORDER BY created_at", (sid,)).fetchall()


def save_parcels(sid, gdf):
    """gdf in EPSG:4326 with a unique_id column; all other columns go to attrs."""
    rows = []
    for r in gdf.itertuples(index=False):
        d = r._asdict(); g = d.pop("geometry")
        attrs = {k: (None if v != v else v) if isinstance(v, float) else (v if isinstance(v, (int, str, bool)) or v is None else str(v)) for k, v in d.items()}
        rows.append((sid, d["unique_id"], Jsonb(json.loads(json.dumps(attrs, default=str))), g.wkt if g is not None else None))
    with connect() as c:
        c.execute("DELETE FROM site.parcel WHERE site_id = %s", (sid,))
        with c.cursor() as cur:
            cur.executemany("INSERT INTO site.parcel (site_id, unique_id, attrs, geom) VALUES (%s, %s, %s, ST_Force2D(ST_GeomFromText(%s, 4326)))", rows)

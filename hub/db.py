"""SQLite connection, migrations runner and per-request connection."""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app, g

MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def migrate(conn: sqlite3.Connection, migrations_dir: Path) -> list[int]:
    """Apply numbered .sql files that are not yet in schema_version. Returns applied versions."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")
    done = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    applied = []
    for f in sorted(Path(migrations_dir).glob("*.sql")):
        m = MIGRATION_RE.match(f.name)
        if not m or int(m.group(1)) in done:
            continue
        version = int(m.group(1))
        with conn:
            conn.executescript(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                         (version, datetime.now().isoformat(timespec="seconds")))
        applied.append(version)
    return applied


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

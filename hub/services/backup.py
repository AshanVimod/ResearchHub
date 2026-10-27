"""Backups: SQLite online backup + library zipped, with rotation."""
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import config
from hub.services import settings as st


def backup_dir(s: dict) -> Path:
    return Path(s.get("backup_dir") or config.FALLBACK_BACKUP_DIR)


def last_backup(conn):
    return conn.execute("SELECT * FROM backups ORDER BY made_at DESC LIMIT 1").fetchone()


def make_backup(conn, s: dict, now: datetime, library_dir: Path = config.LIBRARY_DIR) -> Path:
    target_dir = backup_dir(s)
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / f"researchhub_{now:%Y%m%d_%H%M}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / "research.db"
        dest = sqlite3.connect(tmp_db)
        try:
            conn.backup(dest)
        finally:
            dest.close()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp_db, "research.db")
            if library_dir.exists():
                for f in library_dir.rglob("*"):
                    if f.is_file():
                        z.write(f, Path("library") / f.relative_to(library_dir))
    with conn:
        conn.execute("INSERT INTO backups (path, size_bytes, made_at) VALUES (?, ?, ?)",
                     (str(zip_path), zip_path.stat().st_size, now.isoformat(timespec="seconds")))
    rotate(target_dir, st.as_int(s, "backups_to_keep"))
    return zip_path


def rotate(target_dir: Path, keep: int):
    zips = sorted(target_dir.glob("researchhub_*.zip"), key=lambda p: p.name, reverse=True)
    for old in zips[max(keep, 1):]:
        # Only our own backup zips, in the backup folder, are ever removed.
        old.unlink(missing_ok=True)


def due_for_auto(conn, now: datetime) -> bool:
    last = last_backup(conn)
    return last is None or datetime.fromisoformat(last["made_at"]) < now - timedelta(hours=24)


def age_days(conn, now: datetime):
    last = last_backup(conn)
    return None if last is None else (now - datetime.fromisoformat(last["made_at"])).days

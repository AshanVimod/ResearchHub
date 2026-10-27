"""Key/value settings with defaults."""
from datetime import date

import config


def seed_defaults(conn):
    with conn:
        conn.executemany("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                         list(config.DEFAULT_SETTINGS.items()))


def get_all(conn) -> dict:
    values = dict(config.DEFAULT_SETTINGS)
    values.update({r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")})
    return values


def save(conn, values: dict):
    with conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now','localtime')",
                (key, value))


def as_int(s: dict, key: str) -> int:
    try:
        return int(s.get(key) or config.DEFAULT_SETTINGS[key])
    except ValueError:
        return int(config.DEFAULT_SETTINGS[key])


def as_date(s: dict, key: str):
    v = (s.get(key) or "").strip()
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def as_list(s: dict, key: str) -> list[str]:
    return [line.strip() for line in (s.get(key) or "").splitlines() if line.strip()]

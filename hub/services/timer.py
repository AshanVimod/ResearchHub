"""Time entries and the single running timer."""
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta

import config
from hub.services import timeline

STALE_HOURS = 12


class TimerRunning(Exception):
    pass


class NoTimer(Exception):
    pass


def running(conn):
    return conn.execute("SELECT * FROM time_entries WHERE ended_at IS NULL").fetchone()


def start(conn, category: str, now: datetime, task_id=None, note=None) -> int:
    if category not in config.TIME_CATEGORIES:
        raise ValueError(f"Unknown category: {category}")
    try:
        with conn:
            cur = conn.execute("INSERT INTO time_entries (category, started_at, task_id, note) VALUES (?, ?, ?, ?)",
                               (category, now.isoformat(timespec="seconds"), task_id, note))
    except sqlite3.IntegrityError as exc:
        raise TimerRunning() from exc
    return cur.lastrowid


def stop(conn, now: datetime) -> dict:
    row = running(conn)
    if not row:
        raise NoTimer()
    started = datetime.fromisoformat(row["started_at"])
    if now < started:
        now = started
    minutes = round((now - started).total_seconds() / 60)
    with conn:
        conn.execute("UPDATE time_entries SET ended_at = ?, minutes = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                     (now.isoformat(timespec="seconds"), minutes, row["id"]))
    return {"id": row["id"], "minutes": minutes}


def state(conn, now: datetime) -> dict:
    row = running(conn)
    if not row:
        return {"running": False}
    started = datetime.fromisoformat(row["started_at"])
    elapsed = int((now - started).total_seconds())
    return {"running": True, "id": row["id"], "category": row["category"], "started_at": row["started_at"],
            "elapsed": max(elapsed, 0), "stale": elapsed > STALE_HOURS * 3600, "note": row["note"]}


def add_manual(conn, day: date, minutes: int, category: str, note=None, task_id=None, entry_id=None):
    if category not in config.TIME_CATEGORIES:
        raise ValueError(f"Unknown category: {category}")
    if minutes <= 0:
        raise ValueError("Minutes must be positive.")
    started = datetime.combine(day, datetime.min.time()).replace(hour=9)
    ended = started + timedelta(minutes=minutes)
    with conn:
        if entry_id:
            conn.execute("UPDATE time_entries SET category=?, started_at=?, ended_at=?, minutes=?, note=?, task_id=?, "
                         "updated_at=datetime('now','localtime') WHERE id=? AND ended_at IS NOT NULL",
                         (category, started.isoformat(timespec="seconds"), ended.isoformat(timespec="seconds"),
                          minutes, note, task_id, entry_id))
            return entry_id
        cur = conn.execute("INSERT INTO time_entries (category, started_at, ended_at, minutes, note, task_id) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           (category, started.isoformat(timespec="seconds"), ended.isoformat(timespec="seconds"),
                            minutes, note, task_id))
        return cur.lastrowid


def summary(conn, today: date, start: date | None, hours_target: int) -> dict:
    rows = conn.execute("SELECT category, started_at, minutes FROM time_entries WHERE minutes IS NOT NULL").fetchall()
    total = sum(r["minutes"] for r in rows)
    per_cat = defaultdict(int)
    per_week = defaultdict(lambda: defaultdict(int))
    monday = today - timedelta(days=today.weekday())
    this_week = 0
    for r in rows:
        d = date.fromisoformat(r["started_at"][:10])
        per_cat[r["category"]] += r["minutes"]
        if d >= monday:
            this_week += r["minutes"]
        if start:
            wk = timeline.week_of(d, start)
            if 1 <= wk <= config.TOTAL_WEEKS:
                per_week[wk][r["category"]] += r["minutes"]
    week = timeline.display_week(today, start) if start else None
    expected = round(hours_target * week / config.TOTAL_WEEKS, 1) if week else None
    hours = round(total / 60, 1)
    return {
        "hours": hours,
        "this_week": round(this_week / 60, 1),
        "target": hours_target,
        "expected": expected,
        "pct": min(100, round(hours / hours_target * 100, 1)) if hours_target else 0,
        "expected_pct": min(100, round(expected / hours_target * 100, 1)) if expected and hours_target else 0,
        "ahead": (hours - expected) if expected is not None else None,
        "per_category": {c: round(per_cat[c] / 60, 1) for c in config.TIME_CATEGORIES},
        "per_week": {w: {c: round(m / 60, 2) for c, m in cats.items()} for w, cats in per_week.items()},
        "current_week": week,
    }


def chart_data(summary_: dict) -> dict:
    """Chart.js-ready stacked bar of hours per week by category."""
    last = summary_["current_week"] or config.TOTAL_WEEKS
    weeks = list(range(1, max(last, 1) + 1))
    return {
        "labels": [f"W{w}" for w in weeks],
        "datasets": [{"label": c, "data": [summary_["per_week"].get(w, {}).get(c, 0) for w in weeks]}
                     for c in config.TIME_CATEGORIES],
        "pace": round(summary_["target"] / config.TOTAL_WEEKS, 2),
    }

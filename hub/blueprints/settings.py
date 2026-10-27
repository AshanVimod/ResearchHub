"""Settings, milestones and backup."""
import os
import sys
import threading
from datetime import date
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

import config
from hub import util
from hub.db import get_db
from hub.services import backup, timeline
from hub.services import settings as st

bp = Blueprint("settings", __name__, url_prefix="/settings")


DATA_COUNTS = [("diary_entries", "Diary entries"), ("tasks", "Tasks"), ("time_entries", "Time entries"),
               ("refs", "References"), ("files", "Indexed files"), ("dataset_labels", "Label rows"),
               ("experiments", "Experiment runs"), ("viva_questions", "Viva questions"), ("inbox", "Inbox ideas")]


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def data_info(conn) -> dict:
    """Where everything is stored, for the "Your data" panel."""
    data_dir = Path(current_app.config["DB_PATH"]).parent
    db_path = Path(current_app.config["DB_PATH"])
    db_size = sum(_size(Path(str(db_path) + suffix)) for suffix in ("", "-wal"))
    places = [
        ("Database (everything you enter)", db_path, db_size),
        ("Reference PDFs you uploaded", Path(current_app.config.get("LIBRARY_DIR", config.LIBRARY_DIR)), None),
        ("Word, CSV and Excel exports", Path(current_app.config["EXPORTS_DIR"]), None),
        ("Backups", backup.backup_dir(st.get_all(conn)), None),
        ("Log files", data_dir / "app.log", None),
    ]
    rows = [{"label": label, "path": str(p), "size": size if size is not None else _size(p)} for label, p, size in places]
    counts = [(label, conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table, label in DATA_COUNTS]
    return {"dir": str(data_dir), "places": rows, "counts": counts, "can_quit": current_app.config.get("CAN_QUIT", False)}


@bp.get("")
def index():
    conn = get_db()
    return render_template("settings/index.html", form=config.SETTINGS_FORM, values=st.get_all(conn),
                           milestones=conn.execute("SELECT * FROM milestones ORDER BY start_week, end_week").fetchall(),
                           backups=conn.execute("SELECT * FROM backups ORDER BY made_at DESC LIMIT 10").fetchall(),
                           backup_dir=backup.backup_dir(st.get_all(conn)), setup=request.args.get("setup"), errors={},
                           data=data_info(conn))


@bp.post("/open-data")
def open_data():
    """Open the data folder in Explorer (the app's own folder only)."""
    folder = Path(current_app.config["DB_PATH"]).parent
    if sys.platform == "win32":
        os.startfile(folder)  # noqa: S606
    else:
        flash(f"Your data is in {folder}", "info")
    return redirect(url_for("settings.index", _anchor="data"))


@bp.post("/quit")
def quit_app():
    """Stop the background server started by the shortcut. Everything is already saved."""
    if not current_app.config.get("CAN_QUIT"):
        abort(404)
    threading.Timer(0.5, lambda: os._exit(0)).start()  # let this response reach the browser first
    return render_template("settings/stopped.html")


@bp.post("")
def save():
    conn = get_db()
    old = st.get_all(conn)
    values, errors = {}, {}
    for _group, fields in config.SETTINGS_FORM:
        for key, label, kind, _help in fields:
            v = request.form.get(key, "")
            if kind == "bool":
                v = "true" if v else "false"
            v = v.strip() if kind != "textarea" else "\n".join(l.strip() for l in v.splitlines() if l.strip())
            if kind == "date" and v:
                try:
                    date.fromisoformat(v)
                except ValueError:
                    errors[key] = f"{label}: use a valid date."
            if kind == "number" and v and not v.replace(".", "", 1).isdigit():
                errors[key] = f"{label}: enter a number."
            values[key] = v
    if not values["project_start_date"]:
        errors["project_start_date"] = "Project start date is required."
    for n in (1, 2):
        a, b = values[f"semester{n}_start"], values[f"semester{n}_end"]
        if a and b and a > b:
            errors[f"semester{n}_end"] = f"Semester {n} must end after it starts."
    if errors:
        return render_template("settings/index.html", form=config.SETTINGS_FORM, values={**old, **values},
                               milestones=conn.execute("SELECT * FROM milestones ORDER BY start_week").fetchall(),
                               backups=conn.execute("SELECT * FROM backups ORDER BY made_at DESC LIMIT 10").fetchall(),
                               backup_dir=backup.backup_dir(old), setup=None, errors=errors), 422
    st.save(conn, values)
    start = date.fromisoformat(values["project_start_date"])
    if values["project_start_date"] != old.get("project_start_date"):
        timeline.seed_milestones(conn, start)
        timeline.recompute_due_dates(conn, start)
    if values["semester1_start"] != old.get("semester1_start") or values["semester2_start"] != old.get("semester2_start") \
            or values["semester1_end"] != old.get("semester1_end") or values["semester2_end"] != old.get("semester2_end"):
        _rederive_semesters(conn, values)
    flash("Settings saved.", "success")
    return redirect(url_for("dashboard.index") if not old.get("project_start_date") else url_for("settings.index"))


def _rederive_semesters(conn, values):
    from hub.services import diary
    ranges = diary.semester_ranges(values)
    with conn:
        for e in conn.execute("SELECT id, meeting_date FROM diary_entries").fetchall():
            sem, _ = diary.semester_for(date.fromisoformat(e["meeting_date"]), ranges)
            conn.execute("UPDATE diary_entries SET semester = ? WHERE id = ?", (sem, e["id"]))


@bp.post("/milestones/<int:mid>")
def milestone(mid):
    conn = get_db()
    s = st.get_all(conn)
    start = st.as_date(s, "project_start_date")
    status = request.form.get("status")
    due = request.form.get("due_date") or ""
    with conn:
        if status in ("upcoming", "in_progress", "done"):
            conn.execute("UPDATE milestones SET status = ?, updated_at = datetime('now','localtime') WHERE id = ?", (status, mid))
        if request.form.get("reset"):
            row = conn.execute("SELECT end_week FROM milestones WHERE id = ?", (mid,)).fetchone()
            if row and start:
                conn.execute("UPDATE milestones SET due_date = ?, date_overridden = 0 WHERE id = ?",
                             (timeline.milestone_due(start, row["end_week"]).isoformat(), mid))
            flash("Milestone date reset to the computed date.", "info")
        elif due:
            try:
                date.fromisoformat(due)
            except ValueError:
                flash("Use a valid date.", "danger")
                return redirect(url_for("settings.index", _anchor="milestones"))
            current = conn.execute("SELECT due_date FROM milestones WHERE id = ?", (mid,)).fetchone()
            if current and current["due_date"] != due:
                conn.execute("UPDATE milestones SET due_date = ?, date_overridden = 1 WHERE id = ?", (due, mid))
                flash("Milestone date overridden; it will no longer follow the start date.", "success")
    return redirect(request.form.get("next") or url_for("settings.index", _anchor="milestones"))


@bp.post("/backup")
def make_backup():
    conn = get_db()
    try:
        path = backup.make_backup(conn, st.get_all(conn), util.now())
        flash(f"Backup written to {path}", "success")
    except OSError as exc:
        current_app.logger.exception("Backup failed")
        flash(f"Backup failed: {exc}. Check the backup folder in Settings.", "danger")
    return redirect(request.form.get("next") or url_for("settings.index", _anchor="backup"))

"""Module C: time log page."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import config
from hub import util
from hub.db import get_db
from hub.services import settings as st
from hub.services import timer

bp = Blueprint("time", __name__, url_prefix="/time")


@bp.get("")
def index():
    conn = get_db()
    s = st.get_all(conn)
    summary = timer.summary(conn, util.today(), st.as_date(s, "project_start_date"), st.as_int(s, "hours_target"))
    cat = request.args.get("category", "")
    sql, args = ("SELECT e.*, t.title AS task_title FROM time_entries e LEFT JOIN tasks t ON t.id = e.task_id "
                 "WHERE e.ended_at IS NOT NULL"), []
    if cat in config.TIME_CATEGORIES:
        sql += " AND e.category = ?"
        args.append(cat)
    entries = conn.execute(sql + " ORDER BY e.started_at DESC LIMIT 200", args).fetchall()
    edit_id = request.args.get("edit", type=int)
    editing = conn.execute("SELECT * FROM time_entries WHERE id = ? AND ended_at IS NOT NULL", (edit_id,)).fetchone() if edit_id else None
    open_tasks = conn.execute("SELECT id, title FROM tasks WHERE status != 'done' ORDER BY title").fetchall()
    return render_template("time/index.html", summary=summary, chart=timer.chart_data(summary), entries=entries,
                           editing=editing, open_tasks=open_tasks, f_cat=cat, errors={})


@bp.post("")
def save():
    conn = get_db()
    errors = {}
    try:
        day = date.fromisoformat(request.form.get("day", ""))
    except ValueError:
        errors["day"] = "Enter a date."
        day = None
    hours = request.form.get("hours", type=float) or 0
    minutes = request.form.get("minutes", type=int) or 0
    total = round(hours * 60) + minutes
    if total <= 0:
        errors["minutes"] = "Enter the time spent (hours and/or minutes)."
    category = request.form.get("category")
    if category not in config.TIME_CATEGORIES:
        errors["category"] = "Choose a category."
    if errors:
        for msg in errors.values():
            flash(msg, "danger")
        return redirect(url_for("time.index"))
    timer.add_manual(conn, day, total, category, (request.form.get("note") or "").strip() or None,
                     request.form.get("task_id", type=int) or None, request.form.get("entry_id", type=int) or None)
    flash(f"Logged {util.hours(total)} of {category}.", "success")
    return redirect(url_for("time.index"))


@bp.post("/<int:entry_id>/delete")
def delete(entry_id):
    conn = get_db()
    if not conn.execute("SELECT 1 FROM time_entries WHERE id = ?", (entry_id,)).fetchone():
        abort(404)
    with conn:
        conn.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))
    flash("Time entry deleted.", "info")
    return redirect(url_for("time.index"))

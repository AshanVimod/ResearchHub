"""JSON API: calendar feed, task moves, timer, time summary."""
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

import config
from hub import util
from hub.db import get_db
from hub.services import settings as st
from hub.services import tasks as task_svc
from hub.services import timer

bp = Blueprint("api", __name__, url_prefix="/api")


def _range():
    def parse(v, fallback):
        try:
            return date.fromisoformat((v or "")[:10])
        except ValueError:
            return fallback
    today = util.today()
    return parse(request.args.get("start"), today - timedelta(days=45)), parse(request.args.get("end"), today + timedelta(days=45))


@bp.get("/calendar")
def calendar():
    conn = get_db()
    start, end = _range()
    a, b = start.isoformat(), end.isoformat()
    events = []
    for m in conn.execute("SELECT * FROM milestones WHERE due_date BETWEEN ? AND ? AND code != 'DIARY'", (a, b)):
        events.append({"id": f"m{m['id']}", "title": m["title"], "start": m["due_date"], "allDay": True,
                       "classNames": ["ev-milestone", f"ev-{m['status']}"], "url": "/settings#milestones",
                       "extendedProps": {"kind": "Milestone"}})
    for e in conn.execute("SELECT * FROM diary_entries WHERE meeting_date BETWEEN ? AND ?", (a, b)):
        events.append({"id": f"d{e['id']}", "title": ("Signed meeting" if e["signed"] else "Supervisor meeting"),
                       "start": e["meeting_date"], "allDay": True, "url": f"/diary/{e['id']}",
                       "classNames": ["ev-meeting"], "extendedProps": {"kind": "Meeting"}})
    for e in conn.execute("SELECT * FROM diary_entries WHERE next_meeting_date BETWEEN ? AND ?", (a, b)):
        events.append({"id": f"n{e['id']}", "title": "Planned meeting", "start": e["next_meeting_date"], "allDay": True,
                       "url": f"/diary/{e['id']}", "classNames": ["ev-planned"], "extendedProps": {"kind": "Planned meeting"}})
    today = util.today().isoformat()
    for t in conn.execute("SELECT * FROM tasks WHERE due_date BETWEEN ? AND ?", (a, b)):
        cls = ["ev-task", f"ev-{t['status']}"]
        if t["status"] != "done" and t["due_date"] < today:
            cls.append("ev-overdue")
        events.append({"id": f"t{t['id']}", "title": t["title"], "start": t["due_date"], "allDay": True,
                       "editable": True, "classNames": cls, "url": f"/tasks?edit={t['id']}",
                       "extendedProps": {"kind": "Task", "taskId": t["id"]}})
    return jsonify(events)


@bp.patch("/tasks/<int:task_id>")
def patch_task(task_id):
    body = request.get_json(silent=True) or {}
    kwargs = {}
    if "status" in body:
        kwargs["status"] = body["status"]
    if "position" in body:
        kwargs["position"] = int(body["position"])
    if "due_date" in body:
        due = body["due_date"]
        if due:
            try:
                date.fromisoformat(due)
            except (TypeError, ValueError):
                return jsonify(error="Invalid due_date"), 400
        kwargs["due_date"] = due or None
    try:
        task_svc.move(get_db(), task_id, util.now(), **kwargs)
    except KeyError:
        return jsonify(error="Task not found"), 404
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(ok=True)


@bp.get("/timer")
def timer_state():
    return jsonify(timer.state(get_db(), util.now()))


@bp.post("/timer/start")
def timer_start():
    body = request.get_json(silent=True) or request.form
    category = body.get("category")
    if category not in config.TIME_CATEGORIES:
        return jsonify(error="Choose a category."), 400
    try:
        timer.start(get_db(), category, util.now(), body.get("task_id") or None, body.get("note") or None)
    except timer.TimerRunning:
        return jsonify(error="A timer is already running."), 409
    return jsonify(timer.state(get_db(), util.now()))


@bp.post("/timer/stop")
def timer_stop():
    body = request.get_json(silent=True) or request.form
    when = util.now()
    if body.get("ended_at"):
        try:
            when = datetime.fromisoformat(body["ended_at"])
        except ValueError:
            return jsonify(error="Invalid end time."), 400
    try:
        result = timer.stop(get_db(), when)
    except timer.NoTimer:
        return jsonify(error="No timer is running."), 409
    return jsonify(ok=True, **result)


@bp.get("/time/summary")
def time_summary():
    conn = get_db()
    s = st.get_all(conn)
    summary = timer.summary(conn, util.today(), st.as_date(s, "project_start_date"), st.as_int(s, "hours_target"))
    if request.args.get("group") == "category":
        return jsonify(labels=config.TIME_CATEGORIES, data=[summary["per_category"][c] for c in config.TIME_CATEGORIES])
    return jsonify(timer.chart_data(summary))


@bp.post("/inbox")
def inbox_add():
    text = ((request.get_json(silent=True) or request.form).get("text") or "").strip()
    if not text:
        return jsonify(error="Type something to capture."), 400
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO inbox (text) VALUES (?)", (text,))
    count = conn.execute("SELECT COUNT(*) FROM inbox WHERE processed = 0").fetchone()[0]
    return jsonify(ok=True, count=count)

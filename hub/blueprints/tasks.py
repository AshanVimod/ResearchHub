"""Module C: tasks kanban."""
from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from hub import util
from hub.db import get_db
from hub.services import tasks as svc

bp = Blueprint("tasks", __name__, url_prefix="/tasks")

DUE_WINDOWS = {"overdue": "Overdue", "today": "Due today", "week": "Due in 7 days", "none": "No due date"}


def _form():
    data = {
        "title": (request.form.get("title") or "").strip(),
        "description": (request.form.get("description") or "").strip(),
        "priority": request.form.get("priority", type=int) or 2,
        "due_date": request.form.get("due_date") or None,
        "milestone_id": request.form.get("milestone_id", type=int) or None,
        "chapter_id": request.form.get("chapter_id", type=int) or None,
    }
    errors = {}
    if not data["title"]:
        errors["title"] = "Give the task a title."
    if data["priority"] not in (1, 2, 3):
        errors["priority"] = "Priority must be 1, 2 or 3."
    return data, errors


def _chapters():
    return get_db().execute("SELECT id, ordinal, title FROM chapters WHERE ordinal > 0 ORDER BY ordinal").fetchall()


def _milestones():
    return get_db().execute("SELECT id, title FROM milestones WHERE code != 'DIARY' ORDER BY start_week").fetchall()


@bp.get("")
def index():
    conn = get_db()
    today = util.today()
    sql = ("SELECT t.*, m.title AS milestone_title FROM tasks t LEFT JOIN milestones m ON m.id = t.milestone_id WHERE 1=1")
    args = []
    f = {k: request.args.get(k, "") for k in ("milestone", "chapter", "tag", "due", "view")}
    if f["milestone"].isdigit():
        sql += " AND t.milestone_id = ?"
        args.append(int(f["milestone"]))
    if f["chapter"].isdigit():
        sql += " AND t.chapter_id = ?"
        args.append(int(f["chapter"]))
    if f["tag"]:
        sql += (" AND t.id IN (SELECT tg.item_id FROM taggings tg JOIN tags x ON x.id = tg.tag_id "
                "WHERE tg.item_type = 'task' AND x.name = ?)")
        args.append(f["tag"])
    if f["due"] == "overdue":
        sql += " AND t.due_date < ? AND t.status != 'done'"
        args.append(today.isoformat())
    elif f["due"] == "today":
        sql += " AND t.due_date = ?"
        args.append(today.isoformat())
    elif f["due"] == "week":
        sql += " AND t.due_date BETWEEN ? AND ?"
        args += [today.isoformat(), (today + timedelta(days=7)).isoformat()]
    elif f["due"] == "none":
        sql += " AND t.due_date IS NULL"
    rows = conn.execute(sql + " ORDER BY t.position, t.id", args).fetchall()
    columns = {s: [r for r in rows if r["status"] == s] for s in svc.STATUSES}
    tags = [r["name"] for r in conn.execute("SELECT DISTINCT x.name FROM tags x JOIN taggings tg ON tg.tag_id = x.id "
                                            "WHERE tg.item_type = 'task' ORDER BY x.name")]
    return render_template("tasks/index.html", columns=columns, rows=rows, f=f, tags=tags,
                           task_tags=svc.tags_by_task(conn), milestones=_milestones(), chapters=_chapters(), due_windows=DUE_WINDOWS,
                           filtered=any(f[k] for k in ("milestone", "chapter", "tag", "due")))


@bp.get("/new")
def new():
    task = {"id": None, "title": "", "description": "", "priority": 2, "due_date": request.args.get("due", ""),
            "milestone_id": None, "chapter_id": request.args.get("chapter", type=int),
            "status": request.args.get("status", "todo")}
    return render_template("tasks/_form.html", task=task, tags="", errors={}, milestones=_milestones(), chapters=_chapters())


@bp.get("/<int:task_id>/edit")
def edit(task_id):
    conn = get_db()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone() or abort(404)
    tags = ", ".join(svc.tags_by_task(conn).get(task_id, []))
    return render_template("tasks/_form.html", task=task, tags=tags, errors={}, milestones=_milestones(), chapters=_chapters())


def _save(task_id=None):
    conn = get_db()
    data, errors = _form()
    status = request.form.get("status")
    if errors:
        task = dict(data, id=task_id, status=status or "todo")
        return render_template("tasks/_form.html", task=task, tags=request.form.get("tags", ""),
                               errors=errors, milestones=_milestones(), chapters=_chapters()), 422
    task_id = svc.save(conn, data, util.now(), task_id, status)
    svc.set_tags(conn, task_id, (request.form.get("tags") or "").split(","))
    flash("Task saved.", "success")
    if request.headers.get("HX-Request"):
        return "", 204, {"HX-Refresh": "true"}
    return redirect(request.form.get("next") or url_for("tasks.index"))


@bp.post("")
def create():
    return _save()


@bp.post("/<int:task_id>")
def update(task_id):
    if not get_db().execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone():
        abort(404)
    return _save(task_id)


@bp.post("/<int:task_id>/delete")
def delete(task_id):
    svc.delete(get_db(), task_id)
    flash("Task deleted.", "info")
    return redirect(request.form.get("next") or url_for("tasks.index"))

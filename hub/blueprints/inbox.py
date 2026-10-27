"""Idea inbox: quick capture and conversion to a task, reference note or diary agenda point."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from hub import util
from hub.db import get_db
from hub.services import refs as ref_svc
from hub.services import settings as st
from hub.services import tasks as task_svc

bp = Blueprint("inbox", __name__, url_prefix="/inbox")
PENDING_AGENDA = "pending_agenda"  # settings key: agenda points waiting for the next new diary entry


def pending_agenda(conn) -> list[str]:
    return st.as_list(st.get_all(conn), PENDING_AGENDA)


@bp.get("")
def index():
    conn = get_db()
    show = request.args.get("show", "open")
    items = conn.execute("SELECT * FROM inbox WHERE processed = ? ORDER BY id DESC",
                         (1 if show == "archived" else 0,)).fetchall()
    return render_template(
        "inbox/index.html", items=items, show=show,
        refs=conn.execute("SELECT id, cite_key, title FROM refs ORDER BY cite_key").fetchall(),
        entries=conn.execute("SELECT id, meeting_date FROM diary_entries ORDER BY meeting_date DESC LIMIT 8").fetchall(),
        pending=pending_agenda(conn))


@bp.post("")
def add():
    text = (request.form.get("text") or "").strip()
    if text:
        conn = get_db()
        with conn:
            conn.execute("INSERT INTO inbox (text) VALUES (?)", (text,))
        flash("Captured.", "success")
    return redirect(request.form.get("next") or url_for("inbox.index"))


def _note_line(text: str) -> str:
    return f"- {text} *(from inbox, {util.today().isoformat()})*"


@bp.post("/<int:item_id>/<action>")
def process(item_id, action):
    conn = get_db()
    item = conn.execute("SELECT * FROM inbox WHERE id = ?", (item_id,)).fetchone() or abort(404)
    text = item["text"]
    if action == "task":
        task_id = task_svc.save(conn, {"title": text[:200], "description": text if len(text) > 200 else None, "priority": 2}, util.now())
        flash("Turned into a task.", "success")
        _done(conn, item_id)
        return redirect(url_for("tasks.index", edit=task_id) if request.form.get("open") else url_for("inbox.index"))
    if action == "ref":
        ref_id = request.form.get("ref_id", type=int)
        ref = conn.execute("SELECT id, cite_key, notes FROM refs WHERE id = ?", (ref_id,)).fetchone()
        if not ref:
            flash("Choose a reference to add the note to.", "warning")
            return redirect(url_for("inbox.index"))
        notes = "\n".join(x for x in (ref["notes"], _note_line(text)) if x)
        ref_svc.update_fields(conn, ref["id"], {"notes": notes})
        flash(f"Added to the notes of {ref['cite_key']}.", "success")
    elif action == "agenda":
        target = request.form.get("entry", "next")
        if target == "next":
            st.save(conn, {PENDING_AGENDA: "\n".join(pending_agenda(conn) + [text.replace("\n", " ")])})
            flash("Added to the agenda for your next diary entry.", "success")
        else:
            entry = conn.execute("SELECT id, agenda, meeting_date FROM diary_entries WHERE id = ?", (int(target) if target.isdigit() else 0,)).fetchone()
            if not entry:
                abort(404)
            with conn:
                conn.execute("UPDATE diary_entries SET agenda = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                             ("\n".join(x for x in (entry["agenda"], f"- {text}") if x), entry["id"]))
            flash(f"Added to the agenda of the {util.nice_date(entry['meeting_date'])} meeting.", "success")
    elif action == "archive":
        flash("Archived.", "info")
    elif action == "restore":
        with conn:
            conn.execute("UPDATE inbox SET processed = 0 WHERE id = ?", (item_id,))
        return redirect(url_for("inbox.index", show="archived"))
    else:
        abort(404)
    _done(conn, item_id)
    return redirect(url_for("inbox.index"))


@bp.post("/agenda/clear")
def clear_agenda():
    st.save(get_db(), {PENDING_AGENDA: ""})
    flash("Pending agenda points cleared.", "info")
    return redirect(url_for("inbox.index"))


def _done(conn, item_id):
    with conn:
        conn.execute("UPDATE inbox SET processed = 1, updated_at = datetime('now','localtime') WHERE id = ?", (item_id,))

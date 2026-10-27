"""Module B: supervisor diary."""
from datetime import date

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for

from hub import util
from hub.db import get_db
from hub.services import diary as svc
from hub.services import refs as ref_svc
from hub.services import settings as st

bp = Blueprint("diary", __name__, url_prefix="/diary")
PENDING_AGENDA = "pending_agenda"


def _link_choices(entry_id=None):
    conn = get_db()
    linked_refs = ref_svc.linked(conn, "diary", entry_id, "ref") if entry_id else []
    linked_files = ref_svc.linked(conn, "diary", entry_id, "file") if entry_id else []
    return {"refs": conn.execute("SELECT id, cite_key, title FROM refs ORDER BY cite_key").fetchall(),
            "files": conn.execute("SELECT id, rel_path FROM files WHERE text_status != 'missing' AND ext IN ('.pdf', '.docx', '.xlsx', '.ipynb') "
                                  "ORDER BY rel_path COLLATE NOCASE").fetchall(),
            "linked_refs": linked_refs, "linked_files": linked_files}


def _save_links(entry_id):
    """Replace this entry's ref/file links with the form selection."""
    conn = get_db()
    for kind, field in (("ref", "link_refs"), ("file", "link_files")):
        wanted = {int(v) for v in request.form.getlist(field) if v.isdigit()}
        current = set(ref_svc.linked(conn, "diary", entry_id, kind))
        for other in current - wanted:
            ref_svc.unlink(conn, "diary", entry_id, kind, other)
            ref_svc.unlink(conn, kind, other, "diary", entry_id)
        for other in wanted - current:
            ref_svc.link(conn, "diary", entry_id, kind, other)


def _get(entry_id):
    row = get_db().execute("SELECT * FROM diary_entries WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        abort(404)
    return row


def _actions_from_form():
    titles = request.form.getlist("action_title")
    dues = request.form.getlist("action_due")
    return list(zip(titles, dues + [""] * (len(titles) - len(dues))))


def _form_data():
    data = {f: (request.form.get(f) or "").strip() for f in svc.FIELDS}
    errors = {}
    try:
        date.fromisoformat(data["meeting_date"])
    except ValueError:
        errors["meeting_date"] = "Enter the meeting date."
    if data["next_meeting_date"]:
        try:
            date.fromisoformat(data["next_meeting_date"])
        except ValueError:
            errors["next_meeting_date"] = "Use a valid date."
    if data["mode"] and data["mode"] not in svc.MODES:
        errors["mode"] = "Choose a meeting mode."
    return data, errors


@bp.get("")
def index():
    conn = get_db()
    s = st.get_all(conn)
    sem = request.args.get("semester", type=int)
    signed = request.args.get("signed")
    sql, args = "SELECT * FROM diary_entries WHERE 1=1", []
    if sem:
        sql += " AND semester = ?"
        args.append(sem)
    if signed in ("0", "1"):
        sql += " AND signed = ?"
        args.append(int(signed))
    entries = conn.execute(sql + " ORDER BY meeting_date DESC, id DESC", args).fetchall()
    every = conn.execute("SELECT semester, signed FROM diary_entries").fetchall()
    actions = {}
    for r in conn.execute("SELECT diary_entry_id, COUNT(*) n, SUM(status='done') d FROM tasks "
                          "WHERE diary_entry_id IS NOT NULL GROUP BY diary_entry_id"):
        actions[r["diary_entry_id"]] = (r["d"] or 0, r["n"])
    return render_template("diary/index.html", entries=entries, actions=actions,
                           counts={n: svc.counts(every, n) for n in (1, 2)},
                           required=st.as_int(s, "signed_meetings_per_semester"),
                           current=svc.current_semester(util.today(), svc.semester_ranges(s)),
                           f_sem=sem, f_signed=signed, modes=svc.MODES)


@bp.get("/new")
def new():
    s = st.get_all(get_db())
    entry = {f: "" for f in svc.FIELDS}
    pending = st.as_list(s, PENDING_AGENDA)
    entry.update(meeting_date=util.today().isoformat(), mode="in_person", attendees=s["supervisor_name"],
                 agenda="\n".join(f"- {p}" for p in pending))
    return render_template("diary/form.html", entry=entry, actions=[], errors={}, modes=svc.MODES,
                           pending_count=len(pending), **_link_choices())


@bp.post("")
def create():
    conn = get_db()
    data, errors = _form_data()
    actions = _actions_from_form()
    if errors:
        return render_template("diary/form.html", entry=data, errors=errors, modes=svc.MODES,
                               actions=[{"title": t, "due_date": d} for t, d in actions], **_link_choices()), 422
    entry_id, warning, created = svc.save_entry(conn, data, actions, st.get_all(conn))
    _save_links(entry_id)
    if request.form.get("used_pending"):
        st.save(conn, {PENDING_AGENDA: ""})  # the inbox agenda points are now in this entry
    if warning:
        flash(warning, "warning")
    flash(f"Diary entry saved{f', {created} action task' + ('s' if created != 1 else '') + ' created' if created else ''}.", "success")
    return redirect(url_for("diary.view", entry_id=entry_id))


@bp.get("/<int:entry_id>")
def view(entry_id):
    conn = get_db()
    entry = _get(entry_id)
    actions = conn.execute("SELECT * FROM tasks WHERE diary_entry_id = ? ORDER BY id", (entry_id,)).fetchall()
    edit = request.args.get("edit") == "1"
    if edit:
        return render_template("diary/form.html", entry=entry, actions=actions, errors={}, modes=svc.MODES,
                               **_link_choices(entry_id))
    links = _link_choices(entry_id)
    q = lambda table, ids: conn.execute(f"SELECT * FROM {table} WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall() if ids else []  # noqa: E731
    return render_template("diary/view.html", entry=entry, actions=actions, modes=svc.MODES,
                           linked_refs=q("refs", links["linked_refs"]), linked_files=q("files", links["linked_files"]))


@bp.post("/<int:entry_id>")
def update(entry_id):
    conn = get_db()
    entry = _get(entry_id)
    data, errors = _form_data()
    actions = _actions_from_form()
    if errors:
        existing = conn.execute("SELECT * FROM tasks WHERE diary_entry_id = ? ORDER BY id", (entry_id,)).fetchall()
        merged = dict(entry)
        merged.update(data)
        return render_template("diary/form.html", entry=merged, errors=errors, modes=svc.MODES,
                               actions=existing, **_link_choices(entry_id)), 422
    _, warning, created = svc.save_entry(conn, data, actions, st.get_all(conn), entry_id)
    _save_links(entry_id)
    if warning:
        flash(warning, "warning")
    flash("Entry updated." + (f" {created} new action task{'s' if created != 1 else ''} created." if created else ""), "success")
    return redirect(url_for("diary.view", entry_id=entry_id))


@bp.post("/<int:entry_id>/sign")
def sign(entry_id):
    conn = get_db()
    entry = _get(entry_id)
    if request.form.get("unsign"):
        with conn:
            conn.execute("UPDATE diary_entries SET signed = 0, signed_date = NULL, updated_at = datetime('now','localtime') WHERE id = ?", (entry_id,))
        flash("Signature removed.", "info")
    else:
        signed_date = request.form.get("signed_date") or util.today().isoformat()
        with conn:
            conn.execute("UPDATE diary_entries SET signed = 1, signed_date = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                         (signed_date, entry_id))
        flash(f"Meeting of {util.nice_date(entry['meeting_date'])} marked as signed.", "success")
    return redirect(request.form.get("next") or url_for("diary.view", entry_id=entry_id))


@bp.post("/<int:entry_id>/tasks")
def make_tasks(entry_id):
    conn = get_db()
    _get(entry_id)
    with conn:
        created = svc.sync_actions(conn, entry_id, _actions_from_form())
    flash(f"{created} task{'s' if created != 1 else ''} created." if created else "No new tasks; they already exist.", "info")
    return redirect(url_for("diary.view", entry_id=entry_id))


@bp.post("/<int:entry_id>/delete")
def delete(entry_id):
    conn = get_db()
    _get(entry_id)
    with conn:
        conn.execute("DELETE FROM links WHERE (from_type='diary' AND from_id=?) OR (to_type='diary' AND to_id=?)", (entry_id, entry_id))
        conn.execute("DELETE FROM diary_entries WHERE id = ?", (entry_id,))
    flash("Diary entry deleted. Its action tasks were kept.", "info")
    return redirect(url_for("diary.index"))


@bp.get("/<int:entry_id>/export.docx")
def export_one(entry_id):
    conn = get_db()
    path = svc.export_entry(conn, _get(entry_id), st.get_all(conn), current_app.config["EXPORTS_DIR"], util.today())
    return send_file(path, as_attachment=True, download_name=path.name)


@bp.get("/export.docx")
def export_semester():
    conn = get_db()
    sem = request.args.get("semester", type=int)
    if sem not in (1, 2):
        abort(404)
    path = svc.export_semester(conn, sem, st.get_all(conn), current_app.config["EXPORTS_DIR"], util.today())
    return send_file(path, as_attachment=True, download_name=path.name)

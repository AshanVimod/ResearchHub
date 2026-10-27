"""Module G: thesis tracker and checklists."""
from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from hub import util
from hub.db import get_db
from hub.services import settings as st
from hub.services import thesis as svc

bp = Blueprint("thesis", __name__, url_prefix="/thesis")
LIST_CODES = set(svc.CHECKLISTS) | {"VIVA_SLIDES"}


def _back_to_list(code):
    if code == "VIVA_SLIDES":
        return redirect(url_for("viva.index", _anchor="slides"))
    return redirect(url_for("thesis.index", _anchor=f"list-{code}"))


@bp.get("")
def index():
    conn = get_db()
    s = st.get_all(conn)
    path = s.get("thesis_docx_path", "").strip()
    state = svc.recount(conn, Path(path) if path else None, util.now(), force=request.args.get("recount") == "1")
    chapters = conn.execute("SELECT * FROM chapters ORDER BY ordinal").fetchall()
    last = svc.last_count(conn)
    comments = {}
    for c in conn.execute("SELECT * FROM chapter_comments ORDER BY resolved, id DESC"):
        comments.setdefault(c["chapter_id"], []).append(c)
    open_tasks = {r["chapter_id"]: r["n"] for r in conn.execute(
        "SELECT chapter_id, COUNT(*) n FROM tasks WHERE chapter_id IS NOT NULL AND status != 'done' GROUP BY chapter_id")}
    lists = {}
    for item in conn.execute("SELECT * FROM checklist_items ORDER BY list_code, ordinal, id"):
        if item["list_code"] not in svc.CHECKLISTS:
            continue
        lists.setdefault(item["list_code"], []).append(item)
    main = last["main_words"] if last else 0
    return render_template(
        "thesis/index.html", chapters=chapters, last=last, main=main, min_words=svc.MIN_MAIN_WORDS,
        target_total=sum(c["target_words"] or 0 for c in chapters if 1 <= c["ordinal"] <= 7),
        abstract=last["abstract_words"] if last else None,
        abstract_badge=svc.abstract_badge(last["abstract_words"] if last else None), abstract_range=svc.ABSTRACT,
        notes=svc.NOTES, statuses=svc.STATUSES, comments=comments, open_tasks=open_tasks, lists=lists,
        list_titles=svc.CHECKLIST_TITLES, history=svc.history(conn), path=path, state=state)


@bp.post("/chapters/<int:cid>")
def chapter(cid):
    conn = get_db()
    if not conn.execute("SELECT 1 FROM chapters WHERE id = ?", (cid,)).fetchone():
        abort(404)
    fields = {}
    if request.form.get("status") in svc.STATUSES:
        fields["status"] = request.form["status"]
    if "target_words" in request.form:
        v = request.form["target_words"].strip()
        fields["target_words"] = int(v) if v.isdigit() else None
    if "heading_match" in request.form:
        fields["heading_match"] = request.form["heading_match"].strip()
    if fields:
        with conn:
            conn.execute(f"UPDATE chapters SET {', '.join(k + ' = ?' for k in fields)}, updated_at = datetime('now','localtime') "
                         "WHERE id = ?", list(fields.values()) + [cid])
    if "heading_match" in fields:
        return redirect(url_for("thesis.index", recount=1, _anchor=f"ch-{cid}"))
    if request.headers.get("HX-Request"):
        return "", 204
    return redirect(url_for("thesis.index", _anchor=f"ch-{cid}"))


@bp.post("/chapters/<int:cid>/comments")
def add_comment(cid):
    conn = get_db()
    text = (request.form.get("comment") or "").strip()
    if text:
        with conn:
            conn.execute("INSERT INTO chapter_comments (chapter_id, comment, source) VALUES (?, ?, ?)",
                         (cid, text, (request.form.get("source") or "").strip() or None))
    return redirect(url_for("thesis.index", _anchor=f"ch-{cid}"))


@bp.post("/comments/<int:comment_id>")
def comment(comment_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM chapter_comments WHERE id = ?", (comment_id,)).fetchone() or abort(404)
    with conn:
        if request.form.get("delete"):
            conn.execute("DELETE FROM chapter_comments WHERE id = ?", (comment_id,))
        else:
            conn.execute("UPDATE chapter_comments SET resolved = 1 - resolved, updated_at = datetime('now','localtime') WHERE id = ?",
                         (comment_id,))
    return redirect(url_for("thesis.index", _anchor=f"ch-{row['chapter_id']}"))


@bp.post("/checklist/<int:item_id>")
def check(item_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM checklist_items WHERE id = ?", (item_id,)).fetchone() or abort(404)
    with conn:
        if request.form.get("delete"):
            conn.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))
        else:
            done = 0 if row["done"] else 1
            conn.execute("UPDATE checklist_items SET done = ?, done_at = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                         (done, util.today().isoformat() if done else None, item_id))
    if request.headers.get("HX-Request"):
        return "", 204
    return _back_to_list(row["list_code"])


@bp.post("/checklist/<code>/add")
def add_item(code):
    conn = get_db()
    text = (request.form.get("text") or "").strip()
    if text and code in LIST_CODES:
        with conn:
            n = conn.execute("SELECT COALESCE(MAX(ordinal) + 1, 0) FROM checklist_items WHERE list_code = ?", (code,)).fetchone()[0]
            conn.execute("INSERT INTO checklist_items (list_code, ordinal, text) VALUES (?, ?, ?)", (code, n, text))
    return _back_to_list(code)

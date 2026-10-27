"""Module H 13.3: viva preparation."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from hub import util
from hub.db import get_db
from hub.services import viva as svc

bp = Blueprint("viva", __name__, url_prefix="/viva")


@bp.get("")
def index():
    conn = get_db()
    svc.seed(conn)
    cat = request.args.get("category", "")
    sql, args = "SELECT * FROM viva_questions", []
    if cat in svc.CATEGORIES:
        sql += " WHERE category = ?"
        args.append(cat)
    questions = conn.execute(sql + " ORDER BY confidence, category, id", args).fetchall()
    counts = {r["confidence"]: r["n"] for r in conn.execute("SELECT confidence, COUNT(*) n FROM viva_questions GROUP BY confidence")}
    return render_template(
        "viva/index.html", slides=conn.execute("SELECT * FROM checklist_items WHERE list_code = 'VIVA_SLIDES' ORDER BY ordinal, id").fetchall(),
        runs=conn.execute("SELECT * FROM practice_runs ORDER BY run_at DESC LIMIT 20").fetchall(),
        questions=questions, counts=counts, f_cat=cat, categories=svc.CATEGORIES, confidence=svc.CONFIDENCE,
        talk=svc.TALK_SECONDS, qa=svc.QA_SECONDS, warn=svc.WARN_SECONDS, mmss=svc.mmss)


@bp.post("/runs")
def save_run():
    conn = get_db()
    talk = request.form.get("talk_seconds", type=int)
    if talk is None or talk < 0:
        flash("Run the timer before saving.", "warning")
        return redirect(url_for("viva.index", _anchor="timer"))
    with conn:
        conn.execute("INSERT INTO practice_runs (run_at, talk_seconds, notes) VALUES (?, ?, ?)",
                     (util.now().isoformat(timespec="seconds"), talk, (request.form.get("notes") or "").strip() or None))
    over = talk - svc.TALK_SECONDS
    flash(f"Practice run saved: {svc.mmss(talk)}" + (f" ({svc.mmss(over)} over)." if over > 0 else "."), "success")
    return redirect(url_for("viva.index", _anchor="runs"))


@bp.post("/runs/<int:run_id>/delete")
def delete_run(run_id):
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM practice_runs WHERE id = ?", (run_id,))
    return redirect(url_for("viva.index", _anchor="runs"))


@bp.get("/questions/new")
def new_question():
    return render_template("viva/_question.html", q={"id": None, "category": request.args.get("category", "method"), "confidence": 1},
                           errors={}, categories=svc.CATEGORIES, confidence=svc.CONFIDENCE)


@bp.get("/questions/<int:qid>/edit")
def edit_question(qid):
    q = get_db().execute("SELECT * FROM viva_questions WHERE id = ?", (qid,)).fetchone() or abort(404)
    return render_template("viva/_question.html", q=q, errors={}, categories=svc.CATEGORIES, confidence=svc.CONFIDENCE)


def _save(qid=None):
    conn = get_db()
    q, errors = svc.clean_question(request.form)
    if errors:
        return render_template("viva/_question.html", q=dict(q, id=qid), errors=errors, categories=svc.CATEGORIES,
                               confidence=svc.CONFIDENCE), 422
    with conn:
        if qid:
            conn.execute("UPDATE viva_questions SET question=?, answer=?, category=?, confidence=?, updated_at=datetime('now','localtime') "
                         "WHERE id=?", (q["question"], q["answer"], q["category"], q["confidence"], qid))
        else:
            conn.execute("INSERT INTO viva_questions (question, answer, category, confidence) VALUES (?, ?, ?, ?)",
                         (q["question"], q["answer"], q["category"], q["confidence"]))
    flash("Question saved.", "success")
    if request.headers.get("HX-Request"):
        return "", 204, {"HX-Refresh": "true"}
    return redirect(url_for("viva.index", _anchor="questions"))


@bp.post("/questions")
def create_question():
    return _save()


@bp.post("/questions/<int:qid>")
def update_question(qid):
    get_db().execute("SELECT 1 FROM viva_questions WHERE id = ?", (qid,)).fetchone() or abort(404)
    return _save(qid)


@bp.post("/questions/<int:qid>/delete")
def delete_question(qid):
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM viva_questions WHERE id = ?", (qid,))
    flash("Question deleted.", "info")
    return redirect(url_for("viva.index", _anchor="questions"))


def _seen():
    return [int(x) for x in (request.values.get("seen") or "").split(",") if x.isdigit()]


@bp.get("/drill")
def drill():
    conn = get_db()
    seen, cat = _seen(), request.args.get("category", "")
    q = svc.next_drill(conn, seen, cat)
    total = conn.execute("SELECT COUNT(*) FROM viva_questions" + (" WHERE category = ?" if cat in svc.CATEGORIES else ""),
                         (cat,) if cat in svc.CATEGORIES else ()).fetchone()[0]
    return render_template("viva/drill.html", q=q, seen=seen, total=total, f_cat=cat, categories=svc.CATEGORIES,
                           confidence=svc.CONFIDENCE)


@bp.post("/drill/<int:qid>")
def rate(qid):
    conn = get_db()
    conf = request.form.get("confidence", type=int)
    if conf in svc.CONFIDENCE:
        with conn:
            conn.execute("UPDATE viva_questions SET confidence = ?, updated_at = datetime('now','localtime') WHERE id = ?", (conf, qid))
    seen = _seen() + [qid]
    return redirect(url_for("viva.drill", seen=",".join(map(str, seen)), category=request.form.get("category") or None))

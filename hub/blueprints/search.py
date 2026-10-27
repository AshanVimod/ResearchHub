"""Module F: search page."""
import time

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from hub.db import get_db
from hub.services import indexer, semantic
from hub.services import search as svc
from hub.services import settings as st

bp = Blueprint("search", __name__)


@bp.get("/search")
def index():
    conn = get_db()
    f = {k: request.args.get(k, "").strip() for k in ("q", "type", "tag", "year_from", "year_to", "root_folder", "mode")}
    s = st.get_all(conn)
    sem_on = semantic.enabled(s)
    sem_ok, sem_problem = semantic.available() if sem_on else (False, None)
    meaning = sem_on and f["mode"] == "meaning"
    result, elapsed, sem_error = None, None, None
    years = (int(f["year_from"]) if f["year_from"].isdigit() else None, int(f["year_to"]) if f["year_to"].isdigit() else None)
    if f["q"]:
        t = time.perf_counter()
        if meaning:
            result = {"results": [], "counts": {}}
            if not sem_ok:
                sem_error = sem_problem
            elif f["type"] in ("", "file_page"):
                try:
                    result = semantic.query(conn, f["q"], f["tag"], *years, f["root_folder"])
                except Exception as exc:  # e.g. the model has never been downloaded and the laptop is offline
                    current_app.logger.exception("Semantic query failed")
                    sem_error = f"Meaning search is unavailable: {exc}"
        else:
            result = svc.query(conn, f["q"], f["type"] if f["type"] in svc.TYPES else "", f["tag"], *years, f["root_folder"])
        elapsed = round((time.perf_counter() - t) * 1000)
    # Files whose links point at references open the reference viewer instead.
    file_refs = {r["to_id"]: r["from_id"] for r in conn.execute(
        "SELECT from_id, to_id FROM links WHERE from_type = 'ref' AND to_type = 'file'")}
    stats = conn.execute("SELECT COUNT(*) n, COUNT(DISTINCT item_type || item_id) items FROM search_index").fetchone()
    pending = conn.execute("SELECT COUNT(*) FROM files WHERE text_status = 'pending'").fetchone()[0]
    return render_template(
        "search/index.html", f=f, result=result, elapsed=elapsed, types=svc.TYPES, file_refs=file_refs,
        tags=[r["name"] for r in conn.execute("SELECT DISTINCT t.name FROM tags t JOIN taggings g ON g.tag_id = t.id ORDER BY t.name")],
        folders=svc.top_folders(conn), stats=stats, pending=pending, sem_on=sem_on, meaning=meaning, sem_error=sem_error,
        sem_status=semantic.status(conn) if sem_on else None, sem_problem=sem_problem, indexing=indexer.is_running(),
        saved=conn.execute("SELECT * FROM saved_searches ORDER BY name COLLATE NOCASE").fetchall())


@bp.post("/search/semantic/build")
def build_semantic():
    """Embedding runs at the end of a scan, in the indexer's background thread."""
    started = indexer.start_background(current_app.config["DB_PATH"], current_app.logger)
    flash("Building the meaning index in the background. The first run downloads the model (about 90 MB)."
          if started else "A scan is already running; the meaning index is built at its end.", "info")
    return redirect(url_for("search.index", mode="meaning", q=request.form.get("q") or None))


@bp.post("/search/saved")
def save_search():
    conn = get_db()
    name, q = (request.form.get("name") or "").strip(), (request.form.get("query") or "").strip()
    if name and q:
        with conn:
            conn.execute("INSERT INTO saved_searches (name, query) VALUES (?, ?)", (name, q))
        flash(f"Saved search “{name}”.", "success")
    return redirect(url_for("search.index", q=q))


@bp.post("/search/saved/<int:sid>/delete")
def delete_search(sid):
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM saved_searches WHERE id = ?", (sid,))
    return redirect(url_for("search.index"))

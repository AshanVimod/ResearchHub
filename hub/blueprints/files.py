"""Module E: research folder manager. Read only: open/reveal hand files to Windows."""
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for

from hub import util
from hub.db import get_db
from hub.services import dedupe, indexer, paths
from hub.services import refs as ref_svc
from hub.services import settings as st

bp = Blueprint("files", __name__)


def _row(file_id):
    row = get_db().execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        abort(404)
    return row


def _safe_path(row) -> Path | None:
    """Absolute path after the path-safety check; None (with a message) if the file has gone."""
    path = paths.file_path(row)
    if not paths.is_safe(path, st.get_all(get_db())):
        abort(403)
    if not paths.exists(path):
        flash(f"{row['name']} is no longer there. Re-scan to refresh the index.", "warning")
        return None
    return path


def _linked_refs(conn) -> dict[int, list]:
    out = {}
    for r in conn.execute("SELECT l.to_id AS file_id, r.id, r.cite_key FROM links l JOIN refs r ON r.id = l.from_id "
                          "WHERE l.from_type = 'ref' AND l.to_type = 'file'"):
        out.setdefault(r["file_id"], []).append(r)
    return out


def build_tree(rows) -> dict:
    """Nested dict: {'dirs': {name: subtree}, 'files': [rows]} from rel_paths."""
    tree = {"dirs": {}, "files": []}
    for r in rows:
        node = tree
        parts = r["rel_path"].split("/")
        for part in parts[:-1]:
            node = node["dirs"].setdefault(part, {"dirs": {}, "files": []})
        node["files"].append(r)
    return tree


def row_ext(file_id) -> str:
    return _row(file_id)["ext"]


def _tree_count(node) -> int:
    return len(node["files"]) + sum(_tree_count(n) for n in node["dirs"].values())


@bp.get("/files")
def index():
    conn = get_db()
    s = st.get_all(conn)
    f = {k: request.args.get(k, "") for k in ("view", "q", "ext", "root", "status")}
    sql, args = "SELECT * FROM files WHERE text_status != 'missing'", []
    if f["status"] == "missing":
        sql, args = "SELECT * FROM files WHERE text_status = 'missing'", []
    if f["q"]:
        sql += " AND rel_path LIKE ?"
        args.append(f"%{f['q']}%")
    if f["ext"]:
        sql += " AND ext = ?"
        args.append(f["ext"])
    if f["root"]:
        sql += " AND root = ?"
        args.append(f["root"])
    rows = conn.execute(sql + " ORDER BY root, rel_path COLLATE NOCASE", args).fetchall()
    exts = [r["ext"] for r in conn.execute("SELECT ext, COUNT(*) n FROM files WHERE text_status != 'missing' "
                                           "GROUP BY ext ORDER BY n DESC")]
    trees = {}
    for r in rows:
        trees.setdefault(r["root"], []).append(r)
    stats = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(size_bytes), 0) b, SUM(text_status='error') e, "
                         "SUM(text_status='missing') m FROM files").fetchone()
    return render_template("files/index.html", rows=rows, f=f, exts=exts, roots=st.as_list(s, "research_roots"),
                           trees={root: build_tree(rs) for root, rs in trees.items()}, tree_count=_tree_count,
                           tags=ref_svc.tags_for(conn, "file"), refs=_linked_refs(conn), stats=stats,
                           job=indexer.latest_job(conn), running=indexer.is_running(),
                           dup_count=len(dedupe.duplicate_file_groups(conn)))


@bp.get("/files/duplicates")
def duplicates():
    conn = get_db()
    groups = dedupe.duplicate_file_groups(conn)
    return render_template("files/duplicates.html", groups=groups, tags=ref_svc.tags_for(conn, "file"),
                           wasted=sum(g["wasted"] for g in groups))


@bp.get("/files/recent")
def recent():
    conn = get_db()
    since = (util.now() - timedelta(days=14)).timestamp()
    rows = conn.execute("SELECT * FROM files WHERE mtime >= ? AND text_status != 'missing' ORDER BY mtime DESC", (since,)).fetchall()
    return render_template("files/recent.html", rows=rows, tags=ref_svc.tags_for(conn, "file"), refs=_linked_refs(conn))


@bp.post("/files/<int:file_id>/open")
def open_file(file_id):
    path = _safe_path(_row(file_id))
    if path is None:
        pass
    elif sys.platform == "win32":
        os.startfile(indexer.os_path(path))  # noqa: S606 - hands the file to its default Windows app
        flash(f"Opened {path.name}.", "info")
    else:
        flash("Opening files is only supported on Windows.", "warning")
    return redirect(request.form.get("next") or url_for("files.index"))


@bp.post("/files/<int:file_id>/reveal")
def reveal(file_id):
    path = _safe_path(_row(file_id))
    if path is None:
        pass
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(path)], check=False)  # noqa: S603,S607
    else:
        flash("Reveal is only supported on Windows.", "warning")
    return redirect(request.form.get("next") or url_for("files.index"))


@bp.post("/files/<int:file_id>/to-ref")
def to_ref(file_id):
    row = _row(file_id)
    existing = ref_svc.linked(get_db(), "file", file_id, "ref")
    if existing:
        return redirect(url_for("refs.view", ref_id=existing[0]))
    if row["ext"] != ".pdf":
        flash("Only PDFs can become references.", "warning")
        return redirect(url_for("files.index"))
    return redirect(url_for("refs.new", file_id=file_id))


@bp.post("/files/<int:file_id>/tags")
def tags(file_id):
    conn = get_db()
    _row(file_id)
    ref_svc.set_tags(conn, "file", file_id, (request.form.get("tags") or "").split(","))
    return redirect(request.form.get("next") or url_for("files.index"))


@bp.post("/files/<int:file_id>/keep")
def keep(file_id):
    """Mark the keeper of a duplicate group (tag 'keep'); the others lose the tag. Nothing is deleted."""
    conn = get_db()
    row = _row(file_id)
    with conn:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES ('keep')")
        tag_id = conn.execute("SELECT id FROM tags WHERE name = 'keep'").fetchone()[0]
        conn.execute("DELETE FROM taggings WHERE tag_id = ? AND item_type = 'file' AND item_id IN "
                     "(SELECT id FROM files WHERE sha256 = ?)", (tag_id, row["sha256"]))
        conn.execute("INSERT INTO taggings (tag_id, item_type, item_id) VALUES (?, 'file', ?)", (tag_id, file_id))
    return redirect(url_for("files.duplicates", _anchor=f"g-{row['sha256'][:12]}"))


@bp.get("/files/<int:file_id>/view")
def view_pdf(file_id):
    row = _row(file_id)
    if _safe_path(row) is None or row["ext"] != ".pdf":
        abort(404)
    return render_template("pdf_viewer.html", title=row["name"], back=url_for("files.index"),
                           file_url=url_for("files.raw", file_id=file_id))


@bp.get("/files/<int:file_id>/raw")
def raw(file_id):
    path = _safe_path(_row(file_id))
    if path is None:
        abort(404)
    mimetype = "application/pdf" if row_ext(file_id) == ".pdf" else None
    return send_file(indexer.os_path(path), conditional=True, mimetype=mimetype)


@bp.post("/files/rescan")
def rescan():
    started = indexer.start_background(current_app.config["DB_PATH"], current_app.logger)
    if request.headers.get("HX-Request"):
        return status()
    flash("Scanning your research folders…" if started else "A scan is already running.", "info")
    return redirect(url_for("files.index"))


@bp.get("/api/index/status")
def status():
    conn = get_db()
    return render_template("files/_status.html", job=indexer.latest_job(conn), running=indexer.is_running(),
                           now=datetime.now())

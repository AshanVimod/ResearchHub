"""Module D: reference manager, literature matrix, bibliography, PDF viewer."""
import json
import uuid
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request, send_file,
                   url_for)

import config
from hub import util
from hub.db import get_db
from hub.services import bibtex, crossref, dedupe, ieee, indexer, paths, search
from hub.services import refs as svc
from hub.services import settings as st

bp = Blueprint("refs", __name__)


def _library() -> Path:
    return Path(current_app.config.get("LIBRARY_DIR", config.LIBRARY_DIR))


def _incoming() -> Path:
    return _library() / "_incoming"


def _get(ref_id):
    row = get_db().execute("SELECT * FROM refs WHERE id = ?", (ref_id,)).fetchone()
    if row is None:
        abort(404)
    return row


def _blank(**over):
    data = {f: "" for f in svc.FIELDS}
    data.update(ref_type="journal", status="to_read", authors_text="")
    data.update(over)
    return data


def _from_lookup(found: dict, **extra) -> dict:
    data = _blank(**{k: ("" if v is None else v) for k, v in found.items() if k in svc.FIELDS})
    data["authors_text"] = svc.authors_text(json.dumps(found.get("authors") or []))
    data.update(extra)
    return data


def _chapters():
    return get_db().execute("SELECT id, ordinal, title FROM chapters WHERE ordinal > 0 ORDER BY ordinal").fetchall()


def _chapter_list(value) -> list[int]:
    if isinstance(value, (list, tuple)):
        return [int(v) for v in value if str(v).isdigit()]
    try:
        return [int(v) for v in json.loads(value or "[]")]
    except (TypeError, ValueError):
        return []


def _render_form(data, errors=None, notice=None, duplicates=None, doi_block=None, status=200):
    return render_template("refs/form.html", ref=data, errors=errors or {}, notice=notice, duplicates=duplicates or [],
                           doi_block=doi_block, types=svc.TYPES, statuses=svc.STATUSES, matrix=svc.MATRIX,
                           chapters=_chapters(), selected_chapters=_chapter_list(data.get("chapter_ids"))), status


def _form_data():
    data = {f: request.form.get(f, "") for f in svc.FIELDS}
    data["chapter_ids"] = request.form.getlist("chapter_ids")
    data["authors_text"] = request.form.get("authors_text", "")
    data["authors"] = svc.parse_authors_text(data["authors_text"])
    for k in ("pdf_token", "file_id", "cite_key_hint", "tags"):
        data[k] = request.form.get(k, "")
    errors = {}
    if not data["title"].strip():
        errors["title"] = "A title is required."
    if data["year"] and not data["year"].strip().isdigit():
        errors["year"] = "Year must be a number."
    if data["doi"] and not crossref.DOI_RE.fullmatch(crossref.normalise_doi(data["doi"])):
        errors["doi"] = "DOIs start with 10. (e.g. 10.1038/nature14539)."
    return data, errors


# ---- list --------------------------------------------------------------------

@bp.get("/refs")
def index():
    conn = get_db()
    f = {k: request.args.get(k, "") for k in ("q", "status", "type", "tag", "year_from", "year_to", "sort", "chapter")}
    sql, args = "SELECT * FROM refs WHERE 1=1", []
    if f["q"]:
        hits, _expr = search.run(conn, f["q"])
        ids = sorted({int(h["item_id"]) for h in hits if h["item_type"] == "ref"}) or [0]
        sql += f" AND id IN ({','.join('?' * len(ids))})"
        args += ids
    if f["chapter"].isdigit():
        sql += " AND EXISTS (SELECT 1 FROM json_each(refs.chapter_ids) WHERE value = ?)"
        args.append(int(f["chapter"]))
    if f["status"] in svc.STATUSES:
        sql += " AND status = ?"
        args.append(f["status"])
    if f["type"] in svc.TYPES:
        sql += " AND ref_type = ?"
        args.append(f["type"])
    if f["tag"]:
        sql += " AND id IN (SELECT tg.item_id FROM taggings tg JOIN tags t ON t.id = tg.tag_id WHERE tg.item_type='ref' AND t.name = ?)"
        args.append(f["tag"])
    for key, op in (("year_from", ">="), ("year_to", "<=")):
        if f[key].isdigit():
            sql += f" AND year {op} ?"
            args.append(int(f[key]))
    order = {"year": "year DESC, id DESC", "rating": "rating DESC NULLS LAST, id DESC", "title": "title COLLATE NOCASE"}.get(
        f["sort"], "id DESC")
    rows = conn.execute(f"{sql} ORDER BY {order}", args).fetchall()
    counts = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) n FROM refs GROUP BY status")}
    tags = [r["name"] for r in conn.execute("SELECT DISTINCT t.name FROM tags t JOIN taggings tg ON tg.tag_id = t.id "
                                            "WHERE tg.item_type='ref' ORDER BY t.name")]
    return render_template("refs/index.html", refs=rows, f=f, counts=counts, total=sum(counts.values()), tags=tags,
                           ref_tags=svc.tags_for(conn, "ref"), numbers=svc.number_map(conn), ieee=ieee,
                           types=svc.TYPES, statuses=svc.STATUSES,
                           chapters=_chapters(),
                           filtered=any(f[k] for k in ("q", "status", "type", "tag", "year_from", "year_to", "chapter")))


# ---- add -----------------------------------------------------------------------

@bp.get("/refs/new")
def new():
    conn = get_db()
    file_id = request.args.get("file_id", type=int)
    if file_id:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone() or abort(404)
        path = paths.file_path(row)
        if not paths.is_safe(path, st.get_all(conn)) or not paths.exists(path):
            abort(403)
        return _lookup_pdf(indexer.os_path(path), file_id=str(file_id), pdf_path=str(path), title_fallback=Path(row["name"]).stem)
    return render_template("refs/new.html", mode=request.args.get("mode", "doi"), today=util.today())


@bp.post("/refs/lookup")
def lookup():
    conn = get_db()
    s = st.get_all(conn)
    kind = request.form.get("kind")
    try:
        if kind == "doi":
            doi = crossref.normalise_doi(request.form.get("doi", ""))
            existing = dedupe.doi_duplicate(conn, doi)
            if existing:
                flash(f"That DOI is already in the library as {existing['cite_key']}.", "warning")
                return redirect(url_for("refs.view", ref_id=existing["id"]))
            return _render_form(_from_lookup(crossref.lookup_doi(doi, s.get("crossref_mailto", ""))),
                                notice="Filled from Crossref. Check the details, then save.")
        if kind == "arxiv":
            return _render_form(_from_lookup(crossref.lookup_arxiv(request.form.get("arxiv", ""))),
                                notice="Filled from arXiv. Check the authors' family names, then save.")
        if kind == "pdf":
            upload = request.files.get("pdf")
            if not upload or not upload.filename.lower().endswith(".pdf"):
                flash("Choose a PDF file to upload.", "danger")
                return redirect(url_for("refs.new", mode="pdf"))
            _incoming().mkdir(parents=True, exist_ok=True)
            token = uuid.uuid4().hex
            tmp = _incoming() / f"{token}.pdf"
            upload.save(tmp)
            return _lookup_pdf(tmp, pdf_token=token, title_fallback=Path(upload.filename).stem)
    except crossref.LookupError_ as exc:
        data = _blank(doi=request.form.get("doi", ""), arxiv_id=crossref.parse_arxiv_id(request.form.get("arxiv", "")) or "",
                      ref_type="preprint" if kind == "arxiv" else "journal")
        return _render_form(data, notice=f"{exc}", status=200)
    if kind == "website":
        return _render_form(_blank(ref_type="website", url=request.form.get("url", ""), accessed_date=util.today().isoformat()))
    return _render_form(_blank())


def _lookup_pdf(path: Path, title_fallback: str = "", **extra):
    conn = get_db()
    s = st.get_all(conn)
    try:
        hints = svc.pdf_lookup_hints(path)
    except Exception as exc:  # corrupt or encrypted PDF
        return _render_form(_blank(title=title_fallback or path.stem, **extra), notice=f"Could not read the PDF ({exc}). Fill the form by hand.")
    if hints["doi"]:
        existing = dedupe.doi_duplicate(conn, hints["doi"])
        if existing:
            flash(f"This PDF's DOI is already in the library as {existing['cite_key']}.", "warning")
            if extra.get("file_id"):
                svc.link(conn, "ref", existing["id"], "file", int(extra["file_id"]))
                if not conn.execute("SELECT pdf_path FROM refs WHERE id = ?", (existing["id"],)).fetchone()[0]:
                    svc.update_fields(conn, existing["id"], {"pdf_path": extra.get("pdf_path")})
            return redirect(url_for("refs.view", ref_id=existing["id"]))
        try:
            found = crossref.lookup_doi(hints["doi"], s.get("crossref_mailto", ""))
            return _render_form(_from_lookup(found, **extra), notice=f"Found DOI {hints['doi']} in the PDF and filled from Crossref.")
        except crossref.LookupError_ as exc:
            return _render_form(_blank(doi=hints["doi"], title=hints["title"] or title_fallback, **extra),
                                notice=f"Found DOI {hints['doi']} in the PDF, but the lookup failed: {exc}")
    return _render_form(_blank(title=hints["title"] or title_fallback, **extra),
                        notice="No DOI found in the first two pages; title taken from the PDF. Complete the details.")


@bp.post("/refs")
def create():
    conn = get_db()
    data, errors = _form_data()
    if errors:
        return _render_form(data, errors, status=422)
    doi = crossref.normalise_doi(data["doi"]) if data["doi"] else None
    block = dedupe.doi_duplicate(conn, doi)
    if block:
        return _render_form(data, doi_block=block, status=422)
    merge_into = request.form.get("merge_into", type=int)
    if not request.form.get("keep_both") and not merge_into:
        dups = dedupe.title_duplicates(conn, data["title"], data["year"] or None)
        if dups:
            return _render_form(data, duplicates=dups, status=422)
    ref_id = svc.save(conn, data)
    ref = _get(ref_id)
    if data["pdf_token"]:
        tmp = _incoming() / f"{Path(data['pdf_token']).name}.pdf"
        if tmp.exists():
            svc.update_fields(conn, ref_id, {"pdf_path": svc.store_upload(tmp, _library(), ref["cite_key"])})
            tmp.unlink(missing_ok=True)
    if data["file_id"].isdigit():
        svc.link(conn, "ref", ref_id, "file", int(data["file_id"]))
    svc.set_tags(conn, "ref", ref_id, request.form.get("tags", "").split(","))
    if merge_into and conn.execute("SELECT 1 FROM refs WHERE id = ?", (merge_into,)).fetchone():
        svc.merge(conn, merge_into, ref_id)
        flash("Merged into the existing reference.", "success")
        return redirect(url_for("refs.view", ref_id=merge_into))
    flash(f"Saved as {ref['cite_key']}.", "success")
    return redirect(url_for("refs.view", ref_id=ref_id))


# ---- BibTeX import ----------------------------------------------------------------

@bp.get("/refs/import")
def import_form():
    return render_template("refs/import.html", entries=None, text="")


@bp.post("/refs/import")
def import_bib():
    conn = get_db()
    text = request.form.get("bibtex", "")
    upload = request.files.get("bibfile")
    if upload and upload.filename:
        text = upload.read().decode("utf-8", errors="replace")
    entries = bibtex.parse(text)
    if not entries:
        flash("No BibTeX entries found. Paste entries that start with @article{...} etc.", "warning")
        return render_template("refs/import.html", entries=None, text=text)
    if request.form.get("confirm"):
        chosen = {int(i) for i in request.form.getlist("pick") if i.isdigit()}
        created, skipped = 0, 0
        for i, e in enumerate(entries):
            if i not in chosen:
                continue
            if dedupe.doi_duplicate(conn, e["doi"]):
                skipped += 1
                continue
            data = dict(e)
            svc.save(conn, data)
            created += 1
        flash(f"Imported {created} reference{'s' if created != 1 else ''}" + (f"; skipped {skipped} duplicate DOI(s)." if skipped else "."), "success")
        return redirect(url_for("refs.index"))
    preview = []
    for e in entries:
        dup = dedupe.doi_duplicate(conn, e["doi"])
        near = [] if dup else dedupe.title_duplicates(conn, e["title"], e["year"])
        preview.append({"ref": e, "doi_dup": dup, "near": near[0] if near else None,
                        "ieee": ieee.plain(dict(e, authors_json=json.dumps(e["authors"]), article_no=None, ieee_number=None))})
    return render_template("refs/import.html", entries=preview, text=text)


# ---- detail / edit -------------------------------------------------------------------

@bp.get("/refs/<int:ref_id>")
def view(ref_id):
    conn = get_db()
    ref = _get(ref_id)
    file_ids = svc.linked(conn, "ref", ref_id, "file")
    task_ids = svc.linked(conn, "ref", ref_id, "task")
    diary_ids = svc.linked(conn, "ref", ref_id, "diary")
    q = lambda table, ids: conn.execute(f"SELECT * FROM {table} WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall() if ids else []  # noqa: E731
    pdf = paths.ref_pdf_path(ref, _library())
    return render_template(
        "refs/view.html", ref=ref, ieee_text=ieee.plain(ref), ieee_html=ieee.html(ref),
        number=svc.number_map(conn).get(ref_id), authors=ieee.authors_of(ref), types=svc.TYPES, statuses=svc.STATUSES,
        matrix=svc.MATRIX, files=q("files", file_ids), tasks=q("tasks", task_ids), diary=q("diary_entries", diary_ids),
        highlights=conn.execute("SELECT * FROM highlights WHERE ref_id = ? ORDER BY page, id", (ref_id,)).fetchall(),
        tags=", ".join(svc.tags_for(conn, "ref").get(ref_id, [])), has_pdf=bool(pdf and paths.exists(pdf)),
        duplicates=dedupe.title_duplicates(conn, ref["title"], ref["year"], exclude_id=ref_id),
        open_tasks=conn.execute("SELECT id, title FROM tasks WHERE status != 'done' ORDER BY title").fetchall(),
        ref_chapters=[c for c in _chapters() if c["id"] in _chapter_list(ref["chapter_ids"])],
        recent_diary=conn.execute("SELECT id, meeting_date FROM diary_entries ORDER BY meeting_date DESC LIMIT 20").fetchall(),
    )


@bp.get("/refs/<int:ref_id>/edit")
def edit(ref_id):
    conn = get_db()
    ref = dict(_get(ref_id))
    ref["authors_text"] = svc.authors_text(ref["authors_json"])
    ref = {k: ("" if v is None else v) for k, v in ref.items()}
    ref["tags"] = ", ".join(svc.tags_for(conn, "ref").get(ref_id, []))
    return _render_form(ref)


@bp.post("/refs/<int:ref_id>")
def update(ref_id):
    conn = get_db()
    old = _get(ref_id)
    data, errors = _form_data()
    data["id"] = ref_id
    data["cite_key"] = old["cite_key"]
    if errors:
        return _render_form(data, errors, status=422)
    block = dedupe.doi_duplicate(conn, crossref.normalise_doi(data["doi"]) if data["doi"] else None, exclude_id=ref_id)
    if block:
        return _render_form(data, doi_block=block, status=422)
    data["pdf_path"] = data["pdf_path"] or old["pdf_path"]
    svc.save(conn, data, ref_id)
    svc.set_tags(conn, "ref", ref_id, request.form.get("tags", "").split(","))
    flash("Reference updated.", "success")
    return redirect(url_for("refs.view", ref_id=ref_id))


@bp.post("/refs/<int:ref_id>/quick")
def quick(ref_id):
    """Small inline updates from the detail page: status, rating, notes, ieee_number."""
    conn = get_db()
    _get(ref_id)
    fields = {k: request.form[k] for k in ("status", "rating", "notes", "ieee_number") if k in request.form}
    if "status" in fields and fields["status"] not in svc.STATUSES:
        abort(400, "Unknown status.")
    svc.update_fields(conn, ref_id, fields)
    if "tags" in request.form:
        svc.set_tags(conn, "ref", ref_id, request.form["tags"].split(","))
    if request.headers.get("HX-Request"):
        if "notes" in fields:
            return render_template("refs/_notes.html", ref=_get(ref_id), saved=True)
        return "", 204
    flash("Saved.", "success")
    return redirect(url_for("refs.view", ref_id=ref_id))


@bp.post("/refs/<int:ref_id>/delete")
def delete(ref_id):
    conn = get_db()
    ref = _get(ref_id)
    pdf = paths.ref_pdf_path(ref, _library())
    svc.delete(conn, ref_id)
    # Only PDFs copied into data/library belong to the app; linked research files are never touched.
    if pdf and pdf.exists() and not Path(ref["pdf_path"]).is_absolute() and request.form.get("delete_pdf"):
        pdf.unlink()
    flash(f"Deleted {ref['cite_key']}.", "info")
    return redirect(url_for("refs.index"))


@bp.post("/refs/<int:ref_id>/merge/<int:other_id>")
def merge(ref_id, other_id):
    """Merge two existing records: the older one (lower id) is kept."""
    conn = get_db()
    _get(ref_id), _get(other_id)
    older, newer = sorted((ref_id, other_id))
    svc.merge(conn, older, newer)
    flash("References merged.", "success")
    return redirect(url_for("refs.view", ref_id=older))


@bp.post("/refs/<int:ref_id>/highlights")
def add_highlight(ref_id):
    conn = get_db()
    _get(ref_id)
    quote = (request.form.get("quote") or "").strip()
    if quote or request.form.get("comment"):
        with conn:
            conn.execute("INSERT INTO highlights (ref_id, page, quote, comment) VALUES (?, ?, ?, ?)",
                         (ref_id, request.form.get("page", type=int), quote, (request.form.get("comment") or "").strip() or None))
    return redirect(url_for("refs.view", ref_id=ref_id, _anchor="highlights"))


@bp.post("/refs/<int:ref_id>/highlights/<int:hid>/delete")
def delete_highlight(ref_id, hid):
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM highlights WHERE id = ? AND ref_id = ?", (hid, ref_id))
    return redirect(url_for("refs.view", ref_id=ref_id, _anchor="highlights"))


@bp.post("/refs/<int:ref_id>/link")
def link(ref_id):
    conn = get_db()
    _get(ref_id)
    kind, other = request.form.get("type"), request.form.get("id", type=int)
    if kind not in ("task", "diary", "file") or not other:
        abort(400, "Choose something to link.")
    if request.form.get("unlink"):
        svc.unlink(conn, "ref", ref_id, kind, other)
        svc.unlink(conn, kind, other, "ref", ref_id)
    else:
        svc.link(conn, "ref", ref_id, kind, other)
    return redirect(url_for("refs.view", ref_id=ref_id, _anchor="links"))


# ---- literature matrix ---------------------------------------------------------------

@bp.get("/refs/matrix")
def matrix():
    conn = get_db()
    return render_template("refs/matrix.html", rows=svc.matrix_rows(conn), matrix=svc.MATRIX, ieee=ieee)


def _matrix_field(field):
    if field not in dict(svc.MATRIX):
        abort(404)


@bp.get("/refs/<int:ref_id>/cell/<field>")
def cell_edit(ref_id, field):
    _matrix_field(field)
    return render_template("refs/_cell.html", ref=_get(ref_id), field=field, editing=True)


@bp.post("/refs/<int:ref_id>/cell/<field>")
def cell_save(ref_id, field):
    _matrix_field(field)
    _get(ref_id)
    svc.update_fields(get_db(), ref_id, {field: (request.form.get("value") or "").strip()})
    return render_template("refs/_cell.html", ref=_get(ref_id), field=field, editing=False)


@bp.get("/refs/<int:ref_id>/cell/<field>/view")
def cell_view(ref_id, field):
    _matrix_field(field)
    return render_template("refs/_cell.html", ref=_get(ref_id), field=field, editing=False)


@bp.get("/refs/matrix/export.<fmt>")
def matrix_export(fmt):
    conn = get_db()
    rows = svc.matrix_rows(conn)
    out = Path(current_app.config["EXPORTS_DIR"]) / f"literature_matrix_{util.today().isoformat()}.{fmt}"
    if fmt == "csv":
        svc.export_matrix_csv(rows, out)
    elif fmt == "xlsx":
        svc.export_matrix_xlsx(rows, out)
    else:
        abort(404)
    return send_file(out, as_attachment=True, download_name=out.name)


# ---- bibliography ------------------------------------------------------------------

@bp.get("/refs/bibliography")
def bibliography():
    conn = get_db()
    scope = request.args.get("status", "cited")
    rows = svc.numbering(conn, None if scope == "all" else "cited")
    return render_template("refs/bibliography.html", rows=rows, scope=scope,
                           items=[(r, ieee.html(r), ieee.plain(r)) for r in rows])


@bp.get("/refs/bibliography/export.<fmt>")
def bibliography_export(fmt):
    conn = get_db()
    scope = request.args.get("status", "cited")
    rows = svc.numbering(conn, None if scope == "all" else "cited")
    out = Path(current_app.config["EXPORTS_DIR"]) / f"references_{scope}_{util.today().isoformat()}.{fmt}"
    if fmt == "docx":
        svc.export_bibliography_docx(rows, out)
    elif fmt == "bib":
        svc.export_bib(rows, out)
    else:
        abort(404)
    return send_file(out, as_attachment=True, download_name=out.name)


# ---- PDF viewer (only inside data/library or a research root) -------------

@bp.get("/pdf/<int:ref_id>")
def pdf_view(ref_id):
    ref = _get(ref_id)
    path = paths.ref_pdf_path(ref, _library())
    if not path or not paths.exists(path):
        abort(404)
    if not paths.is_safe(path, st.get_all(get_db()), _library().parent):
        abort(403)
    return render_template("pdf_viewer.html", title=ref["title"], back=url_for("refs.view", ref_id=ref_id),
                           file_url=url_for("refs.pdf_file", ref_id=ref_id))


@bp.get("/pdf/<int:ref_id>/file")
def pdf_file(ref_id):
    ref = _get(ref_id)
    path = paths.ref_pdf_path(ref, _library())
    if not path or not paths.exists(path):
        abort(404)
    if not paths.is_safe(path, st.get_all(get_db()), _library().parent):
        abort(403)
    return send_file(indexer.os_path(path), mimetype="application/pdf")

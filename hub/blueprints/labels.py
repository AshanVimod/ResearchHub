"""Dataset label tracker."""
import sqlite3
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for

from hub import util
from hub.db import get_db
from hub.services import labels as svc

bp = Blueprint("labels", __name__, url_prefix="/labels")
FILTERS = ("q", "source", "label", "doubtful", "entity_group", "period", "nc")


def _filters():
    return {k: request.args.get(k, "") for k in FILTERS}


def _rows(conn, f):
    sql, args = ("SELECT l.*, fl.name AS evidence_file_name FROM dataset_labels l LEFT JOIN files fl ON fl.id = l.evidence_file_id "
                 "WHERE 1=1"), []
    if f["q"]:
        sql += " AND (l.entity LIKE ? OR l.entity_code LIKE ? OR l.notes LIKE ?)"
        args += [f"%{f['q']}%"] * 3
    for k in ("source", "entity_group", "period"):
        if f[k]:
            sql += f" AND l.{k} = ?"
            args.append(f[k])
    if f["label"] in ("0", "1"):
        sql += " AND l.label = ?"
        args.append(int(f["label"]))
    if f["doubtful"] == "1":
        sql += " AND l.doubtful = 1"
    return conn.execute(sql + " ORDER BY l.entity COLLATE NOCASE, l.period, l.source", args).fetchall()


def _pdf_files(conn):
    return conn.execute("SELECT id, rel_path FROM files WHERE ext = '.pdf' AND text_status != 'missing' "
                        "ORDER BY rel_path COLLATE NOCASE").fetchall()


@bp.get("")
def index():
    conn = get_db()
    svc.ensure_rules(conn)
    f = _filters()
    include_nc = f["nc"] == "1"
    rows = _rows(conn, f)
    all_rows = conn.execute("SELECT * FROM dataset_labels").fetchall()
    distinct = lambda col: [r[0] for r in conn.execute(f"SELECT DISTINCT {col} FROM dataset_labels WHERE {col} IS NOT NULL ORDER BY 1")]  # noqa: E731
    return render_template(
        "labels/index.html", rows=rows, f=f, include_nc=include_nc,
        summary=svc.summary(all_rows, include_nc),
        rules=svc.current_rules(conn), sources=svc.SOURCES, strengths=svc.STRENGTHS,
        entity_groups=distinct("entity_group"), years=distinct("period"),
        filtered=any(f[k] for k in FILTERS if k != "nc"))


def _form_page(label, errors=None, status=200):
    conn = get_db()
    return render_template("labels/_form.html", label=label, errors=errors or {}, sources=svc.SOURCES,
                           strengths=svc.STRENGTHS, pdfs=_pdf_files(conn), rules=svc.current_rules(conn),
                           entities=[r[0] for r in conn.execute("SELECT DISTINCT entity FROM dataset_labels ORDER BY 1")],
                           entity_groups=[r[0] for r in conn.execute("SELECT DISTINCT entity_group FROM dataset_labels WHERE entity_group IS NOT NULL ORDER BY 1")]), status


@bp.get("/new")
def new():
    svc.ensure_rules(get_db())
    label = {f: "" for f in svc.FIELDS}
    label.update(id=None, label=1, source="PRIMARY")
    # "Add another row for this entity" pre-fills the entity fields.
    for k in ("entity", "entity_code", "entity_group", "period"):
        if request.args.get(k):
            label[k] = request.args[k]
    return _form_page(label)


@bp.get("/<int:label_id>/edit")
def edit(label_id):
    row = get_db().execute("SELECT * FROM dataset_labels WHERE id = ?", (label_id,)).fetchone() or abort(404)
    return _form_page(dict(row))


def _save(label_id=None):
    conn = get_db()
    cur = svc.current_rules(conn)
    values, errors = svc.clean(request.form.to_dict(), cur["version"] if cur else None)
    if not errors:
        try:
            svc.save(conn, values, label_id)
        except sqlite3.IntegrityError:
            errors["period"] = "This entity already has a row for that period and source."
    if errors:
        return _form_page(dict(values, id=label_id), errors, 422)
    flash(f"Saved {values['entity']} {values['period']} ({values['source']}).", "success")
    if request.headers.get("HX-Request"):
        return "", 204, {"HX-Refresh": "true"}
    return redirect(url_for("labels.index"))


@bp.post("")
def create():
    return _save()


@bp.post("/<int:label_id>")
def update(label_id):
    get_db().execute("SELECT 1 FROM dataset_labels WHERE id = ?", (label_id,)).fetchone() or abort(404)
    return _save(label_id)


@bp.post("/<int:label_id>/delete")
def delete(label_id):
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM dataset_labels WHERE id = ?", (label_id,))
    flash("Label row deleted.", "info")
    return redirect(url_for("labels.index"))


@bp.post("/rules")
def rules():
    conn = get_db()
    text = (request.form.get("text") or "").strip()
    if not text:
        flash("The rules can't be empty.", "danger")
    else:
        version = svc.save_rules(conn, text)
        flash(f"Labelling rules saved as {version}. New rows will record {version}.", "success")
    return redirect(url_for("labels.index", _anchor="rules"))


@bp.get("/export.csv")
def export():
    conn = get_db()
    include_nc = request.args.get("nc") == "1"
    out = Path(current_app.config["EXPORTS_DIR"]) / f"labels_by_entity_period_{util.today().isoformat()}.csv"
    svc.export_csv(conn.execute("SELECT * FROM dataset_labels").fetchall(), out, include_nc)
    return send_file(out, as_attachment=True, download_name=out.name)

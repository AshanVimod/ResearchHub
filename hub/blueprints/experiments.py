"""Module H 13.2: experiment log and the notebook API."""
import json

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

import config
from hub import util
from hub.db import get_db
from hub.services import experiments as svc

bp = Blueprint("experiments", __name__)


def _get(exp_id):
    row = get_db().execute("SELECT * FROM experiments WHERE id = ?", (exp_id,)).fetchone()
    if row is None:
        abort(404)
    return row


@bp.get("/experiments")
def index():
    conn = get_db()
    f = {k: request.args.get(k, "") for k in ("approach", "model", "starred")}
    sql, args = "SELECT * FROM experiments WHERE 1=1", []
    if f["approach"] in svc.APPROACHES:
        sql += " AND approach = ?"
        args.append(f["approach"])
    if f["model"]:
        sql += " AND model = ?"
        args.append(f["model"])
    if f["starred"] == "1":
        sql += " AND starred = 1"
    rows = conn.execute(sql + " ORDER BY run_at DESC, id DESC", args).fetchall()
    cols = svc.metric_columns(rows)
    return render_template("experiments/index.html", rows=rows, cols=cols, f=f, approaches=svc.APPROACHES,
                           labels=svc.METRIC_LABELS, metrics={r["id"]: svc.metrics_of(r) for r in rows},
                           best={c: svc.best(rows, c) for c in cols},
                           config_scripts=str(config.BASE_DIR / "scripts"),
                           models=[r[0] for r in conn.execute("SELECT DISTINCT model FROM experiments WHERE model IS NOT NULL ORDER BY 1")])


@bp.get("/experiments/compare")
def compare():
    conn = get_db()
    ids = [int(i) for i in request.args.getlist("id") if i.isdigit()][:4]
    if len(ids) < 2:
        flash("Pick 2 to 4 runs to compare.", "warning")
        return redirect(url_for("experiments.index"))
    rows = conn.execute(f"SELECT * FROM experiments WHERE id IN ({','.join('?' * len(ids))}) ORDER BY run_at", ids).fetchall()
    cols = svc.metric_columns(rows)
    params = {r["id"]: svc.params_of(r) for r in rows}
    param_keys = sorted({k for p in params.values() for k in p})
    param_diff = {k: len({json.dumps(p.get(k), sort_keys=True) for p in params.values()}) > 1 for k in param_keys}
    return render_template("experiments/compare.html", rows=rows, cols=cols, labels=svc.METRIC_LABELS,
                           metrics={r["id"]: svc.metrics_of(r) for r in rows}, params=params,
                           param_keys=param_keys, param_diff=param_diff, best={c: svc.best(rows, c) for c in cols}, approaches=svc.APPROACHES)


@bp.get("/experiments/new")
def new():
    return render_template("experiments/form.html", exp={"approach": "other", "params_json": "{}", "metrics_json": "{}"},
                           approaches=svc.APPROACHES, error=None)


@bp.post("/experiments")
def create():
    conn = get_db()
    try:
        values = svc.clean(request.form.to_dict(), util.now())
    except svc.InvalidRun as exc:
        return render_template("experiments/form.html", exp=request.form, approaches=svc.APPROACHES, error=str(exc)), 422
    exp_id = svc.save(conn, values)
    return redirect(url_for("experiments.view", exp_id=exp_id))


@bp.get("/experiments/<int:exp_id>")
def view(exp_id):
    row = _get(exp_id)
    return render_template("experiments/view.html", exp=row, metrics=svc.metrics_of(row), params=svc.params_of(row),
                           approaches=svc.APPROACHES, labels=svc.METRIC_LABELS)


@bp.get("/experiments/<int:exp_id>/edit")
def edit(exp_id):
    return render_template("experiments/form.html", exp=_get(exp_id), approaches=svc.APPROACHES, error=None)


@bp.post("/experiments/<int:exp_id>")
def update(exp_id):
    conn = get_db()
    _get(exp_id)
    try:
        values = svc.clean(request.form.to_dict(), util.now())
    except svc.InvalidRun as exc:
        return render_template("experiments/form.html", exp=dict(request.form, id=exp_id), approaches=svc.APPROACHES, error=str(exc)), 422
    svc.save(conn, values, exp_id)
    flash("Run updated.", "success")
    return redirect(url_for("experiments.view", exp_id=exp_id))


@bp.post("/experiments/<int:exp_id>/star")
def star(exp_id):
    conn = get_db()
    row = _get(exp_id)
    with conn:
        conn.execute("UPDATE experiments SET starred = ? WHERE id = ?", (0 if row["starred"] else 1, exp_id))
    if request.headers.get("HX-Request"):
        return render_template("experiments/_star.html", exp=_get(exp_id))
    return redirect(request.form.get("next") or url_for("experiments.index"))


@bp.post("/experiments/<int:exp_id>/delete")
def delete(exp_id):
    conn = get_db()
    _get(exp_id)
    with conn:
        conn.execute("DELETE FROM experiments WHERE id = ?", (exp_id,))
    flash("Run deleted.", "info")
    return redirect(url_for("experiments.index"))


@bp.post("/api/experiments")
def api_create():
    """Logging from Jupyter (scripts/log_experiment.py). JSON only; see the CSRF note in app.py."""
    if not request.is_json:
        return jsonify(error="Send JSON (Content-Type: application/json)."), 415
    try:
        values = svc.clean(request.get_json(silent=True) or {}, util.now())
    except svc.InvalidRun as exc:
        return jsonify(error=str(exc)), 400
    exp_id = svc.save(get_db(), values)
    return jsonify(ok=True, id=exp_id, url=url_for("experiments.view", exp_id=exp_id, _external=True)), 201

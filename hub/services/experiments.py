"""Experiment log."""
import json
from datetime import datetime

APPROACHES = {"baseline": "Baseline", "proposed": "Proposed method", "ablation": "Ablation",
              "tuning": "Hyper-parameter tuning", "transfer": "Transfer / fine-tune", "other": "Other"}
# Shown first, in this order, when present; any other metric keys follow alphabetically.
METRIC_ORDER = ["accuracy", "f1", "pr_auc", "roc_auc", "recall_top10", "recall_top20", "top10_hits", "top20_hits"]
METRIC_LABELS = {"accuracy": "Accuracy", "f1": "F1", "pr_auc": "PR-AUC", "roc_auc": "ROC-AUC", "recall_top10": "Recall@top-10%",
                 "recall_top20": "Recall@top-20%", "top10_hits": "Top-10% hits", "top20_hits": "Top-20% hits"}
LOWER_IS_BETTER = {"log_loss", "brier", "fpr", "loss"}
FIELDS = ["run_name", "run_at", "approach", "model", "data_version", "split_desc", "params_json", "metrics_json",
          "notebook_path", "git_commit", "notes", "starred"]


class InvalidRun(ValueError):
    pass


def _json_obj(value, name):
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise InvalidRun(f"{name} is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise InvalidRun(f"{name} must be a JSON object.")
    return value


def clean(data: dict, now: datetime) -> dict:
    """Validate an API/form payload. Accepts params/metrics as dicts or JSON strings."""
    approach = (data.get("approach") or "other").strip()
    if approach not in APPROACHES:
        raise InvalidRun(f"approach must be one of: {', '.join(APPROACHES)}.")
    metrics = _json_obj(data.get("metrics", data.get("metrics_json")), "metrics")
    for k, v in metrics.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise InvalidRun(f"metric {k!r} must be a number.")
    params = _json_obj(data.get("params", data.get("params_json")), "params")
    run_at = data.get("run_at") or now.isoformat(timespec="seconds")
    try:
        datetime.fromisoformat(str(run_at))
    except ValueError as exc:
        raise InvalidRun("run_at must be an ISO date/time.") from exc
    s = lambda k: (str(data.get(k)).strip() or None) if data.get(k) not in (None, "") else None  # noqa: E731
    return {"run_name": s("run_name") or f"run {run_at[:16]}", "run_at": str(run_at), "approach": approach,
            "model": s("model"), "data_version": s("data_version"), "split_desc": s("split_desc"),
            "params_json": json.dumps(params, sort_keys=True), "metrics_json": json.dumps(metrics, sort_keys=True),
            "notebook_path": s("notebook_path"), "git_commit": s("git_commit"), "notes": s("notes"),
            "starred": 1 if data.get("starred") in (1, True, "1", "on", "true") else 0}


def save(conn, values: dict, exp_id: int | None = None) -> int:
    with conn:
        if exp_id is None:
            return conn.execute(f"INSERT INTO experiments ({', '.join(FIELDS)}) VALUES ({', '.join('?' * len(FIELDS))})",
                                [values[f] for f in FIELDS]).lastrowid
        conn.execute(f"UPDATE experiments SET {', '.join(f + ' = ?' for f in FIELDS)}, updated_at = datetime('now','localtime') "
                     "WHERE id = ?", [values[f] for f in FIELDS] + [exp_id])
    return exp_id


def metrics_of(row) -> dict:
    try:
        return json.loads(row["metrics_json"] or "{}")
    except ValueError:
        return {}


def params_of(row) -> dict:
    try:
        return json.loads(row["params_json"] or "{}")
    except ValueError:
        return {}


def metric_columns(rows) -> list[str]:
    keys = set()
    for r in rows:
        keys.update(metrics_of(r))
    return [k for k in METRIC_ORDER if k in keys] + sorted(keys - set(METRIC_ORDER))


def best(rows, key: str):
    vals = [(metrics_of(r).get(key), r["id"]) for r in rows if isinstance(metrics_of(r).get(key), (int, float))]
    if not vals:
        return None
    return (min if key in LOWER_IS_BETTER else max)(vals)[1]


def import_pending(conn, path, now: datetime) -> int:
    """Load runs that log_experiment.py queued while the app was off, then clear the file."""
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return 0
    n, keep = 0, []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            save(conn, clean(json.loads(line), now))
            n += 1
        except (ValueError, InvalidRun):
            keep.append(line)
    if keep:
        p.write_text("\n".join(keep) + "\n", encoding="utf-8")
    else:
        p.unlink()
    return n

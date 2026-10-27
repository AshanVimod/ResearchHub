"""Log an experiment run to Research Hub from a Jupyter notebook.

    import sys; sys.path.append(r"C:\\path\\to\\research-hub\\scripts")
    from log_experiment import log_run
    log_run(run_name="rf_baseline_v1", approach="baseline", model="RandomForest",
            metrics={"accuracy": 0.86, "f1": 0.81}, params={"n_estimators": 200})

Standard library only, so it works in any notebook environment. If the app is not running the run
is appended to experiments_pending.jsonl (next to the app) and imported when the app next starts.
"""
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

API = "http://127.0.0.1:8000/api/experiments"
PENDING = Path(__file__).resolve().parent.parent / "experiments_pending.jsonl"


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def log_run(run_name: str | None = None, approach: str = "other", model: str | None = None,
            data_version: str | None = None, split_desc: str | None = None, params: dict | None = None,
            metrics: dict | None = None, notebook_path: str | None = None, git_commit: str | None = None,
            notes: str | None = None, run_at: str | None = None, api: str = API, quiet: bool = False) -> dict:
    """Send one run. Returns the server's reply, or {'queued': True} when the app is unreachable."""
    payload = {
        "run_name": run_name, "approach": approach, "model": model, "data_version": data_version,
        "split_desc": split_desc, "params": params or {},
        "metrics": {k: float(v) if hasattr(v, "item") else v for k, v in (metrics or {}).items()},  # numpy -> float
        "notebook_path": notebook_path, "git_commit": git_commit or _git_commit(), "notes": notes,
        "run_at": run_at or datetime.now().isoformat(timespec="seconds"),
    }
    req = urllib.request.Request(api, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            reply = json.loads(r.read().decode("utf-8"))
        if not quiet:
            print(f"Logged run #{reply.get('id')} -> {reply.get('url')}")
        return reply
    except urllib.error.HTTPError as exc:  # the app rejected the payload: tell the user, don't queue it
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Research Hub rejected the run: {detail}") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        with open(PENDING, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        if not quiet:
            print(f"Research Hub is not running; queued in {PENDING}")
        return {"queued": True}

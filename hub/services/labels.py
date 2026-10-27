"""Dataset label tracker: one row per entity × period × evidence source."""
import csv
from pathlib import Path

SOURCES = {"PRIMARY": "Primary record", "PUBLISHED": "Published source", "EXPERT": "Expert judgement",
           "RULE": "Rule / heuristic", "SURVEY": "Survey or interview", "OTHER": "Other"}
# Evidence strength. "not_counted" rows are recorded but only count as positive when the switch is on.
STRENGTHS = {"": "—", "strong": "Strong", "moderate": "Moderate", "weak": "Weak",
            "not_counted": "Recorded, not counted"}
FIELDS = ["entity", "entity_code", "entity_group", "period", "source", "event_date", "evidence_url",
          "evidence_file_id", "label", "evidence_strength", "doubtful", "reviewed_with_supervisor", "rule_version", "notes"]
DEFAULT_RULES = """# Labelling rules v1

- **Positive (1):** a reliable source shows the condition you are labelling for this entity and period.
- **Recorded, not counted:** evidence worth keeping that does **not** make the row positive.
- **Doubtful:** evidence is indirect or the period is unclear; review with the supervisor.
- One row per entity × period × source. An entity-period is positive if any row is positive.
- Edit these rules to suit your project; each change is saved as a new version.
"""


def current_rules(conn):
    return conn.execute("SELECT * FROM label_rules ORDER BY id DESC LIMIT 1").fetchone()


def ensure_rules(conn):
    if not current_rules(conn):
        with conn:
            conn.execute("INSERT INTO label_rules (version, text) VALUES ('v1', ?)", (DEFAULT_RULES,))


def save_rules(conn, text: str) -> str:
    """Store a new version (v2, v3, ...) unless the text is unchanged."""
    cur = current_rules(conn)
    if cur and cur["text"].strip() == text.strip():
        return cur["version"]
    n = conn.execute("SELECT COUNT(*) FROM label_rules").fetchone()[0] + 1
    version = f"v{n}"
    with conn:
        conn.execute("INSERT INTO label_rules (version, text) VALUES (?, ?)", (version, text.strip() + "\n"))
    return version


def clean(data: dict, default_version: str | None) -> tuple[dict, dict]:
    out, errors = {}, {}
    for f in FIELDS:
        v = data.get(f)
        out[f] = v.strip() if isinstance(v, str) else v
        if out[f] == "":
            out[f] = None
    if not out["entity"]:
        errors["entity"] = "Entity is required."
    if not out["period"]:
        errors["period"] = "Period is required (e.g. 2024 or 2023/24)."
    if out["source"] not in SOURCES:
        errors["source"] = "Choose a source."
    if str(out["label"]) not in ("0", "1"):
        errors["label"] = "Label must be 0 or 1."
    else:
        out["label"] = int(out["label"])
    if out["evidence_strength"] not in (None, *STRENGTHS):
        errors["evidence_strength"] = "Unknown evidence strength."
    for f in ("doubtful", "reviewed_with_supervisor"):
        out[f] = 1 if out[f] in (1, "1", "on", "true", True) else 0
    try:
        out["evidence_file_id"] = int(out["evidence_file_id"]) if out["evidence_file_id"] else None
    except (TypeError, ValueError):
        out["evidence_file_id"] = None
    out["rule_version"] = out["rule_version"] or default_version
    return out, errors


def save(conn, values: dict, label_id: int | None = None) -> int:
    with conn:
        if label_id is None:
            cur = conn.execute(f"INSERT INTO dataset_labels ({', '.join(FIELDS)}) VALUES ({', '.join('?' * len(FIELDS))})",
                               [values[f] for f in FIELDS])
            return cur.lastrowid
        conn.execute(f"UPDATE dataset_labels SET {', '.join(f + ' = ?' for f in FIELDS)}, updated_at = datetime('now','localtime') "
                     "WHERE id = ?", [values[f] for f in FIELDS] + [label_id])
    return label_id


def counts_as_positive(row, include_not_counted: bool) -> bool:
    return row["label"] == 1 and (include_not_counted or row["evidence_strength"] != "not_counted")


def entity_periods(rows, include_not_counted: bool = False) -> list[dict]:
    """One entry per entity × period with the aggregated label and its sources."""
    out: dict[tuple, dict] = {}
    for r in rows:
        key = (r["entity"].strip().lower(), r["period"].strip())
        cy = out.setdefault(key, {"entity": r["entity"], "entity_code": r["entity_code"], "entity_group": r["entity_group"],
                                  "period": r["period"], "label": 0, "sources": [], "positive_sources": [],
                                  "doubtful": 0, "reviewed": 1, "rows": 0})
        cy["rows"] += 1
        cy["entity_code"] = cy["entity_code"] or r["entity_code"]
        cy["entity_group"] = cy["entity_group"] or r["entity_group"]
        if r["source"] not in cy["sources"]:
            cy["sources"].append(r["source"])
        if counts_as_positive(r, include_not_counted):
            cy["label"] = 1
            cy["positive_sources"].append(r["source"])
        cy["doubtful"] = max(cy["doubtful"], r["doubtful"] or 0)
        cy["reviewed"] = min(cy["reviewed"], r["reviewed_with_supervisor"] or 0)
    return sorted(out.values(), key=lambda c: (c["entity"].lower(), c["period"]))


def summary(rows, include_not_counted: bool = False) -> dict:
    cys = entity_periods(rows, include_not_counted)
    per_source = {s: {"rows": 0, "positive": 0} for s in SOURCES}
    for r in rows:
        per_source[r["source"]]["rows"] += 1
        per_source[r["source"]]["positive"] += 1 if counts_as_positive(r, include_not_counted) else 0
    per_year: dict[str, dict] = {}
    for cy in cys:
        y = per_year.setdefault(cy["period"], {"entity_periods": 0, "positive": 0})
        y["entity_periods"] += 1
        y["positive"] += cy["label"]
    return {"entity_periods": len(cys), "positive": sum(c["label"] for c in cys),
            "entities_positive": len({c["entity"].lower() for c in cys if c["label"]}),
            "doubtful": sum(1 for c in cys if c["doubtful"]),
            "per_source": {k: v for k, v in per_source.items() if v["rows"]},
            "per_year": dict(sorted(per_year.items()))}


def export_csv(rows, path: Path, include_not_counted: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entity", "code", "group", "period", "label", "sources", "positive_sources",
                    "doubtful", "reviewed_with_supervisor", "n_rows"])
        for c in entity_periods(rows, include_not_counted):
            w.writerow([c["entity"], c["entity_code"] or "", c["entity_group"] or "", c["period"], c["label"],
                        ";".join(c["sources"]), ";".join(c["positive_sources"]), c["doubtful"], c["reviewed"], c["rows"]])
    return path

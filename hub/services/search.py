"""Full-text search over search_index."""
import html
import re
import sqlite3
from datetime import datetime

SNIP_OPEN, SNIP_CLOSE = "\x02", "\x03"
TYPES = {"file_page": "Files", "ref": "References", "diary": "Diary", "task": "Tasks",
         "inbox": "Inbox", "experiment": "Experiments", "label": "Labels"}
TAG_TYPES = {"file_page": "file", "ref": "ref", "task": "task"}
TOKEN_RE = re.compile(r'(-?)"([^"]*)"|(\S+)')


# ---- index maintenance (records use triggers; files use these) --------------------

def upsert(conn, item_type: str, item_id: int, title: str, body: str, page: int | None = None):
    if page is None:
        conn.execute("DELETE FROM search_index WHERE item_type = ? AND item_id = ?", (item_type, item_id))
    else:
        conn.execute("DELETE FROM search_index WHERE item_type = ? AND item_id = ? AND page = ?", (item_type, item_id, page))
    conn.execute("INSERT INTO search_index (title, body, item_type, item_id, page) VALUES (?, ?, ?, ?, ?)",
                 (title, body, item_type, item_id, page))


def delete(conn, item_type: str, item_id: int):
    conn.execute("DELETE FROM search_index WHERE item_type = ? AND item_id = ?", (item_type, item_id))


# ---- query translation --------------------------------------------------------------

def _quote(term: str) -> str:
    return '"' + term.replace('"', "") + '"'


def to_fts(user_query: str) -> str | None:
    """Translate user syntax to FTS5: words (AND), OR, "exact phrase", prefix*, -exclude (NOT).

    Every term is quoted, so stray FTS5 syntax characters in the input cannot break the query.
    Returns None when nothing positive is left to search for.
    """
    positive, negative = [], []
    for m in TOKEN_RE.finditer(user_query or ""):
        neg, phrase, word = m.group(1), m.group(2), m.group(3)
        if phrase is not None:
            if phrase.strip():
                (negative if neg else positive).append(_quote(phrase.strip()))
            continue
        if word == "OR":
            if positive and positive[-1] != "OR":
                positive.append("OR")
            continue
        is_neg = word.startswith("-") and len(word) > 1
        word = word.lstrip("-") if is_neg else word
        prefix = word.endswith("*")
        core = re.sub(r"[^\w\-']+", " ", word.rstrip("*")).strip()
        if not core:
            continue
        term = _quote(core) + ("*" if prefix else "")
        (negative if is_neg else positive).append(term)
    while positive and positive[-1] == "OR":
        positive.pop()
    if positive and positive[0] == "OR":
        positive.pop(0)
    if not positive:
        return None
    expr = " ".join(positive)
    if negative:
        expr = f"({expr})" + "".join(f" NOT {n}" for n in negative)
    return expr


def as_phrase(user_query: str) -> str | None:
    text = re.sub(r'["*]', " ", user_query or "").strip()
    return _quote(text) if text else None


def safe_snippet(raw: str) -> str:
    """HTML-escape everything except the highlight markers."""
    return html.escape(raw or "").replace(SNIP_OPEN, "<mark>").replace(SNIP_CLOSE, "</mark>")


# ---- query --------------------------------------------------------------------------

def _match(conn, expr: str, limit: int):
    return conn.execute(
        f"SELECT item_type, item_id, page, title, "
        f"snippet(search_index, 1, '{SNIP_OPEN}', '{SNIP_CLOSE}', ' … ', 24) AS snip, "
        f"bm25(search_index, 5.0, 1.0) AS rank "
        f"FROM search_index WHERE search_index MATCH ? ORDER BY rank LIMIT ?", (expr, limit)).fetchall()


def run(conn, user_query: str, limit: int = 600):
    """Return (rows, used_expression). Falls back to a quoted phrase on FTS syntax errors."""
    expr = to_fts(user_query)
    if not expr:
        return [], None
    try:
        return _match(conn, expr, limit), expr
    except sqlite3.OperationalError:
        phrase = as_phrase(user_query)
        if not phrase:
            return [], None
        try:
            return _match(conn, phrase, limit), phrase
        except sqlite3.OperationalError:
            return [], None


def _meta(conn, item_type: str, ids: list[int]) -> dict:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    table = {"file_page": "files", "ref": "refs", "diary": "diary_entries", "task": "tasks", "inbox": "inbox",
             "experiment": "experiments", "label": "dataset_labels"}[item_type]
    return {r["id"]: r for r in conn.execute(f"SELECT * FROM {table} WHERE id IN ({marks})", ids)}


def _when(item_type, m):
    """A comparable date for recency ordering and the year filter."""
    try:
        if item_type == "file_page":
            return datetime.fromtimestamp(m["mtime"] or 0).date().isoformat()
        if item_type == "ref":
            return f"{m['year']}-12-31" if m["year"] else (m["created_at"] or "")[:10]
        if item_type == "diary":
            return m["meeting_date"]
        if item_type == "experiment":
            return (m["run_at"] or m["created_at"] or "")[:10]
        if item_type == "label":
            return m["event_date"] or (m["created_at"] or "")[:10]
        return (m["created_at"] or "")[:10]
    except (KeyError, IndexError, TypeError, ValueError, OSError):
        return ""


def query(conn, q: str, item_type: str = "", tag: str = "", year_from=None, year_to=None, folder: str = "",
          max_pages: int = 3) -> dict:
    """Grouped results: one entry per item, PDFs keep their best pages."""
    rows, expr = run(conn, q)
    groups: dict[tuple, dict] = {}
    for r in rows:
        if item_type and r["item_type"] != item_type:
            continue
        key = (r["item_type"], int(r["item_id"]))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"type": r["item_type"], "id": int(r["item_id"]), "title": r["title"], "rank": r["rank"],
                               "hits": []}
        if len(g["hits"]) < max_pages:
            g["hits"].append({"page": r["page"], "snippet": safe_snippet(r["snip"])})
        g["rank"] = min(g["rank"], r["rank"])
    return dict(finalize(conn, groups, tag, year_from, year_to, folder), expr=expr)


def finalize(conn, groups: dict, tag: str = "", year_from=None, year_to=None, folder: str = "") -> dict:
    """Attach metadata, apply filters, order by rank (lower is better) then recency, collapse identical files.

    groups: {(item_type, item_id): {"type", "id", "title", "rank", "hits"}} from keyword or semantic search.
    """
    by_type: dict[str, list[int]] = {}
    for t, i in groups:
        by_type.setdefault(t, []).append(i)
    meta = {t: _meta(conn, t, ids) for t, ids in by_type.items()}
    tagged = None
    if tag:
        tagged = {(t, r["item_id"]) for t, tt in TAG_TYPES.items() for r in conn.execute(
            "SELECT tg.item_id FROM taggings tg JOIN tags x ON x.id = tg.tag_id WHERE tg.item_type = ? AND x.name = ?",
            (tt, tag.lower()))}

    out = []
    for (t, i), g in groups.items():
        m = meta.get(t, {}).get(i)
        if m is None:
            continue  # stale index row
        if t == "file_page" and m["text_status"] == "missing":
            continue
        if tagged is not None and (t, i) not in tagged:
            continue
        when = _when(t, m)
        if (year_from and (not when or when[:4] < str(year_from))) or (year_to and (not when or when[:4] > str(year_to))):
            continue
        if folder and (t != "file_page" or not (m["rel_path"] == folder or m["rel_path"].startswith(folder.rstrip("/") + "/"))):
            continue
        g["meta"], g["when"] = m, when
        out.append(g)
    out.sort(key=lambda g: g["when"] or "", reverse=True)  # newest first...
    out.sort(key=lambda g: round(g["rank"], 4))              # ...within equal bm25 rank (stable sort)
    out = _collapse_copies(out)
    counts: dict[str, int] = {}
    for g in out:
        counts[g["type"]] = counts.get(g["type"], 0) + 1
    return {"results": out, "counts": counts}


def _collapse_copies(results: list[dict]) -> list[dict]:
    """Identical files (same SHA-256) show once, at the best-ranked copy, listing the other paths."""
    first: dict[str, dict] = {}
    out = []
    for g in results:
        sha = g["meta"]["sha256"] if g["type"] == "file_page" else None
        if sha and sha in first:
            first[sha]["copies"].append(g["meta"])
            continue
        g["copies"] = []
        if sha:
            first[sha] = g
        out.append(g)
    return out


def top_folders(conn) -> list[str]:
    seen = []
    for r in conn.execute("SELECT DISTINCT rel_path FROM files WHERE text_status != 'missing'"):
        parts = r["rel_path"].split("/")
        for depth in (1, 2):
            if len(parts) > depth:
                f = "/".join(parts[:depth])
                if f not in seen:
                    seen.append(f)
    return sorted(seen, key=str.lower)

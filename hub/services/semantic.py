"""Offline semantic ("meaning") search behind a feature flag.

PDF and document page text from search_index is split into ~500-word chunks, embedded with
all-MiniLM-L6-v2 and stored as normalised float32 blobs; a query is ranked by cosine similarity
(a dot product) in numpy. The model downloads once into data/models, then works offline.
"""
import html
import logging
import threading

import config
from hub.services import search

log = logging.getLogger(__name__)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_WORDS = 500
MIN_SCORE = 0.2
_model = None
_model_lock = threading.Lock()
_cache = {"key": None, "ids": None, "matrix": None}


def enabled(s: dict) -> bool:
    return (s.get("semantic_search_enabled") or "").lower() == "true"


def available() -> tuple[bool, str | None]:
    try:
        import numpy  # noqa: F401
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False, ("Semantic search needs the optional packages: "
                       r".venv\Scripts\pip install sentence-transformers numpy")
    return True, None


def _load_model():
    global _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(MODEL_NAME, cache_folder=str(config.DATA_DIR / "models"), device="cpu")
    return _model


def warm_up(s: dict, logger=None):
    """Load the model in the background at start-up so the first Meaning search is not slow (~15 s cold)."""
    if not enabled(s) or not available()[0]:
        return

    def run():
        try:
            _load_model()
        except Exception:  # offline before the first download: the search page explains
            (logger or log).warning("Semantic model could not be loaded yet", exc_info=True)
    threading.Thread(target=run, name="semantic-warmup", daemon=True).start()


def embed(texts: list[str]):
    """Return an (n, d) float32 array of L2-normalised embeddings. Replaced by a stub in tests."""
    import numpy as np
    vecs = _load_model().encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def chunk_text(text: str, words: int = CHUNK_WORDS) -> list[str]:
    tokens = (text or "").split()
    return [" ".join(tokens[i:i + words]) for i in range(0, len(tokens), words)]


def has_table(conn) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunks'").fetchone())


def status(conn) -> dict:
    files = conn.execute("SELECT COUNT(*) FROM files WHERE text_status = 'ok'").fetchone()[0]
    done = conn.execute("SELECT COUNT(DISTINCT file_id) FROM chunks").fetchone()[0] if has_table(conn) else 0
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] if has_table(conn) else 0
    return {"files": files, "embedded": done, "chunks": chunks, "pending": max(files - done, 0)}


def embed_pending(conn, limit_files: int | None = None) -> int:
    """Embed every extracted file that has no chunks yet. Returns the number of files embedded."""
    import numpy as np
    pending = conn.execute("SELECT f.id FROM files f WHERE f.text_status = 'ok' AND NOT EXISTS "
                           "(SELECT 1 FROM chunks c WHERE c.file_id = f.id) ORDER BY f.id").fetchall()
    n = 0
    for row in pending[:limit_files] if limit_files else pending:
        pages = conn.execute("SELECT page, body FROM search_index WHERE item_type = 'file_page' AND item_id = ? "
                             "ORDER BY page", (row["id"],)).fetchall()
        items = [(p["page"], i, chunk) for p in pages for i, chunk in enumerate(chunk_text(p["body"]))]
        if not items:
            # Nothing to embed (e.g. a scanned PDF); store a marker so it is not retried every scan.
            items = [(None, 0, "")]
        vecs = embed([t or " " for _, _, t in items])
        with conn:
            conn.executemany("INSERT INTO chunks (file_id, page, chunk_no, text, vector, model) VALUES (?, ?, ?, ?, ?, ?)",
                             [(row["id"], page, i, text, np.asarray(v, dtype=np.float32).tobytes(), MODEL_NAME)
                              for (page, i, text), v in zip(items, vecs)])
        n += 1
    _cache["key"] = None
    return n


def _matrix(conn):
    """All chunk vectors as one (n, d) matrix, cached until the chunk table changes."""
    import numpy as np
    key = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM chunks WHERE text != ''").fetchone()
    key = (key[0], key[1])
    if _cache["key"] != key:
        rows = conn.execute("SELECT id, vector FROM chunks WHERE text != '' ORDER BY id").fetchall()
        _cache.update(key=key, ids=[r["id"] for r in rows],
                      matrix=np.vstack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows]) if rows else None)
    return _cache["ids"], _cache["matrix"]


def query(conn, q: str, tag: str = "", year_from=None, year_to=None, folder: str = "", top_k: int = 60,
          max_pages: int = 3) -> dict:
    import numpy as np
    if not (q or "").strip() or not has_table(conn):
        return {"results": [], "counts": {}}
    ids, matrix = _matrix(conn)
    if matrix is None:
        return {"results": [], "counts": {}}
    qv = embed([q.strip()])[0]
    scores = matrix @ qv
    order = np.argsort(-scores)[:top_k]
    chosen = [(ids[i], float(scores[i])) for i in order if scores[i] >= MIN_SCORE]
    if not chosen:
        return {"results": [], "counts": {}}
    marks = ",".join("?" * len(chosen))
    rows = {r["id"]: r for r in conn.execute(f"SELECT c.id, c.file_id, c.page, c.text, f.name FROM chunks c "
                                             f"JOIN files f ON f.id = c.file_id WHERE c.id IN ({marks})", [c for c, _ in chosen])}
    groups: dict[tuple, dict] = {}
    for chunk_id, score in chosen:
        r = rows[chunk_id]
        key = ("file_page", r["file_id"])
        g = groups.setdefault(key, {"type": "file_page", "id": r["file_id"], "title": r["name"], "rank": -score, "hits": [],
                                    "score": score})
        if len(g["hits"]) < max_pages:
            g["hits"].append({"page": r["page"], "snippet": html.escape(_excerpt(r["text"])), "score": round(score, 2)})
    return search.finalize(conn, groups, tag, year_from, year_to, folder)


def _excerpt(text: str, words: int = 40) -> str:
    tokens = text.split()
    return " ".join(tokens[:words]) + (" …" if len(tokens) > words else "")

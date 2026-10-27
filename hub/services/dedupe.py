"""File hashing and reference duplicate checks."""
import hashlib
from difflib import SequenceMatcher
from pathlib import Path

from hub.services import refs_text

TITLE_RATIO = 0.92
CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def doi_duplicate(conn, doi: str | None, exclude_id: int | None = None):
    if not doi:
        return None
    return conn.execute("SELECT id, title, cite_key FROM refs WHERE lower(doi) = lower(?) AND id IS NOT ?",
                        (doi.strip(), exclude_id)).fetchone()


def title_duplicates(conn, title: str, year, exclude_id: int | None = None) -> list:
    """Near-identical normalised titles (ratio >= 0.92) with the same year +/- 1."""
    target = refs_text.normalise_title(title)
    if not target:
        return []
    out = []
    for r in conn.execute("SELECT id, title, year, cite_key, created_at FROM refs WHERE id IS NOT ?", (exclude_id,)):
        if year and r["year"] and abs(int(r["year"]) - int(year)) > 1:
            continue
        if SequenceMatcher(None, target, refs_text.normalise_title(r["title"])).ratio() >= TITLE_RATIO:
            out.append(r)
    return out


def duplicate_file_groups(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM files WHERE sha256 IN (SELECT sha256 FROM files WHERE text_status != 'missing' AND sha256 IS NOT NULL "
        "GROUP BY sha256 HAVING COUNT(*) > 1) AND text_status != 'missing' ORDER BY size_bytes DESC, sha256, rel_path").fetchall()
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["sha256"], []).append(r)
    return [{"sha256": h, "files": fs, "size": fs[0]["size_bytes"], "wasted": fs[0]["size_bytes"] * (len(fs) - 1)}
            for h, fs in groups.items()]

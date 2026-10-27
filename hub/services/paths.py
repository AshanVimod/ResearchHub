"""Path-safety rule used by every file operation."""
from pathlib import Path

import config
from hub.services import settings as st


def roots(s: dict) -> list[Path]:
    return [Path(r) for r in st.as_list(s, "research_roots")]


def is_safe(path, s: dict, data_dir: Path | None = None) -> bool:
    """True when the resolved path is inside a configured research root or data/."""
    try:
        p = Path(path).resolve()
    except (OSError, ValueError):
        return False
    allowed = [r.resolve() for r in roots(s)] + [Path(data_dir or config.DATA_DIR).resolve()]
    return any(p == a or p.is_relative_to(a) for a in allowed)


def file_path(row) -> Path:
    return Path(row["root"]) / Path(row["rel_path"])


def exists(path: Path) -> bool:
    from hub.services.indexer import os_path
    return os_path(path).exists()


def ref_pdf_path(ref, library: Path) -> Path | None:
    """Absolute path of a reference's PDF: relative paths live in data/library."""
    if not ref["pdf_path"]:
        return None
    p = Path(ref["pdf_path"])
    return p if p.is_absolute() else library / p

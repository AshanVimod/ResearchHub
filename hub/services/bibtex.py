"""Minimal BibTeX reader/writer. No external dependency; handles nested braces and quotes."""
import json
import re
import unicodedata

from hub.services import refs_text

TYPE_MAP = {
    "article": "journal", "inproceedings": "conference", "conference": "conference", "proceedings": "conference",
    "book": "book", "incollection": "chapter", "inbook": "chapter", "phdthesis": "thesis",
    "mastersthesis": "thesis", "techreport": "report", "dataset": "dataset", "software": "software",
    "online": "website", "electronic": "website", "misc": "website", "unpublished": "preprint",
}
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
LATEX = {r"\&": "&", r"\%": "%", r"\_": "_", r"\$": "$", r"\#": "#", "--": "–", "~": " ",
         r"\'e": "é", r"\'{e}": "é", r'\"o': "ö", r'\"{o}': "ö", r'\"u': "ü", r'\"{u}': "ü", r"\`e": "è", r"\c{c}": "ç"}


def _value(text: str, i: int):
    """Read a field value starting at text[i]. Returns (raw value, next index)."""
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        return "", i
    if text[i] == "{":
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{" and text[j - 1:j] != "\\":
                depth += 1
            elif text[j] == "}" and text[j - 1:j] != "\\":
                depth -= 1
                if depth == 0:
                    return text[i + 1:j], j + 1
            j += 1
        return text[i + 1:], len(text)
    if text[i] == '"':
        j, depth = i + 1, 0
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            elif text[j] == '"' and depth == 0 and text[j - 1] != "\\":
                return text[i + 1:j], j + 1
            j += 1
        return text[i + 1:], len(text)
    m = re.match(r"[^,}\s]+", text[i:])
    return (m.group(0), i + m.end()) if m else ("", i)


# LaTeX accent command -> Unicode combining mark, e.g. {\"e} -> ë, \c{c} -> ç
ACCENTS = {"'": "́", "`": "̀", "^": "̂", '"': "̈", "~": "̃", "c": "̧"}
ACCENT_RE = re.compile(r"\{?\\(['`^\"~]|c\s*)\{?([A-Za-z])\}?\}?")


def _accent(m) -> str:
    return unicodedata.normalize("NFC", m.group(2) + ACCENTS[m.group(1).strip()])


def _clean(v: str) -> str:
    v = ACCENT_RE.sub(_accent, v)
    for k, rep in LATEX.items():
        v = v.replace(k, rep)
    return re.sub(r"\s+", " ", v).strip()


def parse_entries(text: str) -> list[dict]:
    """Return raw entries: {'type', 'key', 'fields': {name: raw value}}."""
    entries = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]*)\s*,", text):
        kind = m.group(1).lower()
        if kind in ("comment", "preamble", "string"):
            continue
        fields, i = {}, m.end()
        while i < len(text):
            fm = re.compile(r"\s*([A-Za-z][\w\-]*)\s*=\s*").match(text, i)
            if not fm:
                break
            value, i = _value(text, fm.end())
            fields[fm.group(1).lower()] = value
            sep = re.compile(r"\s*(#\s*)?,?\s*").match(text, i)
            i = sep.end()
            if i < len(text) and text[i] == "}":
                break
        entries.append({"type": kind, "key": m.group(2), "fields": fields})
    return entries


def _authors(raw: str) -> list[dict]:
    out = []
    for name in re.split(r"\s+and\s+", raw or "", flags=re.I):
        name = _clean(name.replace("{", "").replace("}", ""))
        if not name or name.lower() == "others":
            continue
        if "," in name:
            family, given = [p.strip() for p in name.split(",", 1)]
        else:
            given, _, family = name.rpartition(" ")
        out.append({"given": given, "family": family})
    return out


def to_ref(entry: dict) -> dict:
    f = {k: v for k, v in entry["fields"].items()}
    kind = TYPE_MAP.get(entry["type"], "journal")
    eprint = f.get("eprint") or ""
    if (f.get("archiveprefix", "").lower() == "arxiv" or "arxiv" in f.get("journal", "").lower()) and eprint:
        kind = "preprint"
    if entry["type"] == "misc" and not f.get("url") and not f.get("howpublished"):
        kind = "preprint" if eprint else "report"
    raw_title = f.get("title", "")
    title = refs_text.sentence_case(_clean(raw_title))
    month = f.get("month", "").strip().lower()[:3]
    year = re.search(r"\d{4}", f.get("year", "") or f.get("date", ""))
    accessed = f.get("urldate") or ""
    return {
        "ref_type": kind,
        "title": title.replace("{", "").replace("}", ""),
        "authors": _authors(f.get("author", "")),
        "year": int(year.group(0)) if year else None,
        "month": MONTHS.get(month) or (int(month) if month.isdigit() else None),
        "container": _clean(f.get("journal") or f.get("booktitle") or f.get("howpublished") or f.get("school") or "")
        .replace("{", "").replace("}", ""),
        "volume": _clean(f.get("volume", "")),
        "issue": _clean(f.get("number", "")),
        "pages": _clean(f.get("pages", "")).replace("–", "-"),
        "publisher": _clean(f.get("publisher") or f.get("institution") or f.get("organization") or f.get("school") or ""),
        "location": _clean(f.get("address", "")),
        "doi": _clean(f.get("doi", "")).lower(),
        "url": _clean(f.get("url", "")),
        "arxiv_id": eprint if kind == "preprint" else "",
        "accessed_date": accessed[:10],
        "abstract": _clean(f.get("abstract", "")),
        "cite_key_hint": entry.get("key") or "",
    }


def parse(text: str) -> list[dict]:
    return [to_ref(e) for e in parse_entries(text or "")]


# ---- export -----------------------------------------------------------------

OUT_TYPE = {"journal": "article", "conference": "inproceedings", "preprint": "misc", "book": "book",
            "chapter": "incollection", "thesis": "phdthesis", "report": "techreport", "website": "misc",
            "dataset": "misc", "software": "misc"}


def _esc(v) -> str:
    return str(v).replace("{", "").replace("}", "").replace("&", r"\&").replace("%", r"\%")


def dump(ref) -> str:
    authors = json.loads(ref["authors_json"] or "[]")
    container_key = {"journal": "journal", "conference": "booktitle", "chapter": "booktitle", "thesis": "school"}.get(ref["ref_type"], "howpublished")
    fields = [("author", " and ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") for a in authors)),
              (container_key, ref["container"]), ("year", ref["year"]), ("volume", ref["volume"]), ("number", ref["issue"]),
              ("pages", (ref["pages"] or "").replace("-", "--")), ("publisher", ref["publisher"]), ("address", ref["location"]),
              ("doi", ref["doi"]), ("url", ref["url"]), ("urldate", ref["accessed_date"])]
    if ref["arxiv_id"]:
        fields += [("eprint", ref["arxiv_id"]), ("archiveprefix", "arXiv")]
    # Double braces keep the title's capitalisation as written.
    lines = [f"  title = {{{{{_esc(ref['title'])}}}}}"] + [f"  {k} = {{{_esc(v)}}}" for k, v in fields if v]
    body = ",\n".join(lines)
    return f"@{OUT_TYPE.get(ref['ref_type'], 'misc')}{{{ref['cite_key']},\n{body}\n}}\n"

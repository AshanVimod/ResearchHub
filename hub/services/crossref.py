"""DOI (Crossref) and arXiv lookups. Parsing is pure; fetching has timeouts and one retry."""
import html
import re
import xml.etree.ElementTree as ET

from hub.services import refs_text

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
ARXIV_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:)?\s*(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", re.I)
TIMEOUT = 10

TYPE_MAP = {
    "journal-article": "journal", "proceedings-article": "conference", "posted-content": "preprint",
    "book": "book", "monograph": "book", "edited-book": "book", "reference-book": "book",
    "book-chapter": "chapter", "book-section": "chapter", "book-part": "chapter",
    "dissertation": "thesis", "report": "report", "report-component": "report",
    "dataset": "dataset", "component": "dataset",
}


class LookupError_(Exception):
    """Lookup failed; the message is safe to show to the user."""


def normalise_doi(value: str) -> str:
    v = (value or "").strip()
    v = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", v, flags=re.I)
    v = re.sub(r"^doi:\s*", "", v, flags=re.I)
    return v.strip().rstrip(".").lower()


def find_doi(text: str) -> str | None:
    m = DOI_RE.search(text or "")
    return normalise_doi(m.group(0).rstrip(").,;]")) if m else None


def parse_arxiv_id(value: str) -> str | None:
    m = ARXIV_RE.search((value or "").strip())
    return m.group(1) if m else None


def _clean(s: str | None) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", "", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def parse_crossref(message: dict) -> dict:
    """Map a Crossref /works message to ref fields."""
    title = _clean((message.get("title") or [""])[0])
    subtitle = _clean((message.get("subtitle") or [""])[0]) if message.get("subtitle") else ""
    if subtitle and subtitle.lower() not in title.lower():
        title = f"{title}: {subtitle}"
    kind = TYPE_MAP.get(message.get("type", ""), "journal")
    parts = ((message.get("issued") or {}).get("date-parts") or [[None]])[0]
    page = (message.get("page") or "").strip()
    article_no = (message.get("article-number") or "").strip()
    if kind == "journal" and page and "-" not in page and not article_no:
        # MDPI and similar publishers put the article number in `page`.
        article_no, page = page, ""
    authors = [{"given": _clean(a.get("given")), "family": _clean(a.get("family") or a.get("name"))}
               for a in message.get("author") or [] if a.get("family") or a.get("name")]
    return {
        "ref_type": kind,
        "title": refs_text.sentence_case(title),
        "authors": authors,
        "year": parts[0] if parts and parts[0] else None,
        "container": _clean((message.get("container-title") or [""])[0]) if message.get("container-title") else "",
        "volume": message.get("volume") or "",
        "issue": message.get("issue") or "",
        "pages": page,
        "article_no": article_no,
        "publisher": _clean(message.get("publisher")),
        "doi": normalise_doi(message.get("DOI") or ""),
        "url": message.get("URL") or "",
        "abstract": _clean(message.get("abstract")),
    }


ATOM = "{http://www.w3.org/2005/Atom}"


def parse_arxiv(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    entry = root.find(f"{ATOM}entry")
    if entry is None or entry.find(f"{ATOM}title") is None:
        raise LookupError_("arXiv has no record with that id.")
    raw_id = entry.findtext(f"{ATOM}id") or ""
    arxiv_id = parse_arxiv_id(raw_id) or ""
    authors = []
    for a in entry.findall(f"{ATOM}author"):
        name = (a.findtext(f"{ATOM}name") or "").strip()
        if name:
            given, _, family = name.rpartition(" ")
            authors.append({"given": given, "family": family})
    published = entry.findtext(f"{ATOM}published") or ""
    doi = entry.findtext("{http://arxiv.org/schemas/atom}doi") or ""
    return {
        "ref_type": "preprint",
        "title": refs_text.sentence_case(_clean(entry.findtext(f"{ATOM}title"))),
        "authors": authors,
        "year": int(published[:4]) if published[:4].isdigit() else None,
        "container": "arXiv",
        "arxiv_id": arxiv_id,
        "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
        "doi": normalise_doi(doi) if doi else "",
        "abstract": _clean(entry.findtext(f"{ATOM}summary")),
    }


def _get(url: str, headers: dict):
    import requests
    last = None
    for _attempt in range(2):  # one retry
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            if r.status_code == 404:
                raise LookupError_("Not found. Check the identifier.")
            r.raise_for_status()
            return r
        except LookupError_:
            raise
        except requests.RequestException as exc:
            last = exc
    raise LookupError_(f"Lookup failed ({type(last).__name__}). You may be offline; fill the form by hand.")


def lookup_doi(doi: str, mailto: str = "") -> dict:
    doi = normalise_doi(doi)
    if not DOI_RE.fullmatch(doi):
        raise LookupError_("That does not look like a DOI (it should start with 10.).")
    ua = "ResearchHub/1.0 (local research manager" + (f"; mailto:{mailto}" if mailto else "") + ")"
    r = _get(f"https://api.crossref.org/works/{doi}", {"User-Agent": ua})
    return parse_crossref(r.json()["message"])


def lookup_arxiv(value: str) -> dict:
    arxiv_id = parse_arxiv_id(value)
    if not arxiv_id:
        raise LookupError_("That does not look like an arXiv id (e.g. 2607.19259).")
    r = _get(f"https://export.arxiv.org/api/query?id_list={arxiv_id}", {"User-Agent": "ResearchHub/1.0"})
    return parse_arxiv(r.text)

"""IEEE reference formatter.

format(ref) returns segments; plain()/html() render them. A segment is (text, italic).
"""
import html as _html
import json
import re

MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]

# Applied to conference proceedings names, longest first.
PROC_ABBREV = [
    (r"\bProceedings of the\b", "Proc."), (r"\bProceedings of\b", "Proc."), (r"\bProceedings\b", "Proc."),
    (r"\bInternational\b", "Int."), (r"\bConference on\b", "Conf."), (r"\bConference\b", "Conf."),
    (r"\bSymposium on\b", "Symp."), (r"\bSymposium\b", "Symp."), (r"\bWorkshop on\b", "Workshop"),
    (r"\bAnnual\b", "Annu."), (r"\bTransactions on\b", "Trans."), (r"\bTransactions\b", "Trans."),
]


def authors_of(ref) -> list[dict]:
    raw = ref["authors_json"] if "authors_json" in ref.keys() else "[]"
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [a for a in data if isinstance(a, dict) and (a.get("family") or a.get("given"))]


def initials(given: str) -> str:
    out = []
    for part in (given or "").replace(".", ". ").split():
        if "-" in part.strip("."):
            out.append("-".join(p[0] + "." for p in part.strip(".").split("-") if p))
        elif part.strip("."):
            out.append(part.strip(".")[0] + ".")
    return " ".join(out)


def author_name(a: dict) -> str:
    given, family = (a.get("given") or "").strip(), (a.get("family") or "").strip()
    if not given:
        return family
    return f"{initials(given)} {family}".strip()


def author_list(authors: list[dict]) -> str:
    names = [author_name(a) for a in authors]
    if not names:
        return ""
    if len(names) >= 7:
        return f"{names[0]} et al."
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]


def en_dash(pages: str) -> str:
    return re.sub(r"\s*[-‐‑–—]+\s*", "–", pages.strip())


def proceedings(name: str) -> str:
    for pattern, rep in PROC_ABBREV:
        name = re.sub(pattern, rep, name)
    return re.sub(r"\s+", " ", name).strip()


def quoted_title(title: str) -> str:
    """Title inside curly quotes; inner double quotes become single curly quotes."""
    t = title.strip()
    t = re.sub(r'"([^"]*)"', "‘\\1’", t)
    t = re.sub(r"“([^”]*)”", "‘\\1’", t)
    return t


def _date(ref) -> str:
    year, month = ref["year"], ref["month"]
    if year and month and 1 <= int(month) <= 12:
        return f"{MONTHS[int(month) - 1]} {year}"
    return str(year) if year else ""


def _accessed(value: str | None) -> str:
    if not value:
        return ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if not m:
        return value
    y, mo, d = m.groups()
    return f"{MONTHS[int(mo) - 1]} {int(d)}, {y}"


def _get(ref, key):
    try:
        v = ref[key]
    except (KeyError, IndexError):
        return None
    return v.strip() if isinstance(v, str) else v


def format(ref) -> list[tuple[str, bool]]:  # noqa: A001
    """Build the IEEE reference as segments. Missing fields are omitted cleanly."""
    g = lambda k: _get(ref, k)  # noqa: E731
    kind = g("ref_type") or "journal"
    authors = author_list(authors_of(ref))
    title = g("title") or ""
    doi = g("doi")
    segs: list[tuple[str, bool]] = []

    def add(text, italic=False):
        if text:
            segs.append((text, italic))

    lead = f"{authors}, " if authors else ""
    if kind == "book":
        add(lead)
        add(title, True)
        tail = []
        place = ": ".join(x for x in [g("location"), g("publisher")] if x)
        if place:
            tail.append(place)
        if _date(ref):
            tail.append(_date(ref))
        add(". " + ", ".join(tail) if tail else "")
        if doi:
            add(f", doi: {doi}")
        return _finish(segs)

    add(f"{lead}“{quoted_title(title)},” ")
    parts: list[list[tuple[str, bool]]] = []  # each item: segments joined with ", "

    def part(text, italic=False):
        if text:
            parts.append([(text, italic)])

    if kind == "journal":
        part(g("container"), True)
        part(f"vol. {g('volume')}" if g("volume") else "")
        part(f"no. {g('issue')}" if g("issue") else "")
        if g("pages"):
            part(f"pp. {en_dash(g('pages'))}" if re.search(r"[-–]", g("pages")) else f"p. {g('pages')}")
        part(f"Art. no. {g('article_no')}" if g("article_no") else "")
        part(_date(ref))
        part(f"doi: {doi}" if doi else "")
    elif kind == "conference":
        if g("container"):
            parts.append([("in ", False), (proceedings(g("container")), True)])
        part(g("location"))
        part(_date(ref))
        part(f"pp. {en_dash(g('pages'))}" if g("pages") else "")
        part(f"Art. no. {g('article_no')}" if g("article_no") else "")
        part(f"doi: {doi}" if doi else "")
    elif kind == "preprint":
        if g("arxiv_id"):
            part(f"arXiv:{g('arxiv_id')}")
        else:
            part(g("container"), True)
        part(_date(ref))
        part(f"doi: {doi}" if doi else "")
    elif kind == "chapter":
        if g("container"):
            parts.append([("in ", False), (g("container"), True)])
        place = ": ".join(x for x in [g("location"), g("publisher")] if x)
        part(place)
        part(_date(ref))
        part(f"pp. {en_dash(g('pages'))}" if g("pages") else "")
        part(f"doi: {doi}" if doi else "")
    elif kind == "thesis":
        part(g("container") or "Thesis")
        part(g("publisher"))
        part(g("location"))
        part(_date(ref))
    elif kind == "report":
        part(g("publisher") or g("container"))
        part(g("location"))
        part(f"Tech. Rep. {g('article_no') or g('issue')}" if (g("article_no") or g("issue")) else "")
        part(_date(ref))
        part(f"doi: {doi}" if doi else "")
    else:  # website, dataset, software
        part(g("container") if kind == "website" else (g("publisher") or g("container")), kind != "website")
        if kind != "website":
            part(f"version {g('volume')}" if g("volume") else "")
        part(_date(ref))
        part(f"doi: {doi}" if doi else "")

    for i, p in enumerate(parts):
        if i:
            add(", ")
        segs.extend(p)

    if kind in ("website", "dataset", "software") and g("url"):
        add(". " if parts else "")
        add(f"[Online]. Available: {g('url')}")
        if g("accessed_date"):
            add(f". Accessed: {_accessed(g('accessed_date'))}")
    return _finish(segs)


def _finish(segs):
    """Strip a trailing comma/space and end with a single full stop (not after a bare URL)."""
    while segs and not segs[-1][0].strip():
        segs.pop()
    if not segs:
        return segs
    text, it = segs[-1]
    text = text.rstrip()
    if text.endswith(",”"):  # nothing after the title: close it with a full stop instead
        segs[-1] = (text[:-2] + ".”", it)
        return segs
    text = text.rstrip(",")
    if re.search(r"Available: \S+$", text):
        segs[-1] = (text, it)
        return segs
    if not text.endswith("."):
        text += "."
    segs[-1] = (text, it)
    return segs


def plain(ref) -> str:
    return "".join(t for t, _ in format(ref))


def html(ref) -> str:
    return "".join(f"<i>{_html.escape(t)}</i>" if it else _html.escape(t) for t, it in format(ref))

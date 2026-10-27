"""Small shared helpers: clock, CSRF, safe Markdown, formatting."""
import html
import re
import secrets
from datetime import date, datetime

from flask import abort, current_app, request, session
from markupsafe import Markup


# ---- clock (overridable in tests via app.config["NOW"]) ---------------------

def now() -> datetime:
    fixed = current_app.config.get("NOW") if current_app else None
    return fixed or datetime.now().replace(microsecond=0)


def today() -> date:
    return now().date()


# ---- CSRF --------------------------------------------------------

def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


CSRF_EXEMPT_JSON = {"experiments.api_create"}


def check_csrf():
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        if current_app.config.get("CSRF_DISABLED"):
            return
        # The notebook logging API cannot carry a session token. It accepts JSON only, and a
        # cross-site page cannot send application/json without a CORS preflight the app never grants.
        if request.endpoint in CSRF_EXEMPT_JSON and request.is_json:
            return
        sent = request.headers.get("X-CSRFToken") or request.form.get("csrf_token")
        if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
            abort(400, "Missing or invalid CSRF token. Reload the page and try again.")


# ---- tiny safe Markdown (escape first) --------------------------------------

_INLINE = [
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\w)"), r"<em>\1</em>"),
    (re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)"), r'<a href="\2" target="_blank" rel="noopener">\1</a>'),
]


def markdown(text: str | None) -> Markup:
    if not text:
        return Markup("")
    out, para, items, kind = [], [], [], None

    def inline(s):
        for rx, rep in _INLINE:
            s = rx.sub(rep, s)
        return s

    def flush():
        nonlocal para, items, kind
        if para:
            out.append("<p>" + "<br>".join(inline(p) for p in para) + "</p>")
            para = []
        if items:
            out.append(f"<{kind}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{kind}>")
            items, kind = [], None

    for line in html.escape(text).splitlines():
        stripped = line.strip()
        bullet = re.match(r"^[-*]\s+(.*)", stripped)
        number = re.match(r"^\d+[.)]\s+(.*)", stripped)
        if bullet or number:
            k = "ul" if bullet else "ol"
            if para or (kind and kind != k):
                flush()
            kind = k
            items.append((bullet or number).group(1))
        elif not stripped:
            flush()
        else:
            if items:
                flush()
            para.append(stripped)
    flush()
    return Markup("".join(out))


# ---- formatting --------------------------------------------------------------

def nice_date(value, fmt="%d %b %Y") -> str:
    if not value:
        return ""
    try:
        return date.fromisoformat(str(value)[:10]).strftime(fmt).lstrip("0")
    except ValueError:
        return str(value)


def hours(minutes) -> str:
    minutes = int(minutes or 0)
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def filesize(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def timestamp(value, fmt="%d %b %Y %H:%M") -> str:
    if value in (None, ""):
        return ""
    return datetime.fromtimestamp(float(value)).strftime(fmt).lstrip("0")

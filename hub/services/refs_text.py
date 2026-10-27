"""Text helpers for references: sentence case, title normalisation, cite keys."""
import re
import unicodedata

# Words kept capitalised by sentence_case even though they look like ordinary words.
PROPER = {
    "i", "china", "chinese", "india", "indian", "asia", "asian",
    "europe", "european", "america", "american", "english", "africa", "african", "australia", "japan",
    "japanese", "korea", "korean", "bayesian", "markov", "gaussian", "shapley", "monte", "carlo",
    "altman", "benford", "python", "kaggle", "twitter", "google", "microsoft",
}
STOPWORDS = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "with", "using", "via", "from", "by", "at",
             "is", "are", "toward", "towards", "into", "how", "what", "why", "do", "does"}


def ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")


def _keep(word: str) -> bool:
    core = re.sub(r"^[^\w]+|[^\w]+$", "", word)
    if not core:
        return True
    if any(ch.isdigit() for ch in core):
        return True
    if any(ch.isupper() for ch in core[1:]):  # LSTM, XGBoost, SIGKDD, iPhone
        return True
    return core.lower() in PROPER


def sentence_case(title: str) -> str:
    """Sentence case that keeps acronyms, mixed-case words, proper nouns in PROPER and {braced} text.

    The first word, and the first word after a colon, question or exclamation mark, are capitalised.
    """
    if not title:
        return title
    protected = []

    def stash(m):
        protected.append(m.group(1))
        return f"\x00{len(protected) - 1}\x00"

    t = re.sub(r"\{([^{}]*)\}", stash, title)
    out, capital_next = [], True
    for token in re.split(r"(\s+)", t):
        if not token or token.isspace() or "\x00" in token:
            out.append(token)
            if "\x00" in token:
                capital_next = False
            continue
        lead = re.match(r"^[^\w]*", token).group(0)
        rest = token[len(lead):]
        if capital_next and rest:
            word = rest[0].upper() + (rest[1:] if _keep(rest) else rest[1:].lower())
        elif _keep(rest):
            word = rest
        else:
            word = rest.lower()
        out.append(lead + word)
        capital_next = bool(re.search(r"[:?!]\W*$", token))
    result = "".join(out)
    return re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], result)


def normalise_title(title: str) -> str:
    """Lower-case, strip punctuation and whitespace, for duplicate comparison."""
    return re.sub(r"[\W_]+", "", ascii_fold(title or "").lower())


def cite_key_base(authors: list[dict], year, title: str) -> str:
    family = ""
    if authors:
        family = authors[0].get("family") or authors[0].get("given") or ""
    family = re.sub(r"[^a-z]", "", ascii_fold(family).lower()) or "anon"
    word = ""
    for w in re.findall(r"[A-Za-z0-9]+", ascii_fold(title or "")):
        if w.lower() not in STOPWORDS:
            word = w.lower()
            break
    return f"{family}{year or ''}{word}"

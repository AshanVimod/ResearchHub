"""Viva preparation: slide checklist, practice runs, question bank and drill."""
import random

TALK_SECONDS = 15 * 60
QA_SECONDS = 5 * 60
WARN_SECONDS = 2 * 60

# A typical presentation order; edit the checklist in the app.
SLIDES = [
    "Title slide: project title, supervisor, index number",
    "Introduction: problem, aims and objectives",
    "Motivation",
    "Literature Review",
    "Methodology",
    "Results",
    "Discussion",
    "Conclusion and Future Work",
    "Recommendation",
    "References",
]
CATEGORIES = {"method": "Method", "data": "Data", "results": "Results", "ethics": "Ethics",
              "future_work": "Future work", "other": "Other"}
CONFIDENCE = {1: "Shaky", 2: "Okay", 3: "Confident"}


def seed(conn):
    with conn:
        if not conn.execute("SELECT 1 FROM checklist_items WHERE list_code = 'VIVA_SLIDES'").fetchone():
            conn.executemany("INSERT INTO checklist_items (list_code, ordinal, text) VALUES ('VIVA_SLIDES', ?, ?)",
                             list(enumerate(SLIDES)))


def clean_question(data: dict) -> tuple[dict, dict]:
    q = {"question": (data.get("question") or "").strip(), "answer": (data.get("answer") or "").strip() or None,
         "category": data.get("category") if data.get("category") in CATEGORIES else "other",
         "confidence": int(data["confidence"]) if str(data.get("confidence")) in ("1", "2", "3") else 1}
    errors = {"question": "Write the question."} if not q["question"] else {}
    return q, errors


def next_drill(conn, seen: list[int], category: str | None = None, rng=random):
    """Lowest confidence first; random among equals; skip questions already seen this session."""
    sql, args = "SELECT * FROM viva_questions WHERE 1=1", []
    if seen:
        sql += f" AND id NOT IN ({','.join('?' * len(seen))})"
        args += seen
    if category in CATEGORIES:
        sql += " AND category = ?"
        args.append(category)
    rows = conn.execute(sql, args).fetchall()
    if not rows:
        return None
    low = min(r["confidence"] or 1 for r in rows)
    return rng.choice([r for r in rows if (r["confidence"] or 1) == low])


def mmss(seconds) -> str:
    seconds = int(seconds or 0)
    sign = "-" if seconds < 0 else ""
    m, s = divmod(abs(seconds), 60)
    return f"{sign}{m}:{s:02d}"

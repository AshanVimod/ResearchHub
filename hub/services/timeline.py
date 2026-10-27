"""Week, phase and milestone maths."""
from datetime import date, timedelta

import config

# code, title, start_week, end_week, marks_weight, notes
MILESTONE_SEED = [
    ("OUTLINE", "Supervisor, outline and project start", 2, 3, None, "Outline submitted to course coordinator"),
    ("PROPOSAL_DEFENCE", "Proposal defence presentation (10 min)", 6, 7, 10, "Proposal max 10 pages, department template"),
    ("EXECUTION_1", "Carry out project, analysis, preliminary conclusions", 7, 15, None, None),
    ("MIDTERM", "Mid-term progress review", 16, 17, 15, "Within the week after Semester 1 exams"),
    ("EXECUTION_2", "Continue the project", 17, 30, None, None),
    ("DRAFT_THESIS", "Draft thesis to supervisor", 31, 31, None, "At least 10,000 words; supervisor review at least 1 week ahead"),
    ("FINAL_THESIS", "Final draft (loose bound) to department", 32, 32, 25, "Plagiarism check before submission"),
    ("VIVA", "Oral presentation (15 + 5 min Q&A)", 33, 34, 40, None),
    ("DIARY", "Project diary (continuous)", 1, 34, 10, "At least 5 signed meetings per semester"),
    ("IEEE_PAPER", "IEEE conference manuscript (bonus)", 27, 32, 5, "Optional, capped at 100"),
]

# Continuous milestones never define the current phase.
CONTINUOUS = {"DIARY"}


def week_of(d: date, start: date) -> int:
    """Raw week number; week 1 starts on the project start date."""
    return (d - start).days // 7 + 1


def display_week(d: date, start: date) -> int:
    return max(1, min(config.TOTAL_WEEKS, week_of(d, start)))


def milestone_due(start: date, end_week: int) -> date:
    return start + timedelta(days=end_week * 7 - 1)


def week_start(start: date, week: int) -> date:
    return start + timedelta(days=(week - 1) * 7)


def seed_milestones(conn, start: date | None):
    if conn.execute("SELECT COUNT(*) FROM milestones").fetchone()[0]:
        return
    with conn:
        for code, title, sw, ew, marks, notes in MILESTONE_SEED:
            due = milestone_due(start, ew).isoformat() if start else None
            conn.execute(
                "INSERT INTO milestones (code, title, start_week, end_week, due_date, marks_weight, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (code, title, sw, ew, due, marks, notes))


def recompute_due_dates(conn, start: date):
    """Recompute every milestone date except the ones the owner overrode."""
    with conn:
        for row in conn.execute("SELECT id, end_week FROM milestones WHERE date_overridden = 0").fetchall():
            conn.execute("UPDATE milestones SET due_date = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                         (milestone_due(start, row["end_week"]).isoformat(), row["id"]))


def phase_for_week(milestones, week: int):
    """The milestone whose week range contains `week`; ties go to the later one."""
    candidates = [m for m in milestones
                  if m["code"] not in CONTINUOUS and m["start_week"] <= week <= m["end_week"]]
    if not candidates:
        return None
    return max(candidates, key=lambda m: (m["start_week"], m["end_week"]))


def phase_label(milestones, week: int) -> str:
    m = phase_for_week(milestones, week)
    if m:
        return m["title"]
    upcoming = sorted((x for x in milestones if x["code"] not in CONTINUOUS and x["start_week"] > week),
                      key=lambda x: x["start_week"])
    return f"Lead-up to: {upcoming[0]['title']}" if upcoming else "Project complete"


def next_deadline(milestones, tasks, today: date):
    """Earliest milestone or task due on/after today and not done.

    Returns dict(kind, id, title, due_date, days) or None.
    """
    items = []
    for m in milestones:
        if m["due_date"] and m["status"] != "done" and m["due_date"] >= today.isoformat():
            items.append(("milestone", m["id"], m["title"], m["due_date"]))
    for t in tasks:
        if t["due_date"] and t["status"] != "done" and t["due_date"] >= today.isoformat():
            items.append(("task", t["id"], t["title"], t["due_date"]))
    if not items:
        return None
    # Milestones win ties on the same day.
    kind, id_, title, due = min(items, key=lambda i: (i[3], i[0] != "milestone"))
    return {"kind": kind, "id": id_, "title": title, "due_date": due,
            "days": (date.fromisoformat(due) - today).days}


def timeline_rows(milestones, start: date, today: date):
    """Rows for the 34-week CSS-grid timeline bar."""
    rows = []
    for m in sorted(milestones, key=lambda x: (x["start_week"], x["end_week"])):
        rows.append({
            "code": m["code"], "title": m["title"], "status": m["status"],
            "start": m["start_week"], "end": m["end_week"],
            "span": m["end_week"] - m["start_week"] + 1,
            "due_date": m["due_date"], "marks": m["marks_weight"],
        })
    raw = week_of(today, start)
    return {"rows": rows, "today_week": raw if 1 <= raw <= config.TOTAL_WEEKS else None,
            "weeks": config.TOTAL_WEEKS}

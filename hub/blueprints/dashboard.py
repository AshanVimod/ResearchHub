"""Module A: dashboard and calendar."""
from datetime import date, timedelta

from flask import Blueprint, render_template

from hub import util
from hub.db import get_db
from hub.services import backup, diary, tasks as task_svc, timeline, timer
from hub.services import settings as st

bp = Blueprint("dashboard", __name__)


def _alerts(conn, s, today, milestones, open_tasks, now):
    out = diary.alerts(today, conn.execute("SELECT meeting_date, next_meeting_date, signed, semester FROM diary_entries").fetchall(), s)
    overdue = [t for t in open_tasks if task_svc.is_overdue(t, today)]
    if overdue:
        out.append({"level": "danger", "text": f"{len(overdue)} overdue task{'s' if len(overdue) != 1 else ''}.", "href": "/tasks?due=overdue"})
    soon = (today + timedelta(days=14)).isoformat()
    for m in milestones:
        if m["status"] != "done" and m["due_date"] and today.isoformat() <= m["due_date"] <= soon and m["code"] != "DIARY":
            days = (date.fromisoformat(m["due_date"]) - today).days
            out.append({"level": "warning", "text": f"{m['title']} due in {days} day{'s' if days != 1 else ''} ({util.nice_date(m['due_date'])}).",
                        "href": "/calendar"})
    age = backup.age_days(conn, now)
    if age is None or age >= 7:
        out.append({"level": "warning", "text": "No backup in the last 7 days." if age is not None else "No backup made yet.",
                    "href": "/settings#backup", "action": "backup"})
    order = {"danger": 0, "warning": 1}
    return sorted(out, key=lambda a: order[a["level"]])


@bp.get("/")
def index():
    conn = get_db()
    s = st.get_all(conn)
    now, today = util.now(), util.today()
    start = st.as_date(s, "project_start_date")
    milestones = conn.execute("SELECT * FROM milestones ORDER BY start_week, end_week").fetchall()
    open_tasks = conn.execute("SELECT * FROM tasks WHERE status != 'done'").fetchall()

    week = timeline.display_week(today, start)
    raw_week = timeline.week_of(today, start)
    nxt = timeline.next_deadline(milestones, open_tasks, today)

    sem_ranges = diary.semester_ranges(s)
    sem = diary.current_semester(today, sem_ranges) or (diary.semester_for(today, sem_ranges)[0] if sem_ranges else None)
    entries = conn.execute("SELECT * FROM diary_entries ORDER BY meeting_date DESC").fetchall()
    last_meeting = next((e for e in entries if e["meeting_date"] <= today.isoformat()), None)
    next_meeting = min((e["next_meeting_date"] for e in entries if e["next_meeting_date"] and e["next_meeting_date"] >= today.isoformat()), default=None)

    today_tasks = conn.execute(
        "SELECT t.*, m.title AS milestone_title FROM tasks t LEFT JOIN milestones m ON m.id = t.milestone_id "
        "WHERE t.status != 'done' AND (t.status = 'doing' OR (t.due_date IS NOT NULL AND t.due_date <= ?)) "
        "ORDER BY CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END, t.due_date, t.priority LIMIT 12",
        (today.isoformat(),)).fetchall()

    summary = timer.summary(conn, today, start, st.as_int(s, "hours_target"))
    return render_template(
        "dashboard/index.html",
        week=week, raw_week=raw_week, phase=timeline.phase_label(milestones, raw_week),
        next_deadline=nxt, alerts=_alerts(conn, s, today, milestones, open_tasks, now),
        tl=timeline.timeline_rows(milestones, start, today),
        summary=summary, chart=timer.chart_data(summary),
        semester=sem, diary_counts=diary.counts(entries, sem) if sem else None,
        required=st.as_int(s, "signed_meetings_per_semester"),
        last_meeting=last_meeting, next_meeting=next_meeting,
        today_tasks=today_tasks, milestones=milestones,
        inbox_count=conn.execute("SELECT COUNT(*) FROM inbox WHERE processed = 0").fetchone()[0],
    )


@bp.get("/calendar")
def calendar():
    return render_template("dashboard/calendar.html")

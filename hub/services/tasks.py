"""Task rules: kanban moves, completion stamps, overdue."""
from datetime import date, datetime

STATUSES = ["todo", "doing", "done"]
FIELDS = ["title", "description", "priority", "due_date", "milestone_id", "chapter_id"]


def is_overdue(task, today: date) -> bool:
    return bool(task["due_date"]) and task["status"] != "done" and task["due_date"] < today.isoformat()


def _renumber(conn, status: str, moved_id: int | None = None, position: int | None = None):
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM tasks WHERE status = ? ORDER BY position, id", (status,))]
    if moved_id is not None:
        ids = [i for i in ids if i != moved_id]
        pos = len(ids) if position is None else max(0, min(position, len(ids)))
        ids.insert(pos, moved_id)
    conn.executemany("UPDATE tasks SET position = ? WHERE id = ?", [(i, tid) for i, tid in enumerate(ids)])


def move(conn, task_id: int, now: datetime, status=None, position=None, due_date=...):
    """Change status/position/due date in one transaction, renumbering both columns."""
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise KeyError(task_id)
    old_status = row["status"]
    new_status = status or old_status
    if new_status not in STATUSES:
        raise ValueError(f"Unknown status: {new_status}")
    with conn:
        sets, args = ["status = ?", "updated_at = datetime('now','localtime')"], [new_status]
        if new_status == "done" and old_status != "done":
            sets.append("completed_at = ?")
            args.append(now.isoformat(timespec="seconds"))
        elif new_status != "done":
            sets.append("completed_at = NULL")
        if due_date is not ...:
            sets.append("due_date = ?")
            args.append(due_date or None)
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", args + [task_id])
        if position is not None or new_status != old_status:
            _renumber(conn, new_status, task_id, position)
            if new_status != old_status:
                _renumber(conn, old_status)


def save(conn, data: dict, now: datetime, task_id: int | None = None, status: str | None = None) -> int:
    values = [data.get(f) or None for f in FIELDS]
    with conn:
        if task_id is None:
            status = status if status in STATUSES else "todo"
            pos = conn.execute("SELECT COALESCE(MAX(position) + 1, 0) FROM tasks WHERE status = ?", (status,)).fetchone()[0]
            cur = conn.execute(
                f"INSERT INTO tasks ({', '.join(FIELDS)}, status, position, completed_at) VALUES ({', '.join('?' * (len(FIELDS) + 3))})",
                values + [status, pos, now.isoformat(timespec="seconds") if status == "done" else None])
            return cur.lastrowid
        conn.execute(f"UPDATE tasks SET {', '.join(f + ' = ?' for f in FIELDS)}, "
                     "updated_at = datetime('now','localtime') WHERE id = ?", values + [task_id])
    if status and status in STATUSES:
        move(conn, task_id, now, status=status)
    return task_id


def delete(conn, task_id: int):
    with conn:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        conn.execute("DELETE FROM taggings WHERE item_type = 'task' AND item_id = ?", (task_id,))
        conn.execute("DELETE FROM links WHERE (from_type = 'task' AND from_id = ?) OR (to_type = 'task' AND to_id = ?)",
                     (task_id, task_id))
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if row:
            _renumber(conn, row["status"])


def set_tags(conn, task_id: int, names: list[str]):
    with conn:
        conn.execute("DELETE FROM taggings WHERE item_type = 'task' AND item_id = ?", (task_id,))
        for name in {n.strip().lower() for n in names if n.strip()}:
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
            tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO taggings (tag_id, item_type, item_id) VALUES (?, 'task', ?)",
                         (tag_id, task_id))


def tags_by_task(conn) -> dict:
    out = {}
    for r in conn.execute("SELECT tg.item_id, t.name FROM taggings tg JOIN tags t ON t.id = tg.tag_id "
                          "WHERE tg.item_type = 'task' ORDER BY t.name"):
        out.setdefault(r["item_id"], []).append(r["name"])
    return out

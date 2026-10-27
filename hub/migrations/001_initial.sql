-- 001_initial.sql (Phase 1) ------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);

CREATE TABLE milestones (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    title TEXT NOT NULL,
    start_week INTEGER, end_week INTEGER,
    due_date TEXT,
    date_overridden INTEGER DEFAULT 0,
    marks_weight REAL,
    status TEXT DEFAULT 'upcoming' CHECK (status IN ('upcoming','in_progress','done')),
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);

CREATE TABLE diary_entries (
    id INTEGER PRIMARY KEY,
    meeting_date TEXT NOT NULL,
    mode TEXT CHECK (mode IN ('in_person','online','email')),
    attendees TEXT,
    agenda TEXT,
    discussion TEXT,
    decisions TEXT,
    supervisor_feedback TEXT,
    reflection TEXT,
    next_meeting_date TEXT,
    signed INTEGER DEFAULT 0,
    signed_date TEXT,
    semester INTEGER,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'todo' CHECK (status IN ('todo','doing','done')),
    priority INTEGER DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
    due_date TEXT,
    milestone_id INTEGER REFERENCES milestones(id) ON DELETE SET NULL,
    chapter_id INTEGER,
    diary_entry_id INTEGER REFERENCES diary_entries(id) ON DELETE SET NULL,
    position INTEGER DEFAULT 0,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);
CREATE INDEX tasks_status ON tasks(status, position);
CREATE INDEX tasks_due ON tasks(due_date);

CREATE TABLE time_entries (
    id INTEGER PRIMARY KEY,
    category TEXT NOT NULL CHECK (category IN
        ('reading','coding','data','writing','meeting','experiments','presentation','admin')),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    minutes INTEGER,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);
CREATE UNIQUE INDEX one_running_timer ON time_entries(ended_at IS NULL)
    WHERE ended_at IS NULL;
CREATE INDEX time_started ON time_entries(started_at);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    color TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);

CREATE TABLE links (
    id INTEGER PRIMARY KEY,
    from_type TEXT NOT NULL, from_id INTEGER NOT NULL,
    to_type TEXT NOT NULL, to_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT,
    UNIQUE (from_type, from_id, to_type, to_id)
);

CREATE TABLE taggings (
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL, item_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT,
    PRIMARY KEY (tag_id, item_type, item_id)
);

CREATE TABLE inbox (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);

CREATE TABLE backups (
    id INTEGER PRIMARY KEY,
    path TEXT,
    size_bytes INTEGER,
    made_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);

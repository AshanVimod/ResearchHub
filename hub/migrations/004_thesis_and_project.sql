-- 004_thesis_and_project.sql (Phase 3) -------------------------------------
CREATE TABLE chapters (
    id INTEGER PRIMARY KEY, ordinal INTEGER, title TEXT,
    heading_match TEXT,             -- Heading 1 text that starts the chapter; alternatives separated by |
    target_words INTEGER, current_words INTEGER, last_counted_at TEXT,
    status TEXT DEFAULT 'not_started' CHECK (status IN
        ('not_started','drafting','with_supervisor','revising','final')),
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
);

CREATE TABLE chapter_comments (
    id INTEGER PRIMARY KEY,
    chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    comment TEXT, source TEXT, resolved INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
);

CREATE TABLE checklist_items (
    id INTEGER PRIMARY KEY, list_code TEXT, ordinal INTEGER,
    text TEXT, done INTEGER DEFAULT 0, done_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
);

-- Word-count history, one row per recount (progress-over-time chart).
CREATE TABLE thesis_counts (
    id INTEGER PRIMARY KEY, counted_at TEXT, file_mtime REAL,
    main_words INTEGER, abstract_words INTEGER, per_chapter_json TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
);

-- tasks.chapter_id exists since 001; SQLite cannot add a foreign key to an existing column,
-- so ON DELETE SET NULL is enforced with a trigger.
CREATE TRIGGER chapters_ad AFTER DELETE ON chapters BEGIN
    UPDATE tasks SET chapter_id = NULL WHERE chapter_id = old.id;
END;
CREATE INDEX tasks_chapter ON tasks(chapter_id);

CREATE TABLE dataset_labels (
    id INTEGER PRIMARY KEY,
    entity TEXT NOT NULL, entity_code TEXT, entity_group TEXT,
    period TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('PRIMARY','PUBLISHED','EXPERT','RULE','SURVEY','OTHER')),
    event_date TEXT, evidence_url TEXT, evidence_file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
    label INTEGER NOT NULL CHECK (label IN (0,1)),
    evidence_strength TEXT,
    doubtful INTEGER DEFAULT 0, reviewed_with_supervisor INTEGER DEFAULT 0,
    rule_version TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT,
    UNIQUE (entity, period, source)
);

-- Versioned labelling rules (markdown); each label row records the version it used.
CREATE TABLE label_rules (
    id INTEGER PRIMARY KEY, version TEXT UNIQUE NOT NULL, text TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
);

CREATE TABLE experiments (
    id INTEGER PRIMARY KEY, run_name TEXT, run_at TEXT,
    approach TEXT CHECK (approach IN ('baseline','proposed','ablation','tuning','transfer','other')),
    model TEXT, data_version TEXT, split_desc TEXT,
    params_json TEXT, metrics_json TEXT,
    notebook_path TEXT, git_commit TEXT, notes TEXT, starred INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
);

CREATE TABLE viva_questions (
    id INTEGER PRIMARY KEY, question TEXT, answer TEXT, category TEXT,
    confidence INTEGER CHECK (confidence BETWEEN 1 AND 3),
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
);

CREATE TABLE practice_runs (
    id INTEGER PRIMARY KEY, run_at TEXT, talk_seconds INTEGER, notes TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
);

-- Search triggers for the new record types.
CREATE TRIGGER labels_ai AFTER INSERT ON dataset_labels BEGIN
    INSERT INTO search_index (title, body, item_type, item_id)
    VALUES (new.entity || ' ' || new.period,
            ifnull(new.entity_code, '') || ' ' || ifnull(new.entity_group, '') || ' ' || new.source || ' ' ||
            ifnull(new.evidence_strength, '') || ' ' || ifnull(new.notes, ''), 'label', new.id);
END;
CREATE TRIGGER labels_au AFTER UPDATE ON dataset_labels BEGIN
    DELETE FROM search_index WHERE item_type = 'label' AND item_id = old.id;
    INSERT INTO search_index (title, body, item_type, item_id)
    VALUES (new.entity || ' ' || new.period,
            ifnull(new.entity_code, '') || ' ' || ifnull(new.entity_group, '') || ' ' || new.source || ' ' ||
            ifnull(new.evidence_strength, '') || ' ' || ifnull(new.notes, ''), 'label', new.id);
END;
CREATE TRIGGER labels_ad AFTER DELETE ON dataset_labels BEGIN
    DELETE FROM search_index WHERE item_type = 'label' AND item_id = old.id;
END;

CREATE TRIGGER experiments_ai AFTER INSERT ON experiments BEGIN
    INSERT INTO search_index (title, body, item_type, item_id)
    VALUES (ifnull(new.run_name, 'Run'), ifnull(new.model, '') || ' ' || ifnull(new.approach, '') || ' ' ||
            ifnull(new.data_version, '') || ' ' || ifnull(new.split_desc, '') || ' ' || ifnull(new.notes, '') || ' ' ||
            ifnull(new.notebook_path, ''), 'experiment', new.id);
END;
CREATE TRIGGER experiments_au AFTER UPDATE OF run_name, model, approach, data_version, split_desc, notes, notebook_path ON experiments BEGIN
    DELETE FROM search_index WHERE item_type = 'experiment' AND item_id = old.id;
    INSERT INTO search_index (title, body, item_type, item_id)
    VALUES (ifnull(new.run_name, 'Run'), ifnull(new.model, '') || ' ' || ifnull(new.approach, '') || ' ' ||
            ifnull(new.data_version, '') || ' ' || ifnull(new.split_desc, '') || ' ' || ifnull(new.notes, '') || ' ' ||
            ifnull(new.notebook_path, ''), 'experiment', new.id);
END;
CREATE TRIGGER experiments_ad AFTER DELETE ON experiments BEGIN
    DELETE FROM search_index WHERE item_type = 'experiment' AND item_id = old.id;
END;

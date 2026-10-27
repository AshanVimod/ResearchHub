-- 002_references.sql (Phase 2) ---------------------------------------------
CREATE TABLE refs (
    id INTEGER PRIMARY KEY,
    ref_type TEXT NOT NULL CHECK (ref_type IN
        ('journal','conference','preprint','book','chapter','thesis','report','website','dataset','software')),
    title TEXT NOT NULL,
    authors_json TEXT NOT NULL DEFAULT '[]',
    year INTEGER, month INTEGER,
    container TEXT,
    volume TEXT, issue TEXT, pages TEXT, article_no TEXT,
    publisher TEXT, location TEXT,
    doi TEXT, url TEXT, arxiv_id TEXT,
    accessed_date TEXT,
    abstract TEXT,
    pdf_path TEXT,
    status TEXT DEFAULT 'to_read' CHECK (status IN ('to_read','reading','read','cited','excluded')),
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    chapter_ids TEXT,
    notes TEXT,
    lm_country TEXT, lm_dataset TEXT, lm_sample TEXT, lm_label_source TEXT,
    lm_method TEXT, lm_metrics TEXT, lm_key_result TEXT, lm_limitations TEXT,
    lm_relevance TEXT,
    cite_key TEXT UNIQUE,
    ieee_number INTEGER,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);
CREATE UNIQUE INDEX refs_doi ON refs(lower(doi)) WHERE doi IS NOT NULL AND doi <> '';

CREATE TABLE highlights (
    id INTEGER PRIMARY KEY,
    ref_id INTEGER REFERENCES refs(id) ON DELETE CASCADE,
    page INTEGER, quote TEXT, comment TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);

CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    root TEXT NOT NULL, rel_path TEXT NOT NULL,
    name TEXT, ext TEXT, size_bytes INTEGER, mtime REAL,
    sha256 TEXT, page_count INTEGER,
    text_status TEXT DEFAULT 'pending' CHECK (text_status IN
        ('pending','ok','skipped','error','missing')),
    error TEXT, indexed_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT,
    UNIQUE (root, rel_path)
);
CREATE INDEX files_sha ON files(sha256);

CREATE TABLE index_jobs (
    id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT,
    scanned INTEGER DEFAULT 0, added INTEGER DEFAULT 0, updated INTEGER DEFAULT 0,
    removed INTEGER DEFAULT 0, errors INTEGER DEFAULT 0, state TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);

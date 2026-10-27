-- 005_semantic.sql (Phase 4, used only when semantic_search_enabled = true) --------
-- Page text split into ~500-word chunks, embedded with all-MiniLM-L6-v2 (normalised float32 blobs).
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    page INTEGER,
    chunk_no INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL,
    vector BLOB NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT
);
CREATE INDEX chunks_file ON chunks(file_id);

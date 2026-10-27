-- 003_search.sql (Phase 3) -------------------------------------------------
-- One row per searchable unit: a PDF page, a docx/xlsx/text file, a reference, a diary entry...
CREATE VIRTUAL TABLE search_index USING fts5(
    title, body,
    item_type UNINDEXED,  -- 'file_page','ref','diary','task','inbox','experiment','label'
    item_id UNINDEXED,
    page UNINDEXED,
    tokenize = 'porter unicode61 remove_diacritics 2'
);

-- Records keep themselves in the index (search.upsert/delete is used for file pages).
CREATE TRIGGER refs_ai AFTER INSERT ON refs BEGIN
    INSERT INTO search_index (title, body, item_type, item_id)
    VALUES (new.title, (ifnull(new.cite_key, '') || ' ' || ifnull(new.authors_json, '') || ' ' || ifnull(new.container, '') || ' ' || ifnull(new.abstract, '') || ' ' || ifnull(new.notes, '') || ' ' || ifnull(new.lm_country, '') || ' ' || ifnull(new.lm_dataset, '') || ' ' || ifnull(new.lm_sample, '') || ' ' || ifnull(new.lm_label_source, '') || ' ' || ifnull(new.lm_method, '') || ' ' || ifnull(new.lm_metrics, '') || ' ' || ifnull(new.lm_key_result, '') || ' ' || ifnull(new.lm_limitations, '') || ' ' || ifnull(new.lm_relevance, '')), 'ref', new.id);
END;
CREATE TRIGGER refs_au AFTER UPDATE ON refs BEGIN
    DELETE FROM search_index WHERE item_type = 'ref' AND item_id = old.id;
    INSERT INTO search_index (title, body, item_type, item_id)
    VALUES (new.title, (ifnull(new.cite_key, '') || ' ' || ifnull(new.authors_json, '') || ' ' || ifnull(new.container, '') || ' ' || ifnull(new.abstract, '') || ' ' || ifnull(new.notes, '') || ' ' || ifnull(new.lm_country, '') || ' ' || ifnull(new.lm_dataset, '') || ' ' || ifnull(new.lm_sample, '') || ' ' || ifnull(new.lm_label_source, '') || ' ' || ifnull(new.lm_method, '') || ' ' || ifnull(new.lm_metrics, '') || ' ' || ifnull(new.lm_key_result, '') || ' ' || ifnull(new.lm_limitations, '') || ' ' || ifnull(new.lm_relevance, '')), 'ref', new.id);
END;
CREATE TRIGGER refs_ad AFTER DELETE ON refs BEGIN
    DELETE FROM search_index WHERE item_type = 'ref' AND item_id = old.id;
END;

CREATE TRIGGER diary_ai AFTER INSERT ON diary_entries BEGIN
    INSERT INTO search_index (title, body, item_type, item_id)
    VALUES ('Meeting ' || new.meeting_date, (ifnull(new.attendees, '') || ' ' || ifnull(new.agenda, '') || ' ' || ifnull(new.discussion, '') || ' ' || ifnull(new.decisions, '') || ' ' || ifnull(new.supervisor_feedback, '') || ' ' || ifnull(new.reflection, '')), 'diary', new.id);
END;
CREATE TRIGGER diary_au AFTER UPDATE ON diary_entries BEGIN
    DELETE FROM search_index WHERE item_type = 'diary' AND item_id = old.id;
    INSERT INTO search_index (title, body, item_type, item_id)
    VALUES ('Meeting ' || new.meeting_date, (ifnull(new.attendees, '') || ' ' || ifnull(new.agenda, '') || ' ' || ifnull(new.discussion, '') || ' ' || ifnull(new.decisions, '') || ' ' || ifnull(new.supervisor_feedback, '') || ' ' || ifnull(new.reflection, '')), 'diary', new.id);
END;
CREATE TRIGGER diary_ad AFTER DELETE ON diary_entries BEGIN
    DELETE FROM search_index WHERE item_type = 'diary' AND item_id = old.id;
END;

CREATE TRIGGER tasks_ai AFTER INSERT ON tasks BEGIN
    INSERT INTO search_index (title, body, item_type, item_id) VALUES (new.title, coalesce(new.description, ''), 'task', new.id);
END;
CREATE TRIGGER tasks_au AFTER UPDATE OF title, description ON tasks BEGIN
    DELETE FROM search_index WHERE item_type = 'task' AND item_id = old.id;
    INSERT INTO search_index (title, body, item_type, item_id) VALUES (new.title, coalesce(new.description, ''), 'task', new.id);
END;
CREATE TRIGGER tasks_ad AFTER DELETE ON tasks BEGIN
    DELETE FROM search_index WHERE item_type = 'task' AND item_id = old.id;
END;

CREATE TRIGGER inbox_ai AFTER INSERT ON inbox BEGIN
    INSERT INTO search_index (title, body, item_type, item_id) VALUES ('Idea', new.text, 'inbox', new.id);
END;
CREATE TRIGGER inbox_au AFTER UPDATE OF text ON inbox BEGIN
    DELETE FROM search_index WHERE item_type = 'inbox' AND item_id = old.id;
    INSERT INTO search_index (title, body, item_type, item_id) VALUES ('Idea', new.text, 'inbox', new.id);
END;
CREATE TRIGGER inbox_ad AFTER DELETE ON inbox BEGIN
    DELETE FROM search_index WHERE item_type = 'inbox' AND item_id = old.id;
END;

CREATE TRIGGER files_ad AFTER DELETE ON files BEGIN
    DELETE FROM search_index WHERE item_type = 'file_page' AND item_id = old.id;
END;

-- Back-fill records created before this migration.
INSERT INTO search_index (title, body, item_type, item_id)
    SELECT title, (ifnull(cite_key, '') || ' ' || ifnull(authors_json, '') || ' ' || ifnull(container, '') || ' ' || ifnull(abstract, '') || ' ' || ifnull(notes, '') || ' ' || ifnull(lm_country, '') || ' ' || ifnull(lm_dataset, '') || ' ' || ifnull(lm_sample, '') || ' ' || ifnull(lm_label_source, '') || ' ' || ifnull(lm_method, '') || ' ' || ifnull(lm_metrics, '') || ' ' || ifnull(lm_key_result, '') || ' ' || ifnull(lm_limitations, '') || ' ' || ifnull(lm_relevance, '')), 'ref', id FROM refs;
INSERT INTO search_index (title, body, item_type, item_id)
    SELECT 'Meeting ' || meeting_date, (ifnull(attendees, '') || ' ' || ifnull(agenda, '') || ' ' || ifnull(discussion, '') || ' ' || ifnull(decisions, '') || ' ' || ifnull(supervisor_feedback, '') || ' ' || ifnull(reflection, '')),
           'diary', id FROM diary_entries;
INSERT INTO search_index (title, body, item_type, item_id) SELECT title, coalesce(description, ''), 'task', id FROM tasks;
INSERT INTO search_index (title, body, item_type, item_id) SELECT 'Idea', text, 'inbox', id FROM inbox;
-- Files indexed before search existed get their text extracted on the next scan.
UPDATE files SET text_status = 'pending' WHERE text_status IN ('pending', 'ok');

CREATE TABLE saved_searches (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, query TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT
);

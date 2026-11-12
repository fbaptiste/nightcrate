-- v0.50.0 — retain files a scan could list but could not catalog.
-- depends: 0071.thumbnail_checklist

CREATE TABLE uncataloged_file (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    path        TEXT    NOT NULL,
    reason      TEXT    NOT NULL
                CHECK (reason IN ('damaged', 'unsupported', 'unreadable')),
    message     TEXT    NOT NULL,
    run_id      INTEGER REFERENCES ingestion_run(id) ON DELETE SET NULL,
    detected_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (project_id, path)
);

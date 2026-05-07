-- depends: 0027.plan_filter_settings

CREATE TABLE IF NOT EXISTS phd2_recent_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    opened_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_phd2_recent_files_opened ON phd2_recent_files(opened_at DESC);

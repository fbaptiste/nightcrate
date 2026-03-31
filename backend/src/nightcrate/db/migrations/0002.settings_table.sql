-- depends: 0001.initial

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- single row only
    data TEXT NOT NULL DEFAULT '{}'          -- JSON-serialized Settings
);

INSERT OR IGNORE INTO settings (id, data) VALUES (1, '{}');

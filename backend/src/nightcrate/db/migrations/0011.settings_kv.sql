-- depends: 0010.rig_summary_telescope_id
--
-- Reshape `settings` from a singleton JSON-blob row into a proper key-value
-- table. Each preference is now one row keyed by its name, so the DB is
-- directly browsable (no more "one big JSON column with id=1").
--
-- Migration steps:
--   1. Build `settings_new(key, value_json, updated_at)`.
--   2. Split the old singleton row's JSON object into one row per key,
--      serialising each value back into proper JSON text (string → quoted,
--      number/bool/null → literal, array/object → raw JSON from json_each).
--   3. Swap the tables.

CREATE TABLE settings_new (
    key TEXT PRIMARY KEY NOT NULL,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO settings_new (key, value_json)
SELECT
    je.key,
    CASE je.type
        WHEN 'text'    THEN json_quote(je.value)
        WHEN 'integer' THEN CAST(je.value AS TEXT)
        WHEN 'real'    THEN CAST(je.value AS TEXT)
        WHEN 'true'    THEN 'true'
        WHEN 'false'   THEN 'false'
        WHEN 'null'    THEN 'null'
        ELSE je.value  -- 'array' and 'object' are returned as JSON text already
    END AS value_json
FROM settings, json_each(settings.data) je
WHERE settings.id = 1;

DROP TABLE settings;
ALTER TABLE settings_new RENAME TO settings;

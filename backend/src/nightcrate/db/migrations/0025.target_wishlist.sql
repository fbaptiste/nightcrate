-- Target wishlist & planning (v0.30.0)
-- depends: 0024.mount_worm_period

-- Lightweight bookmark: "I'm interested in this DSO."
CREATE TABLE IF NOT EXISTS favorite_target (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id     INTEGER NOT NULL UNIQUE REFERENCES dso(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_favorite_target_dso
    ON favorite_target(dso_id);

-- Assignment: a favorite planned for a specific location+horizon+rig combo.
CREATE TABLE IF NOT EXISTS target_plan (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dso_id      INTEGER NOT NULL REFERENCES favorite_target(dso_id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES location(id)          ON DELETE CASCADE,
    horizon_id  INTEGER NOT NULL REFERENCES location_horizon(id)  ON DELETE CASCADE,
    rig_id      INTEGER NOT NULL REFERENCES rig(id)               ON DELETE CASCADE,
    moon_sep_deg INTEGER NOT NULL DEFAULT 0,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dso_id, location_id, horizon_id, rig_id)
);

CREATE INDEX IF NOT EXISTS idx_target_plan_dso
    ON target_plan(dso_id);

CREATE INDEX IF NOT EXISTS idx_target_plan_location_rig
    ON target_plan(location_id, rig_id);

CREATE TRIGGER IF NOT EXISTS trg_target_plan_updated_at
AFTER UPDATE ON target_plan
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE target_plan SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Date ranges for a plan (multiple per plan, no overlaps enforced at app layer).
CREATE TABLE IF NOT EXISTS target_plan_date_range (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id    INTEGER NOT NULL REFERENCES target_plan(id) ON DELETE CASCADE,
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    CHECK (start_date <= end_date)
);

CREATE INDEX IF NOT EXISTS idx_target_plan_date_range_plan
    ON target_plan_date_range(plan_id);

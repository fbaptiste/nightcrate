-- v0.41.0 — purge legacy canonical-line-name rows from the unresolved queue.
--
-- Up through v0.40.3, resolve_filter recorded an unresolved observation for ANY
-- unmatched FILTER value, including canonical line names ("Ha", "Oiii", …) —
-- and the v0.40.x ingest never supplied a RigContext, so line-name scoping was
-- always skipped and every scan queued them. v0.41.0 stops recording them (a
-- confirmed alias is global, so "Ha -> one physical filter" is wrong for any
-- dual-rig user; rig_filter_slot scoping is the only correct resolution), but
-- the rows already written would still surface in the new Admin review queue
-- and invite exactly that mistake.
--
-- Only unresolved filter rows are removed. Rows a user already confirmed are
-- left alone: deleting them would strand the alias they point at, and that is a
-- decision for the user, not a migration.
DELETE FROM unresolved_equipment_observation
WHERE equipment_kind = 'filter'
  AND resolved_at IS NULL
  AND normalized_alias IN (
      -- Mirrors services/equipment_resolver.py:_LINE_NAME_MAP keys. That map is
      -- code-level (a closed vocabulary), so the list is restated here; keep the
      -- two in sync if a spelling is ever added.
      'ha', 'h-a', 'h alpha', 'h-alpha', 'halpha', 'hydrogen alpha', 'hydrogen-alpha',
      'hb', 'h-b', 'h beta', 'h-beta', 'hbeta', 'hydrogen beta',
      'oiii', 'o3', 'o-iii', 'o iii', 'oxygen iii', 'oxygen-iii', 'oxygeniii',
      'sii', 's2', 's-ii', 's ii', 'sulfur ii', 'sulphur ii', 'sulfur-ii',
      'l', 'lum', 'luminance', 'clear',
      'r', 'red', 'g', 'green', 'b', 'blue',
      'uvir', 'uv/ir', 'uv-ir', 'uv ir cut'
  );

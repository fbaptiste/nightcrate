-- v0.41.1 — read noise, named by gain rather than by mode.
--
-- sensor.read_noise_e held the LOW-gain figure on some rows and the HIGH-gain
-- figure on others, and nothing said which. An IMX571 reads about 3.3e in low
-- gain and about 0.7e in high gain, so reading the column as "this sensor's read
-- noise" makes the most popular imaging sensor in the catalogue look 4.7x noisier
-- than it is. Worse, full_well_capacity_ke holds the low-gain figure, so a row
-- combining the two describes a state the sensor cannot occupy: 50000/0.7 is 16.1
-- stops of dynamic range on a 16-bit part. Nothing computes that yet, which is
-- the only reason it has not surfaced as a bug.
--
-- The camera columns are renamed rather than split, and no camera value changes.
-- They keep their effective_ prefix: it marks a vendor-tuned override that wins
-- over the sensor's baseline, and dropping it would give camera and sensor a
-- column of the same name meaning two different things.
-- They become correct for four rows that are wrong today: asi1600mm_pro,
-- asi1600mc_pro, qhy163m_pro and qhy163c_pro carry lcg=3.5 / hcg=1.2 on a
-- Panasonic MN34230, which has no dual-conversion-gain mode at all. Read as "at
-- low gain" and "at high gain" — two points on one curve — they are simply true.
-- Whether a discrete mode switch exists is already carried by dual_gain and
-- hcg_threshold_gain, which keep their names.
--
-- No view references any of these columns (rig_summary selects neither), so a
-- plain RENAME COLUMN is enough — no table rebuild and no view drop/recreate.

ALTER TABLE sensor RENAME COLUMN read_noise_e TO read_noise_low_gain_e;
ALTER TABLE sensor ADD COLUMN read_noise_high_gain_e REAL;

ALTER TABLE camera RENAME COLUMN effective_read_noise_lcg_e TO effective_read_noise_low_gain_e;
ALTER TABLE camera RENAME COLUMN effective_read_noise_hcg_e TO effective_read_noise_high_gain_e;

-- No value backfill here, deliberately. Renaming a seeded field invalidates every
-- stored seed_hash in the table, and the tempting repair — write this release's CSV
-- values in directly, as 0024 did — overwrites any row the user had edited. Instead
-- seed_loader/rehash.py reconstructs each row's pre-migration hash from the values
-- below (exactly one of the two read-noise columns is populated per row, so the
-- original single value is recoverable) and re-hashes only the rows that match.
-- The loader then carries the CSV forward through its normal update path, which
-- still respects user edits.

-- Move each sensor's value into the column it actually describes.
--
-- Thirteen are established by cross-reference against the cameras that use the
-- sensor: the value matches their effective_read_noise_hcg_e exactly. Five more
-- say "HCG" in the row's own note. Two are ZWO's published ASI676 figure, which
-- engages at gain 180. The last eight have no camera in the catalogue recording
-- a read noise, and their seeded value is the part's published MINIMUM, which is
-- the high-gain end of its range — the IMX178's 1.4e is the bottom of a
-- documented 2.2-1.4e span.
--
-- Everything left in read_noise_low_gain_e is there on the same evidence running
-- the other way. IMX571, IMX455 and IMX533 match their cameras' lcg. So do the
-- IMX183, IMX128 and IMX071 rows, which are single-gain: the audit's spec
-- recommended putting every single-gain value in the high column, and the camera
-- cross-reference contradicts that for these three. The IMX174 (6.0e against a
-- published 6.6-3.4e range) and AR0130 (4.0e) values are base-gain figures.
--
-- The missing side is deliberately NOT derived from the camera rows: high-gain
-- read noise is a camera implementation detail and the cameras disagree — the
-- IMX455's four cameras span 0.86-1.50e. A blank is the honest answer.

UPDATE sensor
SET read_noise_high_gain_e = read_noise_low_gain_e,
    read_noise_low_gain_e = NULL
WHERE seed_key IN (
    'sensor.smartsens.sc2210_mono',
    'sensor.sony.imx585_mono',
    'sensor.sony.imx585_color',
    'sensor.sony.imx294_color',
    'sensor.sony.imx492_mono',
    'sensor.sony.imx461_mono',
    'sensor.sony.imx461_color',
    'sensor.sony.imx411_mono',
    'sensor.sony.imx410_color',
    'sensor.sony.imx193_color',
    'sensor.sony.imx094_color',
    'sensor.panasonic.mn34230_mono',
    'sensor.panasonic.mn34230_color',
    'sensor.sony.imx662_color',
    'sensor.sony.imx662_mono',
    'sensor.sony.imx678_color',
    'sensor.sony.imx678_mono',
    'sensor.sony.imx715_color',
    'sensor.sony.imx676_color',
    'sensor.sony.imx676_mono',
    'sensor.sony.imx178_mono',
    'sensor.sony.imx178_color',
    'sensor.sony.imx290_mono',
    'sensor.sony.imx290_color',
    'sensor.sony.imx462_color',
    'sensor.sony.imx462_mono',
    'sensor.sony.imx464_color',
    'sensor.sony.imx485_color'
);

-- 01_load.sql: raw CSVs (data/raw/, read-only) -> typed DuckDB tables.
-- No cleaning happens here; tables mirror the raw files plus a `split` column so the
-- three splits can be queried together. Paths are relative to the repo root
-- (build_dataset.py sets file_search_path).

-- Operational readouts: vehicle_id, time_step (DOUBLE, anonymized operating time, NOT
-- calendar time) and 105 anonymized features. UNION BY NAME widens any column whose type
-- was inferred differently per file (e.g. BIGINT in one, DOUBLE in another).
CREATE OR REPLACE TABLE readouts AS
SELECT 'train' AS split, *      FROM read_csv('data/raw/train_operational_readouts.csv', sample_size = -1)
UNION ALL BY NAME
SELECT 'validation' AS split, * FROM read_csv('data/raw/validation_operational_readouts.csv', sample_size = -1)
UNION ALL BY NAME
SELECT 'test' AS split, *       FROM read_csv('data/raw/test_operational_readouts.csv', sample_size = -1)
ORDER BY split, vehicle_id, time_step;

-- Vehicle specifications Spec_0..Spec_7 (anonymized categories, kept as text).
CREATE OR REPLACE TABLE specifications AS
SELECT 'train' AS split, *      FROM read_csv('data/raw/train_specifications.csv', all_varchar = true)
UNION ALL BY NAME
SELECT 'validation' AS split, * FROM read_csv('data/raw/validation_specifications.csv', all_varchar = true)
UNION ALL BY NAME
SELECT 'test' AS split, *       FROM read_csv('data/raw/test_specifications.csv', all_varchar = true);
-- all_varchar also made vehicle_id text; restore it to an integer key.
ALTER TABLE specifications ALTER vehicle_id TYPE BIGINT;

-- Training time-to-event: one row per training vehicle.
-- in_study_repair = 1 -> Component X repaired at length_of_study_time_step;
-- in_study_repair = 0 -> right-censored (no repair seen up to that time step).
CREATE OR REPLACE TABLE train_tte AS
SELECT
    CAST(vehicle_id AS BIGINT)                 AS vehicle_id,
    CAST(length_of_study_time_step AS DOUBLE)  AS length_of_study_time_step,
    CAST(in_study_repair AS INTEGER)           AS in_study_repair
FROM read_csv('data/raw/train_tte.csv');

-- Validation/test labels: urgency class of each vehicle's LAST readout only.
CREATE OR REPLACE TABLE eval_labels AS
SELECT 'validation' AS split, CAST(vehicle_id AS BIGINT) AS vehicle_id, CAST(class_label AS INTEGER) AS class_label
FROM read_csv('data/raw/validation_labels.csv')
UNION ALL
SELECT 'test', CAST(vehicle_id AS BIGINT), CAST(class_label AS INTEGER)
FROM read_csv('data/raw/test_labels.csv');

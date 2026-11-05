-- 04_model_tables.sql: modelling tables built from readout_features.
-- Kept separate from 03 so 03 depends only on `readouts` (which the look-ahead test needs).

-- Training table: EVERY training readout with its features, specs and labels. Prediction
-- points are NOT chosen here: notebook 03 picks and explains the sampling/weighting.
-- class_label is NULL for censored readouts within 48 steps of end of observation.
CREATE OR REPLACE TABLE train_features AS
SELECT
    f.*,
    s.* EXCLUDE (split, vehicle_id),
    l.in_study_repair,
    l.time_to_end,
    l.time_to_repair,
    l.class_label
FROM readout_features AS f
JOIN train_readout_labels AS l USING (vehicle_id, time_step)
JOIN specifications AS s ON s.split = f.split AND s.vehicle_id = f.vehicle_id
WHERE f.split = 'train'
ORDER BY f.vehicle_id, f.time_step;

-- Validation/test table: one row per vehicle = its LAST readout (the point the label
-- describes), with features, specs and class_label.
CREATE OR REPLACE TABLE vehicle_features AS
SELECT
    f.*,
    s.* EXCLUDE (split, vehicle_id),
    e.class_label
FROM readout_features AS f
JOIN specifications AS s ON s.split = f.split AND s.vehicle_id = f.vehicle_id
JOIN eval_labels AS e ON e.split = f.split AND e.vehicle_id = f.vehicle_id
WHERE f.split IN ('validation', 'test')
QUALIFY row_number() OVER (PARTITION BY f.split, f.vehicle_id ORDER BY f.time_step DESC) = 1
ORDER BY f.split, f.vehicle_id;

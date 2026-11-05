-- 02_labels.sql: time to repair and urgency class for every training readout.
--
-- Definitions (CLAUDE.md):
--   time_to_end    = length_of_study_time_step - time_step: steps until observation ends.
--                    Rounded to 1 decimal because time_step is a DOUBLE with 0.1-0.2
--                    resolution; without rounding, float noise (e.g. 5.99999999998) would
--                    push readouts sitting exactly on 6/12/24/48 into the wrong class.
--   time_to_repair = time_to_end for repaired vehicles, NULL for censored ones.
--   class_label    = urgency class with HALF-OPEN windows on time to repair:
--                    4: [0,6)  3: [6,12)  2: [12,24)  1: [24,48)  0: >= 48 or no repair.
--   Censored vehicles: if time_to_end >= 48, the next 48 steps were fully observed with
--   no repair -> class 0. If time_to_end < 48 a repair could still happen after
--   observation ends, so the class is unknown -> NULL (dropped from classifier training,
--   kept for survival models).

CREATE OR REPLACE TABLE train_readout_labels AS
WITH base AS (
    SELECT
        r.vehicle_id,
        r.time_step,
        t.in_study_repair,
        t.length_of_study_time_step,
        round(t.length_of_study_time_step - r.time_step, 1) AS time_to_end
    FROM readouts AS r
    JOIN train_tte AS t USING (vehicle_id)
    WHERE r.split = 'train'
)
SELECT
    vehicle_id,
    time_step,
    in_study_repair,
    length_of_study_time_step,
    time_to_end,
    CASE WHEN in_study_repair = 1 THEN time_to_end END AS time_to_repair,
    CASE
        WHEN in_study_repair = 1 THEN
            CASE
                WHEN time_to_end < 6  THEN 4
                WHEN time_to_end < 12 THEN 3
                WHEN time_to_end < 24 THEN 2
                WHEN time_to_end < 48 THEN 1
                ELSE 0
            END
        WHEN time_to_end >= 48 THEN 0
        ELSE NULL
    END::INTEGER AS class_label
FROM base
ORDER BY vehicle_id, time_step;

# Truck predictive maintenance: when to call a truck in for Component X

## Business question
For a fleet of heavy trucks that send operational readouts, which trucks should the
workshop call in for Component X, and how urgently, so the fleet's combined cost of
breakdowns and early repairs is as low as possible? How much does that save compared
with today's run-to-failure approach and with a simple fixed-age rule?

## Data
- **SCANIA Component X dataset** (Swedish National Data Service, DOI 10.5878/bnh5-ka77,
  version 3, CC BY 4.0). Real, anonymized readouts from ~33,600 Scania heavy trucks for one
  anonymized engine component. Citation and file details: data/SOURCES.md.
- Download: `python src/download_data.py` (~1.65 GB into data/raw/, SHA-256 checked).
- Rebuild: `python src/build_dataset.py` (raw CSV -> data/pdm.duckdb + data/processed/).

## Metric definitions
- **Unit of analysis = vehicle.** Train, validation and test vehicles are disjoint.
  Every split, CV fold and metric is by vehicle, never by readout row.
- **time_step** = anonymized operating time since Component X was fitted. It is NOT
  calendar time and readouts are irregular per vehicle. Never call it days or weeks in
  results; the dashboard may use "time steps" or the label "planning window".
- **Repair event**: train_tte `in_study_repair = 1` at `length_of_study_time_step`;
  `0` = right-censored (no repair seen). ~9.6% of training vehicles have a repair.
- **Urgency class** of a readout = time to repair: 0 (>48 or no repair), 1 [24,48),
  2 [12,24), 3 [6,12), 4 [0,6). Windows are half-open (state this in notebooks).
  Training readouts of censored vehicles within 48 steps of end of observation have an
  unknown class and are dropped from classifier training (kept for survival models).
- **Planner actions** (use these labels everywhere in the dashboard):
  4 = Call in now, 3 = Book within 12 steps, 2 = Book within 24 steps,
  1 = Plan within 48 steps, 0 = No action.
- **Cost** = IDA 2024 challenge matrix, COST[actual][predicted]:
  ```
  actual\pred   0    1    2    3    4
  0             0    7    8    9   10
  1           200    0    7    8    9
  2           300  200    0    7    8
  3           400  300  200    0    7
  4           500  400  300  200    0
  ```
  Costs are **relative units** set by Scania experts, not SEK. Headline results are
  **cost per 1,000 trucks** so validation and test are comparable.
  Any SEK or downtime-hours figure is an *assumption* (cost per unit, hours per breakdown),
  labelled "illustrative" and exposed as a what-if parameter, never presented as data.
- **Baselines** every model is compared against:
  (a) run-to-failure = predict class 0 for everyone;
  (b) fixed-age rule = class chosen from time_step only, thresholds fit on training survival curves.

## Project rules
- Never modify anything in data/raw/. All cleaning and feature building happen in
  src/build_dataset.py and sql/*.sql (DuckDB). Notebooks read data/pdm.duckdb or
  data/processed/ only.
- The readouts file is large (~1.1M rows x 107 cols). Use DuckDB/Parquet for heavy work;
  don't load full raw CSVs into pandas in notebooks.
- **Validation** is for every modelling and threshold choice. **Test is touched once**,
  in notebook 04, after all choices are frozen; say so in a markdown cell.
- Training rows must mimic the evaluation setup (one prediction point per vehicle, or
  weights so each vehicle counts equally) -- explain the choice before the code.
- Features may only use readouts at or before the prediction point (no look-ahead).
  Counters are mostly cumulative: use differences/rates, not just levels.
- Class probabilities must be checked for calibration before they feed the
  expected-cost decision rule.
- Every modelling choice (feature, transform, sampling, model, threshold, why) gets a
  markdown cell *before* the code that implements it, plus a sentence interpreting the result.
- Variables are anonymized (e.g. `171_0`, `397_12`). Don't invent physical meanings;
  describe them as "counter 171" or "histogram 397, bin 12".
- Commit after each step (one notebook section, one SQL file, one build change) with a
  message saying what changed and why. Rerun the notebook top to bottom before committing.
- Keep notebook outputs in git (the portfolio is read on GitHub). data/raw/ and
  data/pdm.duckdb are git-ignored (too large); small tables in data/processed/ and
  powerbi/data/ are committed.

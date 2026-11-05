# Data sources

## SCANIA Component X dataset (version 3)

- **Publisher:** Swedish National Data Service (SND), researchdata.se, dataset 2024-34
- **DOI:** https://doi.org/10.5878/bnh5-ka77 (v3; data files identical to v2, DOI 10.5878/jvb5-d390)
- **Licence:** CC BY 4.0 (attribution required, see citation below)
- **Download:** `python src/download_data.py` (no account needed, ~1.65 GB)
- **Paper:** Kharazian, Lindgren, Magnússon, Steinert & Andersson Reyna (2025).
  *SCANIA Component X dataset: a real-world multivariate time series dataset for predictive
  maintenance.* Scientific Data 12, 493. https://doi.org/10.1038/s41597-025-04802-6
  (preprint: https://arxiv.org/abs/2401.15199)

### Files

| File | Rows (approx.) | Content |
|---|---|---|
| train_operational_readouts.csv | 1,122,452 | vehicle_id, time_step, 105 features, full study period, 23,550 vehicles |
| train_specifications.csv | 23,550 | Spec_0 ... Spec_7 (anonymized categories Cat0..Cat28) |
| train_tte.csv | 23,550 | length_of_study_time_step, in_study_repair (1 = repaired, 0 = censored) |
| validation_operational_readouts.csv | 196,227 | 5,046 vehicles, truncated at a random last readout |
| validation_specifications.csv | 5,046 | as above |
| validation_labels.csv | 5,046 | class_label of the last readout |
| test_operational_readouts.csv | 198,140 | 5,045 vehicles, truncated at a random last readout |
| test_specifications.csv | 5,045 | as above |
| test_labels.csv | 5,045 | class_label of the last readout |

Class counts (0/1/2/3/4): validation 4,910 / 16 / 14 / 30 / 76; test 4,903 / 26 / 15 / 41 / 60.
Training: 2,272 repaired, 21,278 censored.

### Features
- 8 numerical counters: 171_0, 666_0, 427_0, 837_0, 309_0, 835_0, 370_0, 100_0 (mostly cumulative)
- 6 histograms, columns named `<variable>_<bin>`: 167 (10 bins), 272 (10), 291 (11),
  158 (10), 459 (20), 397 (36). Outer bins are open-ended.
- Fewer than 1% missing values per feature.

### Quirks and caveats (from the paper)
- Variable names, categories and timestamps are anonymized; time_step is relative operating time.
- Some operational data and repair rates were scaled/perturbed; readout and repair frequencies
  may not reflect real truck usage.
- Only vehicles with complete service history are included, and only repairs done in Scania's
  own network are visible.
- Validation/test labels describe only the last readout of each vehicle.

### Citation (use in README and dashboard footer)
> Data: SCANIA Component X dataset, Swedish National Data Service, https://doi.org/10.5878/bnh5-ka77, CC BY 4.0.

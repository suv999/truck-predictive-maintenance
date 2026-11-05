"""Build data/pdm.duckdb from data/raw/ by running sql/*.sql in order, then validate.

Usage:
    python src/build_dataset.py            # rebuild from scratch and run all checks
    python src/build_dataset.py --seeds 50 # more random draws in the label check

Checks (the script exits non-zero if a hard check fails):
  1. Row/vehicle counts match data/SOURCES.md.
  2. Label sanity: repaired vehicles never get a NULL class, censored ones never get 1-4,
     class is monotonic in time to repair.
  3. Class counts per split (training at readout and last-readout level, validation, test).
  4. Random-readout check: one random readout per training vehicle (fixed seeds), class
     mix compared with validation's. Written to data/processed/label_check.csv.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "pdm.duckdb"
SQL_DIR = ROOT / "sql"
PROCESSED = ROOT / "data" / "processed"

# Expected counts from data/SOURCES.md.
EXPECTED_ROWS = {
    ("readouts", "train"): 1_122_452,
    ("readouts", "validation"): 196_227,
    ("readouts", "test"): 198_140,
    ("specifications", "train"): 23_550,
    ("specifications", "validation"): 5_046,
    ("specifications", "test"): 5_045,
    ("eval_labels", "validation"): 5_046,
    ("eval_labels", "test"): 5_045,
}
EXPECTED_TTE = {"rows": 23_550, "repaired": 2_272, "censored": 21_278}
CLASSES = [0, 1, 2, 3, 4]


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def run_sql(con: duckdb.DuckDBPyConnection) -> None:
    for path in sorted(SQL_DIR.glob("[0-9][0-9]_*.sql")):
        print(f"  running {path.name}")
        con.execute(path.read_text(encoding="utf-8"))


def check_counts(con) -> list[str]:
    section("1. Row counts vs SOURCES.md")
    errors = []
    for (table, split), expected in EXPECTED_ROWS.items():
        rows, vehicles = con.execute(
            f"SELECT count(*), count(DISTINCT vehicle_id) FROM {table} WHERE split = ?", [split]
        ).fetchone()
        ok = rows == expected
        print(f"  {table:15s} {split:10s} rows={rows:>9,} vehicles={vehicles:>6,} expected={expected:>9,} {'ok' if ok else 'MISMATCH'}")
        if not ok:
            errors.append(f"{table}/{split}: {rows} rows, expected {expected}")
    rows, repaired = con.execute("SELECT count(*), sum(in_study_repair) FROM train_tte").fetchone()
    censored = rows - repaired
    ok = (rows, repaired, censored) == tuple(EXPECTED_TTE.values())
    print(f"  train_tte       rows={rows:,} repaired={repaired:,} censored={censored:,} {'ok' if ok else 'MISMATCH'}")
    if not ok:
        errors.append(f"train_tte: {rows}/{repaired}/{censored}, expected {EXPECTED_TTE}")
    n_cols = len(con.execute("DESCRIBE readouts").fetchall()) - 1  # minus split
    print(f"  readouts columns (excl. split) = {n_cols} (expected 107)")
    if n_cols != 107:
        errors.append(f"readouts has {n_cols} columns, expected 107")
    return errors


def check_labels(con) -> list[str]:
    section("2. Label sanity")
    errors = []
    checks = {
        "repaired readouts with NULL class": "SELECT count(*) FROM train_readout_labels WHERE in_study_repair = 1 AND class_label IS NULL",
        "censored readouts with class 1-4": "SELECT count(*) FROM train_readout_labels WHERE in_study_repair = 0 AND class_label > 0",
        "negative time_to_end": "SELECT count(*) FROM train_readout_labels WHERE time_to_end < 0",
        "training readouts without a tte row": "SELECT count(*) FROM readouts r ANTI JOIN train_tte t USING (vehicle_id) WHERE r.split = 'train'",
        # Within a repaired vehicle, a later readout (smaller time to repair) never has a lower class.
        "non-monotonic class within vehicle": """
            SELECT count(*) FROM (
                SELECT class_label, lag(class_label) OVER (PARTITION BY vehicle_id ORDER BY time_step) AS prev
                FROM train_readout_labels WHERE in_study_repair = 1
            ) WHERE class_label < prev""",
    }
    for label, query in checks.items():
        n = con.execute(query).fetchone()[0]
        print(f"  {label:40s} {n:>6,} {'ok' if n == 0 else 'FAIL'}")
        if n:
            errors.append(f"{label}: {n}")
    on_boundary = con.execute(
        "SELECT time_to_end, count(*) FROM train_readout_labels "
        "WHERE in_study_repair = 1 AND time_to_end IN (6, 12, 24, 48) GROUP BY 1 ORDER BY 1"
    ).fetchall()
    print(f"  repaired readouts exactly on a boundary (go to the less urgent class): {on_boundary or 'none'}")
    return errors


def class_counts(con) -> None:
    section("3. Class counts per split")
    queries = {
        "train, all readouts": "SELECT class_label, count(*) FROM train_readout_labels GROUP BY 1",
        "train, last readout per vehicle": """
            SELECT class_label, count(*) FROM (
                SELECT class_label, row_number() OVER (PARTITION BY vehicle_id ORDER BY time_step DESC) AS rn
                FROM train_readout_labels) WHERE rn = 1 GROUP BY 1""",
        "validation (last readout)": "SELECT class_label, count(*) FROM eval_labels WHERE split = 'validation' GROUP BY 1",
        "test (last readout)": "SELECT class_label, count(*) FROM eval_labels WHERE split = 'test' GROUP BY 1",
    }
    print(f"  {'':34s}" + "".join(f"{c:>10}" for c in [*CLASSES, "NULL"]) + f"{'total':>11}")
    for label, query in queries.items():
        counts = dict(con.execute(query).fetchall())
        row = [counts.get(c, 0) for c in CLASSES] + [counts.get(None, 0)]
        print(f"  {label:34s}" + "".join(f"{n:>10,}" for n in row) + f"{sum(row):>11,}")


def random_readout_check(con, n_seeds: int) -> pd.DataFrame:
    section(f"4. One random readout per training vehicle ({n_seeds} seeds) vs validation")
    draws = con.execute(
        """
        WITH seeds AS (SELECT range AS seed FROM range(?)),
        ranked AS (
            SELECT s.seed, l.class_label,
                   row_number() OVER (PARTITION BY s.seed, l.vehicle_id
                                      ORDER BY hash(concat_ws('|', l.vehicle_id, l.time_step, s.seed))) AS rn
            FROM train_readout_labels AS l CROSS JOIN seeds AS s
        )
        SELECT seed, class_label, count(*) AS n FROM ranked WHERE rn = 1 GROUP BY ALL
        """,
        [n_seeds],
    ).df()
    wide = draws.pivot_table(index="seed", columns="class_label", values="n", aggfunc="sum",
                             fill_value=0, dropna=False)
    wide.columns = ["NULL" if pd.isna(c) else int(c) for c in wide.columns]
    for c in [*CLASSES, "NULL"]:
        if c not in wide:
            wide[c] = 0
    known = wide[CLASSES]
    share_known = known.div(known.sum(axis=1), axis=0)          # NULL draws excluded
    null_share = wide["NULL"] / wide[[*CLASSES, "NULL"]].sum(axis=1)

    val = dict(con.execute("SELECT class_label, count(*) FROM eval_labels WHERE split = 'validation' GROUP BY 1").fetchall())
    val_total = sum(val.values())

    rows = []
    for c in CLASSES:
        rows.append({
            "class_label": c,
            "train_random_mean_share": share_known[c].mean(),
            "train_random_min_share": share_known[c].min(),
            "train_random_max_share": share_known[c].max(),
            "train_random_mean_count_per_5046": share_known[c].mean() * val_total,
            "validation_count": val.get(c, 0),
            "validation_share": val.get(c, 0) / val_total,
        })
    result = pd.DataFrame(rows)
    result["share_ratio_train_to_val"] = result["train_random_mean_share"] / result["validation_share"]

    print(f"  draws with an unknown (NULL) class: mean {null_share.mean():.1%} of vehicles "
          f"(range {null_share.min():.1%}-{null_share.max():.1%}); shares below exclude them")
    print(f"  {'class':>5} {'train mean':>11} {'train range':>17} {'per 5,046':>10} {'val n':>7} {'val share':>10} {'ratio':>7}")
    for r in result.itertuples():
        print(f"  {r.class_label:>5} {r.train_random_mean_share:>11.2%} "
              f"{r.train_random_min_share:>8.2%}-{r.train_random_max_share:<8.2%} "
              f"{r.train_random_mean_count_per_5046:>10.1f} {r.validation_count:>7,} "
              f"{r.validation_share:>10.2%} {r.share_ratio_train_to_val:>7.2f}")
    result.insert(0, "null_share_of_draws", null_share.mean())
    result.insert(0, "n_seeds", n_seeds)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=20, help="random draws for check 4")
    args = parser.parse_args()

    if not (ROOT / "data" / "raw" / "train_operational_readouts.csv").exists():
        print("data/raw/ is empty: run python src/download_data.py first")
        return 1

    DB_PATH.unlink(missing_ok=True)
    Path(str(DB_PATH) + ".wal").unlink(missing_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(f"SET file_search_path = '{ROOT.as_posix()}'")

    section(f"Building {DB_PATH.relative_to(ROOT)}")
    run_sql(con)

    errors = check_counts(con) + check_labels(con)
    class_counts(con)
    result = random_readout_check(con, args.seeds)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / "label_check.csv"
    result.round(6).to_csv(out, index=False)
    print(f"\n  wrote {out.relative_to(ROOT)}")
    con.close()

    if errors:
        print(f"\n{len(errors)} hard check(s) FAILED:\n  " + "\n  ".join(errors))
        return 1
    print("\nAll hard checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

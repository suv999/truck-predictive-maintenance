"""Prove that sql/03_features.sql uses no readout later than the one it describes.

Method (truncation test): build features on a sample of vehicles' full histories, then
rebuild after (a) deleting and (b) scrambling every readout after a random cut point per
vehicle. If any feature at a readout <= cut looked forward, its value would change.
Runs the real SQL file against real data copied from data/pdm.duckdb (build it first:
python src/build_dataset.py).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "pdm.duckdb"
FEATURE_SQL = ROOT / "sql" / "03_features.sql"
sys.path.insert(0, str(ROOT / "src"))
from make_features_sql import FEATURES, build  # noqa: E402

N_VEHICLES = 300
SEED = 7
KEY = ["split", "vehicle_id", "time_step"]


@pytest.fixture(scope="module")
def sample_readouts() -> pd.DataFrame:
    if not DB_PATH.exists():
        pytest.skip("data/pdm.duckdb not built; run python src/build_dataset.py")
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        # Vehicles from every split, favouring ones with long histories so cuts land mid-way.
        return con.execute(
            f"""
            WITH v AS (
                SELECT split, vehicle_id FROM readouts GROUP BY split, vehicle_id HAVING count(*) >= 8
                ORDER BY hash(split, vehicle_id, {SEED}) LIMIT {N_VEHICLES}
            )
            SELECT r.* FROM readouts r JOIN v USING (split, vehicle_id)
            """
        ).df()


def features_for(readouts: pd.DataFrame) -> pd.DataFrame:
    con = duckdb.connect()
    con.register("src_df", readouts)
    con.execute("CREATE TABLE readouts AS SELECT * FROM src_df")
    con.execute(FEATURE_SQL.read_text(encoding="utf-8"))
    out = con.execute("SELECT * FROM readout_features").df()
    con.close()
    return out.sort_values(KEY).reset_index(drop=True)


def cut_points(readouts: pd.DataFrame) -> pd.DataFrame:
    """A random cut time_step per vehicle, strictly before its last readout."""
    rng = np.random.default_rng(SEED)
    rows = []
    for (split, vid), g in readouts.groupby(["split", "vehicle_id"]):
        ts = np.sort(g["time_step"].to_numpy())
        rows.append((split, vid, ts[rng.integers(0, len(ts) - 1)]))
    return pd.DataFrame(rows, columns=["split", "vehicle_id", "cut"])


def assert_same_before_cut(full: pd.DataFrame, altered: pd.DataFrame, cuts: pd.DataFrame) -> None:
    keep = full.merge(cuts, on=["split", "vehicle_id"])
    keep = keep[keep["time_step"] <= keep["cut"]].drop(columns="cut")
    alt = altered.merge(cuts, on=["split", "vehicle_id"])
    alt = alt[alt["time_step"] <= alt["cut"]].drop(columns="cut")
    assert len(keep) > 1000 and len(keep) == len(alt)
    merged = keep.merge(alt, on=KEY, suffixes=("_full", "_alt"), validate="one_to_one")
    bad = {}
    for f in FEATURES:
        if f in KEY:
            continue
        a = merged[f"{f}_full"].to_numpy(dtype=float)
        b = merged[f"{f}_alt"].to_numpy(dtype=float)
        same = np.isclose(a, b, rtol=1e-9, atol=1e-9, equal_nan=True)
        if not same.all():
            bad[f] = int((~same).sum())
    assert not bad, f"features changed when later readouts changed: {bad}"


def test_sql_file_is_up_to_date():
    assert FEATURE_SQL.read_text(encoding="utf-8") == build(), \
        "sql/03_features.sql is stale: run python src/make_features_sql.py"


def test_no_forward_window_syntax():
    code = "\n".join(l for l in FEATURE_SQL.read_text(encoding="utf-8").splitlines()
                     if not l.lstrip().startswith("--"))
    for pattern in (r"\bFOLLOWING\b", r"\blead\s*\(", r"\blast_value\s*\(", r"\bnth_value\s*\("):
        assert not re.search(pattern, code, re.IGNORECASE), f"forward-looking construct: {pattern}"


def test_features_unchanged_when_future_deleted(sample_readouts):
    cuts = cut_points(sample_readouts)
    full = features_for(sample_readouts)
    trunc = sample_readouts.merge(cuts, on=["split", "vehicle_id"])
    trunc = trunc[trunc["time_step"] <= trunc["cut"]].drop(columns="cut")
    assert_same_before_cut(full, features_for(trunc), cuts)


def test_features_unchanged_when_future_scrambled(sample_readouts):
    cuts = cut_points(sample_readouts)
    full = features_for(sample_readouts)
    scrambled = sample_readouts.merge(cuts, on=["split", "vehicle_id"])
    future = scrambled["time_step"] > scrambled["cut"]
    rng = np.random.default_rng(SEED + 1)
    value_cols = [c for c in scrambled.columns if c not in KEY + ["cut"]]
    scrambled.loc[future, value_cols] = rng.uniform(0, 1e7, size=(future.sum(), len(value_cols)))
    assert future.sum() > 1000
    assert_same_before_cut(full, features_for(scrambled.drop(columns="cut")), cuts)


def test_test_is_sensitive_to_lookahead(sample_readouts):
    """Sanity check of the test itself: a deliberately leaky feature must be caught."""
    cuts = cut_points(sample_readouts)
    leaky_sql = FEATURE_SQL.read_text(encoding="utf-8").replace(
        "lag(time_step) OVER w AS ts_prev", "lead(time_step) OVER w AS ts_prev")
    assert leaky_sql != FEATURE_SQL.read_text(encoding="utf-8")

    def leaky(readouts):
        con = duckdb.connect()
        con.register("src_df", readouts)
        con.execute("CREATE TABLE readouts AS SELECT * FROM src_df")
        con.execute(leaky_sql)
        out = con.execute("SELECT * FROM readout_features").df().sort_values(KEY).reset_index(drop=True)
        con.close()
        return out

    trunc = sample_readouts.merge(cuts, on=["split", "vehicle_id"])
    trunc = trunc[trunc["time_step"] <= trunc["cut"]].drop(columns="cut")
    with pytest.raises(AssertionError, match="features changed"):
        assert_same_before_cut(leaky(sample_readouts), leaky(trunc), cuts)

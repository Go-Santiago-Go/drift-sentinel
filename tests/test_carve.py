"""Hermetic tests for the carve logic: run anywhere, no real data, no files.

These build a tiny synthetic dataset in memory and check the invariants the carve must uphold for
any input: the split proportion, that the holdout is the earliest slice and disjoint from the pool,
and that the carve is deterministic. This is the suite that runs in CI, where the real 144 MB dataset
does not exist. It verifies the LOGIC; the real frozen-seal check lives in test_holdout.py and only
runs where the real data is present.
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from carve_holdout import carve, content_hash


def make_synthetic(n_rows: int = 100) -> pd.DataFrame:
    """A tiny frame shaped like the real data: a Time column, a feature, and a Class label.

    Time is handed to carve in REVERSED order on purpose. If the carve failed to sort, invariant #2
    below would break, so a broken or missing sort cannot pass silently.
    """
    times = list(reversed(range(n_rows)))
    return pd.DataFrame(
        {
            "Time": times,
            "feature": range(n_rows),
            "Class": [0] * (n_rows - 5) + [1] * 5,
        }
    )


def test_split_proportion():
    df = make_synthetic(100)
    holdout, pool = carve(df, fraction=0.20)

    assert len(holdout) == 20
    assert len(pool) == 80
    # Together they account for every row, nothing lost or duplicated.
    assert len(holdout) + len(pool) == len(df)


def test_holdout_is_earliest_and_disjoint_from_pool():
    df = make_synthetic(100)
    holdout, pool = carve(df)

    # The core promise of the frozen holdout: it is the FRONT of the timeline, so its latest Time is
    # strictly before the pool's earliest Time. This is what guarantees no training row can leak in.
    assert holdout["Time"].max() < pool["Time"].min()


def test_carve_is_deterministic():
    df = make_synthetic(100)
    first, _ = carve(df)
    second, _ = carve(df)

    # Same input, same holdout, therefore same seal. Reproducibility is what the frozen hash relies on.
    assert content_hash(first) == content_hash(second)

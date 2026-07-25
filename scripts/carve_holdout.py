"""Carve the frozen holdout: the fixed early time slice every model version is scored against.

Run once from the repo root. The output is a Parquet file (gitignored) plus a small manifest
(committed). The manifest's hash is the version record: if the file is ever regenerated and the
hash changes, the ruler moved and every past metric became incomparable.

Five steps:
  1. Read the raw CSV and put it in a fixed order (stable sort by Time).
  2. Split off the earliest 20% by Time as the holdout.
  3. Write the holdout to disk as Parquet.
  4. Hash the holdout's contents and build a manifest.
  5. Write the manifest to a committed file.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd

RAW = "data/creditcard.csv"
MANIFEST = Path("holdout_manifest.json")
CUT_FRACTION = 0.20


def content_hash(frame: pd.DataFrame) -> str:
    """Fingerprint a frame's VALUES, independent of file format or library version.

    hash_pandas_object hashes each row from its values, so the result is stable across Parquet
    versions and machines. This is the single source of truth for the seal: both the carve script
    and the test call it, so they can never drift apart.
    """
    row_hashes = pd.util.hash_pandas_object(frame, index=False).values
    return hashlib.sha256(row_hashes.tobytes()).hexdigest()


def carve(df: pd.DataFrame, fraction: float = CUT_FRACTION):
    """Order by Time and split off the earliest `fraction` as the frozen holdout.

    Returns (holdout, pool). Pure on purpose: no file IO, so tests can call it on a small synthetic
    frame. Stable sort keeps rows sharing a Time in their original order, which is what makes the
    split, and therefore the hash, reproducible.
    """
    ordered = df.sort_values("Time", kind="stable").reset_index(drop=True)
    cut = int(len(ordered) * fraction)
    return ordered.iloc[:cut], ordered.iloc[cut:]


def main():
    # Step 1: read the raw data.
    df = pd.read_csv(RAW)
    print(f"loaded {len(df):,} rows")

    # Step 2: order by Time and split off the earliest 20% as the frozen holdout.
    # carve() is pure (no IO) so the test can exercise this exact logic on synthetic data. The pool
    # is the remaining 80% that training and drift-replay draw from; writing it separately means
    # downstream code physically cannot touch a holdout row.
    holdout, pool = carve(df)
    print(f"holdout: {len(holdout):,} rows, {holdout['Class'].sum()} frauds")
    print(f"pool:    {len(pool):,} rows, {pool['Class'].sum()} frauds")

    # Step 3: write both frames to disk as Parquet.
    # Parquet preserves dtypes and compresses well; index=False because the positional index
    # is not data, we can always recompute it. Both files live under data/, which is gitignored,
    # so the bytes never enter git; only the manifest (step 5) does.
    out_dir = Path("data/holdout")
    out_dir.mkdir(parents=True, exist_ok=True)
    holdout.to_parquet(out_dir / "holdout.parquet", index=False)
    pool.to_parquet(out_dir / "pool.parquet", index=False)
    print(f"wrote {out_dir}/holdout.parquet and {out_dir}/pool.parquet")

    # Step 4: hash the holdout's CONTENT, not the Parquet file bytes.
    # See content_hash() above for why we fingerprint values instead of the file. The same
    # function is called by the test, so the seal written here and the seal checked in CI are
    # computed identically by construction.
    holdout_hash = content_hash(holdout)
    print(f"holdout content hash: {holdout_hash}")

    # Step 5: write the manifest, the one artifact that gets committed to git.
    # The parquet bytes stay gitignored; this small JSON is the version record. content_hash is
    # the load-bearing field (the seal); the counts are there so a reviewer can sanity-check the
    # carve without loading the data. sort_keys + indent make the file stable and diff-friendly.
    manifest = {
        "source": RAW,
        "cut_fraction": CUT_FRACTION,
        "n_rows_total": len(df),
        "holdout": {"rows": len(holdout), "frauds": int(holdout["Class"].sum())},
        "pool": {"rows": len(pool), "frauds": int(pool["Class"].sum())},
        "hash_algorithm": "sha256(hash_pandas_object(holdout, index=False))",
        "content_hash": holdout_hash,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()

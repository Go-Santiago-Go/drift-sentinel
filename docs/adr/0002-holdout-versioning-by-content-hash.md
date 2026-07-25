# ADR 0002: Version the frozen holdout by content hash, not DVC

## Context

I need a frozen holdout: a fixed early slice of the fraud dataset that never changes and that every
model version is scored against. It is the single ruler that makes champion vs challenger comparisons
valid. If the ruler moves, every past metric becomes incomparable and the promotion gate is
meaningless.

Two properties follow from that. I have to be able to prove which bytes were used (versioning), and
any accidental change has to be caught rather than discovered later (tamper-evidence). The raw dataset
is ~144 MB, so committing the bytes to git is off the table.

The obvious managed tool for this is DVC (Data Version Control), which stores large files in remote
storage and commits a small hash pointer to git. Its core pattern, commit the fingerprint and keep the
bytes out of git, is exactly what I need.

## Decision

I am not adopting DVC. I version the holdout by a committed content hash instead.

The carve script writes the holdout to gitignored Parquet, computes a SHA-256 over a canonical
fingerprint of the row values (via `pandas.util.hash_pandas_object`, not the file bytes), and writes
that hash plus row and fraud counts to a committed `holdout_manifest.json`. A pytest test reloads the
holdout, recomputes the hash with the same shared function, and asserts it equals the manifest.

That seal test guards locally, where the data lives and where the holdout could actually change, since
regenerating it is the only way it moves. It skips in a fresh CI checkout because the gitignored data
is absent there. A separate hermetic test that synthesizes its own data covers the carve logic in CI.

I hash the values, not the Parquet file, on purpose: Parquet embeds the writer library version and
layout metadata that can change between runs without any data changing, which would raise false
alarms. Hashing the values is stable across library versions and machines.

## Consequences

Positive:

- Near-zero moving parts: a script, a JSON file, and a test. Nothing to install, no remote to
  configure, no new CLI to learn.
- The mechanism is fully legible and I can explain it in an interview: content addressing, why I hash
  the values rather than the file, why the fingerprint goes in git and the bytes do not.
- The invariant is enforced by an automated test, not by my discipline.

Negative:

- It is single-purpose. It versions exactly one fixed file. It gives me no data lineage across many
  evolving datasets, no shared remote caching for a team, and no per-commit checkout of data.
- If the project later grows multiple datasets that change over time, this hand-rolled approach would
  become tech debt and I would replace it with DVC or similar.

## Alternatives considered

- **DVC:** I rejected it as overkill for a single fixed reference file on a single-machine project. I
  would revisit it if datasets multiply, or if data ever needs to flow into CI (for training or
  integration tests), since `dvc pull` would then earn its keep.
- **Commit the Parquet directly:** rejected. It bloats the repo and still would not prove the values
  are unchanged without a hash.
- **Hash the Parquet file bytes:** rejected. File-level metadata makes the hash unstable across
  library versions, producing false "the ruler moved" alarms.

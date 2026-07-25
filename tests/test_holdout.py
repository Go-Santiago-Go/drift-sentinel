"""Enforce the frozen holdout invariant: the carved data still matches its committed seal.

This is the automated version of eyeballing two carve runs. It reloads the holdout, recomputes the
content hash with the SAME function the carve script used, and asserts it equals the hash recorded in
holdout_manifest.json. If the holdout is ever regenerated differently or altered, this test goes red.
"""

import json
import sys
from pathlib import Path

import pandas as pd

# Anchor every path to the test file, not the current directory, so the test passes no matter what
# folder pytest is launched from.
REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "holdout_manifest.json"
HOLDOUT_PATH = REPO_ROOT / "data" / "holdout" / "holdout.parquet"

# Put scripts/ on the import path so we can reuse the carve script's hash function instead of
# retyping it. One implementation means the seal written at carve time and the seal checked here can
# never drift apart. The import sits below the insert because the path must be set before it resolves,
# and it is safe because carve_holdout guards main() behind `if __name__ == "__main__"`: importing the
# module runs no carving.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from carve_holdout import content_hash


def test_holdout_hash_matches_manifest():
    # Expected value: the seal committed to git at carve time.
    manifest = json.loads(MANIFEST_PATH.read_text())
    expected_hash = manifest["content_hash"]

    # Actual value: reload the holdout from disk and hash it right now.
    holdout = pd.read_parquet(HOLDOUT_PATH)
    actual_hash = content_hash(holdout)

    # The whole invariant in one line. The message prints on failure so a red CI log explains what
    # broke and why it matters, not just "AssertionError".
    assert actual_hash == expected_hash, (
        "Holdout content hash does not match the committed manifest. "
        "The frozen ruler moved: the data was regenerated differently or altered."
    )

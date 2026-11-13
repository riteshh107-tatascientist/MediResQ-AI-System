import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mediresq import datagen  # noqa: E402
from mediresq.db import Database  # noqa: E402

AS_OF = date(2026, 11, 13)
_BASE = {}


def fresh_db():
    """New seeded DB (deterministic). Seeds once, then copies the file for speed."""
    import shutil
    if "path" not in _BASE:
        d = tempfile.mkdtemp()
        p = os.path.join(d, "base.db")
        datagen.seed_database(Database(p), AS_OF)
        _BASE["path"] = p
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t.db")
    shutil.copy(_BASE["path"], p)
    return Database(p)

"""Create + seed the SQLite DB with the synthetic dataset and CSV exports.  python scripts/init_db.py [--as-of 2026-11-13]"""
import argparse, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mediresq import config, datagen
from mediresq.db import Database

ap = argparse.ArgumentParser()
ap.add_argument("--as-of", default=config.AS_OF or str(date.today()))
a = ap.parse_args()
if config.DB_PATH.exists():
    config.DB_PATH.unlink()
db = Database(config.DB_PATH)
datagen.seed_database(db, date.fromisoformat(a.as_of), csv_dir=config.CSV_DIR)
print("Seeded", config.DB_PATH, "as_of", a.as_of)
for name, ok, det in datagen.validate_database(db):
    print(("PASS " if ok else "FAIL ") + name, det)

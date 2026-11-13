"""Central configuration. Values can be overridden with environment variables or a local .env file."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()

DATA_DIR = ROOT / "data"
CSV_DIR = DATA_DIR / "csv"
CACHE_DIR = DATA_DIR / "cache"
ASSET_DIR = ROOT / "assets"
DB_PATH = Path(os.getenv("MEDIRESQ_DB", str(DATA_DIR / "mediresq.db")))
SEED = int(os.getenv("MEDIRESQ_SEED", "42"))
DEMO_PASSWORD = os.getenv("MEDIRESQ_DEMO_PASSWORD", "MediResQ@Demo2026")  # demo accounts only, synthetic
AS_OF = os.getenv("MEDIRESQ_AS_OF", "")  # ISO date; empty = today

# Planning assumptions (documented in docs/ARCHITECTURE.md)
PLAN_HORIZON_DAYS = 14        # optimizer planning horizon
MIN_SHELF_AFTER_ARRIVAL = 14  # days of shelf life a transferred batch must still have on arrival
WH_RESERVE_DAYS = 2.0         # warehouse keeps this many days of network demand (split across warehouses)
Z_BY_CRITICALITY = {1: 1.28, 2: 1.65, 3: 2.05}  # service-level z-scores for safety stock

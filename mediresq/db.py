"""Thin database abstraction over sqlite3 (stdlib). All SQL is ANSI-style so a PostgreSQL
backend can be swapped in later by re-implementing the Database class."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS facilities(
  facility_id TEXT PRIMARY KEY, name TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN('warehouse','hospital')),
  city TEXT, lat REAL, lon REAL,
  priority INTEGER NOT NULL DEFAULT 2 CHECK(priority BETWEEN 1 AND 3),
  size_factor REAL NOT NULL DEFAULT 1.0 CHECK(size_factor>0));
CREATE TABLE IF NOT EXISTS medicines(
  medicine_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, form TEXT, category TEXT,
  unit_cost REAL CHECK(unit_cost IS NULL OR unit_cost>=0),
  criticality INTEGER NOT NULL DEFAULT 2 CHECK(criticality BETWEEN 1 AND 3),
  shelf_life_days INTEGER CHECK(shelf_life_days IS NULL OR shelf_life_days>0),
  cold_chain INTEGER NOT NULL DEFAULT 0 CHECK(cold_chain IN(0,1)));
CREATE TABLE IF NOT EXISTS stock_policy(
  facility_id TEXT NOT NULL REFERENCES facilities(facility_id),
  medicine_id TEXT NOT NULL REFERENCES medicines(medicine_id),
  min_stock REAL, max_stock REAL, safety_stock REAL, reorder_point REAL, avg_daily_consumption REAL,
  PRIMARY KEY(facility_id, medicine_id));
CREATE TABLE IF NOT EXISTS batches(
  batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
  facility_id TEXT NOT NULL REFERENCES facilities(facility_id),
  medicine_id TEXT NOT NULL REFERENCES medicines(medicine_id),
  batch_no TEXT NOT NULL, mfg_date TEXT NOT NULL, expiry_date TEXT NOT NULL,
  qty INTEGER NOT NULL CHECK(qty>=0),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN('active','quarantined')),
  unit_cost REAL CHECK(unit_cost IS NULL OR unit_cost>=0),
  UNIQUE(facility_id, medicine_id, batch_no), CHECK(expiry_date>mfg_date));
CREATE TABLE IF NOT EXISTS consumption(
  date TEXT NOT NULL, facility_id TEXT NOT NULL REFERENCES facilities(facility_id),
  medicine_id TEXT NOT NULL REFERENCES medicines(medicine_id),
  qty REAL NOT NULL CHECK(qty>=0), unmet_qty REAL NOT NULL DEFAULT 0 CHECK(unmet_qty>=0),
  PRIMARY KEY(date, facility_id, medicine_id));
CREATE TABLE IF NOT EXISTS suppliers(
  supplier_id TEXT PRIMARY KEY, name TEXT NOT NULL, region TEXT,
  cold_chain_capable INTEGER NOT NULL DEFAULT 0, contact_email TEXT);
CREATE TABLE IF NOT EXISTS supplier_catalog(
  supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
  medicine_id TEXT NOT NULL REFERENCES medicines(medicine_id),
  unit_price REAL CHECK(unit_price>=0), std_lead_days INTEGER NOT NULL CHECK(std_lead_days>0),
  PRIMARY KEY(supplier_id, medicine_id));
CREATE TABLE IF NOT EXISTS purchase_orders(
  po_id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
  medicine_id TEXT NOT NULL REFERENCES medicines(medicine_id),
  dest_facility_id TEXT NOT NULL REFERENCES facilities(facility_id),
  qty INTEGER NOT NULL CHECK(qty>0), order_date TEXT NOT NULL, promised_date TEXT NOT NULL,
  actual_date TEXT, received_qty INTEGER,
  status TEXT NOT NULL CHECK(status IN('Delivered','Open','Cancelled')));
CREATE TABLE IF NOT EXISTS shipments(
  shipment_id TEXT PRIMARY KEY, po_id TEXT REFERENCES purchase_orders(po_id),
  supplier_id TEXT REFERENCES suppliers(supplier_id), origin TEXT NOT NULL,
  dest_facility_id TEXT NOT NULL REFERENCES facilities(facility_id),
  medicine_id TEXT NOT NULL REFERENCES medicines(medicine_id),
  qty INTEGER NOT NULL CHECK(qty>0), ship_date TEXT NOT NULL, expected_arrival TEXT NOT NULL,
  actual_arrival TEXT, status TEXT NOT NULL CHECK(status IN('Delivered','In Transit')),
  simulated INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS lanes(
  origin_id TEXT NOT NULL REFERENCES facilities(facility_id),
  dest_id TEXT NOT NULL REFERENCES facilities(facility_id),
  distance_km REAL NOT NULL, transit_hours REAL NOT NULL, cost_per_unit REAL NOT NULL,
  capacity_units INTEGER NOT NULL, cold_ok INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(origin_id, dest_id));
CREATE TABLE IF NOT EXISTS disruption_events(
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL CHECK(event_type IN('supplier_delay','demand_surge','warehouse_disruption','transport_disruption','partial_delivery')),
  entity_id TEXT NOT NULL, magnitude REAL NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
  detected_date TEXT, description TEXT, simulated INTEGER NOT NULL DEFAULT 1,
  created_by TEXT, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS stock_movements(
  movement_id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
  facility_id TEXT NOT NULL REFERENCES facilities(facility_id),
  medicine_id TEXT NOT NULL REFERENCES medicines(medicine_id),
  batch_id INTEGER, movement_type TEXT NOT NULL, qty INTEGER NOT NULL, reference TEXT);
CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL, salt TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN('admin','supply_manager','warehouse_manager','viewer')),
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS recommendations(
  rec_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
  rec_type TEXT NOT NULL CHECK(rec_type IN('TRANSFER','PROCURE')),
  medicine_id TEXT NOT NULL REFERENCES medicines(medicine_id),
  source_id TEXT, dest_id TEXT NOT NULL, supplier_id TEXT,
  qty INTEGER NOT NULL CHECK(qty>0), est_cost REAL, eta_hours REAL, priority_score REAL, reasoning TEXT,
  status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN('Pending','Approved','Rejected','Modified','Executed')),
  decided_by TEXT, decided_at TEXT, comment TEXT, final_qty INTEGER, scenario_tag TEXT);
CREATE TABLE IF NOT EXISTS audit_log(
  audit_id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
  action TEXT NOT NULL, entity TEXT, entity_id TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS alert_status(
  alert_key TEXT PRIMARY KEY, status TEXT NOT NULL, updated_by TEXT, updated_at TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_cons ON consumption(facility_id, medicine_id, date);
CREATE INDEX IF NOT EXISTS ix_batch ON batches(facility_id, medicine_id);
CREATE INDEX IF NOT EXISTS ix_po ON purchase_orders(supplier_id, medicine_id);
"""


class Database:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c

    @contextmanager
    def tx(self):
        c = self.connect()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def init_schema(self):
        with self.tx() as c:
            c.executescript(SCHEMA)

    def df(self, sql, params=()):
        c = self.connect()
        try:
            return pd.read_sql_query(sql, c, params=params)
        finally:
            c.close()

    def execute(self, sql, params=()):
        with self.tx() as c:
            return c.execute(sql, params).lastrowid

    def executemany(self, sql, rows):
        with self.tx() as c:
            c.executemany(sql, rows)

    def scalar(self, sql, params=()):
        c = self.connect()
        try:
            r = c.execute(sql, params).fetchone()
            return None if r is None else r[0]
        finally:
            c.close()

    def insert_df(self, table, df):
        if df is None or df.empty:
            return
        cols = list(df.columns)
        sql = f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})"
        rows = [tuple(None if pd.isna(v) else (v.item() if hasattr(v, 'item') else v) for v in r)
                for r in df.itertuples(index=False, name=None)]
        self.executemany(sql, rows)

    def audit(self, actor, action, entity="", entity_id="", detail="", ts=None):
        from datetime import datetime
        self.execute("INSERT INTO audit_log(ts,actor,action,entity,entity_id,detail) VALUES(?,?,?,?,?,?)",
                     (ts or datetime.now().isoformat(timespec="seconds"), actor, action, entity, str(entity_id), detail))

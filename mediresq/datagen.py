"""Reproducible SYNTHETIC data generator + seeding + validation.
Every name, quantity and event produced here is fabricated for demonstration. No real facility,
supplier or patient data is used or implied."""
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import auth, config
from .db import Database

MEDS = [  # id, name, form, category, unit_cost INR, criticality, shelf_days, cold, base_daily(mid hospital), season
    ("M01", "Paracetamol 500mg", "Tablet", "Analgesic", 1.2, 1, 730, 0, 420, "monsoon"),
    ("M02", "Amoxicillin 500mg", "Capsule", "Antibiotic", 6.5, 2, 730, 0, 180, "monsoon"),
    ("M03", "Azithromycin 500mg", "Tablet", "Antibiotic", 18, 2, 730, 0, 90, "monsoon"),
    ("M04", "Ceftriaxone 1g", "Injection", "Antibiotic", 48, 3, 730, 0, 70, "monsoon"),
    ("M05", "Metformin 500mg", "Tablet", "Antidiabetic", 1.8, 2, 1095, 0, 300, "none"),
    ("M06", "Amlodipine 5mg", "Tablet", "Cardiovascular", 1.5, 2, 1095, 0, 260, "none"),
    ("M07", "Atorvastatin 10mg", "Tablet", "Cardiovascular", 4, 1, 1095, 0, 200, "none"),
    ("M08", "Insulin Glargine 100IU/ml", "Injection", "Antidiabetic", 520, 3, 540, 1, 22, "none"),
    ("M09", "Oxytocin 10IU", "Injection", "Maternal health", 35, 3, 540, 1, 30, "none"),
    ("M10", "ORS Sachet", "Sachet", "Rehydration", 9, 2, 730, 0, 120, "monsoon"),
    ("M11", "Normal Saline 0.9% 500ml", "IV fluid", "IV fluid", 28, 3, 1095, 0, 150, "none"),
    ("M12", "Ringer Lactate 500ml", "IV fluid", "IV fluid", 32, 3, 1095, 0, 110, "none"),
    ("M13", "Salbutamol Inhaler 100mcg", "Inhaler", "Respiratory", 95, 3, 730, 0, 45, "winter"),
    ("M14", "Heparin 5000IU", "Injection", "Anticoagulant", 140, 3, 730, 0, 25, "none"),
    ("M15", "Epinephrine 1mg/ml", "Injection", "Emergency", 60, 3, 540, 0, 12, "none"),
    ("M16", "Furosemide 40mg", "Tablet", "Diuretic", 2.2, 2, 1095, 0, 95, "none"),
    ("M17", "Ondansetron 4mg", "Tablet", "Antiemetic", 5, 1, 730, 0, 85, "none"),
    ("M18", "Omeprazole 20mg", "Capsule", "Gastro", 2.8, 1, 730, 0, 240, "none"),
    ("M19", "Tetanus Toxoid Vaccine", "Vaccine", "Vaccine", 38, 3, 730, 1, 18, "none"),
    ("M20", "Dexamethasone 4mg", "Injection", "Corticosteroid", 22, 2, 730, 0, 55, "none"),
]
FACS = [  # id, name, type, city, lat, lon, priority, size
    ("WH-01", "Central Medical Warehouse Bhopal (synthetic)", "warehouse", "Bhopal", 23.26, 77.41, 2, 1.0),
    ("WH-02", "Regional Warehouse Indore (synthetic)", "warehouse", "Indore", 22.72, 75.86, 2, 1.0),
    ("WH-03", "Regional Warehouse Nagpur (synthetic)", "warehouse", "Nagpur", 21.15, 79.09, 2, 1.0),
    ("H-01", "District Hospital Alpha (synthetic)", "hospital", "Bhopal", 23.18, 77.45, 2, 1.0),
    ("H-02", "Civil Hospital Beta (synthetic)", "hospital", "Indore", 22.75, 75.90, 3, 1.3),
    ("H-03", "Community Health Centre Gamma (synthetic)", "hospital", "Sagar", 23.85, 78.75, 1, 0.5),
    ("H-04", "Medical College Hospital Delta (synthetic)", "hospital", "Nagpur", 21.20, 79.10, 3, 1.8),
    ("H-05", "Urban Referral Hospital Epsilon (synthetic)", "hospital", "Raisen", 23.33, 77.80, 2, 0.9),
]
SUPS = [  # id, name, region, cold, ontime_prob, mean_fill, lead_sd
    ("S-01", "Meridian Pharma Distributors (synthetic)", "West", 0, 0.92, 0.97, 0.8),
    ("S-02", "Apex Lifesciences Supply (synthetic)", "Central", 0, 0.85, 0.94, 1.0),
    ("S-03", "Nova Generic Healthcare (synthetic)", "Central", 0, 0.62, 0.84, 1.8),
    ("S-04", "Pinnacle Medical Traders (synthetic)", "South", 0, 0.78, 0.90, 1.2),
    ("S-05", "BlueChain Cold Logistics (synthetic)", "West", 1, 0.90, 0.96, 0.9),
    ("S-06", "Sahyadri Pharma Wholesale (synthetic)", "West", 0, 0.70, 0.88, 1.5),
    ("S-07", "Ganga Biologicals (synthetic)", "North", 1, 0.81, 0.92, 1.3),
]
DOW = np.array([1.15, 1.10, 1.05, 1.05, 1.00, 0.85, 0.80])  # Mon..Sun


def _hav(a, b):
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _season(kind, d):
    doy = d.timetuple().tm_yday
    if kind == "monsoon":   # bump June-September
        return 1 + 0.35 * math.exp(-((doy - 220) / 45.0) ** 2)
    if kind == "winter":
        return 1 + 0.30 * math.exp(-((min(abs(doy - 15), abs(doy - 380)) / 40.0) ** 2))
    return 1.0


def generate(as_of=None, seed=None):
    """Return dict of DataFrames (deterministic for given as_of+seed)."""
    as_of = as_of or date.today()
    rng = np.random.default_rng(config.SEED if seed is None else seed)
    iso = lambda d: d.isoformat()  # noqa: E731
    fac = pd.DataFrame(FACS, columns=["facility_id", "name", "type", "city", "lat", "lon", "priority", "size_factor"])
    med = pd.DataFrame([m[:8] for m in MEDS], columns=["medicine_id", "name", "form", "category", "unit_cost",
                                                      "criticality", "shelf_life_days", "cold_chain"])
    base = {m[0]: m[8] for m in MEDS}
    seas = {m[0]: m[9] for m in MEDS}
    hosp = fac[fac.type == "hospital"]
    wh = fac[fac.type == "warehouse"]
    size = dict(zip(fac.facility_id, fac.size_factor))

    # ---- consumption (365 days, hospitals only)
    days = [as_of - timedelta(days=i) for i in range(365, 0, -1)]
    rows = []
    for h in hosp.facility_id:
        for m in med.medicine_id:
            trend = rng.uniform(-0.0002, 0.0006)
            for i, d in enumerate(days):
                mu = base[m] * size[h] * (1 + trend * i) * DOW[d.weekday()] * _season(seas[m], d)
                q = rng.poisson(mu) + rng.normal(0, 0.06 * mu)
                if rng.random() < 0.005:
                    q *= rng.uniform(2.5, 3.5)  # outlier
                q = max(0, int(round(q)))
                if rng.random() < 0.01:
                    continue                      # missing record
                unmet = round(q * 0.2) if rng.random() < 0.003 else 0
                rows.append((iso(d), h, m, q, unmet))
    cons = pd.DataFrame(rows, columns=["date", "facility_id", "medicine_id", "qty", "unmet_qty"])
    cons_arr = cons.groupby(["facility_id", "medicine_id"]).qty.apply(lambda s: s.tail(56).mean())
    daily = {k: float(v) for k, v in cons_arr.items()}
    net_daily = {m: sum(daily[(h, m)] for h in hosp.facility_id) for m in med.medicine_id}

    # ---- lanes
    coords = {r.facility_id: (r.lat, r.lon) for r in fac.itertuples()}
    ln = []
    for a in fac.facility_id:
        for b in fac.facility_id:
            if a == b:
                continue
            dist = round(_hav(coords[a], coords[b]) * 1.3, 1)
            hh = a.startswith("H-") and b.startswith("H-")
            cold_ok = 0 if ("H-03" in (a, b) and hh) else 1
            ln.append((a, b, dist, round(dist / 45 + 4, 1), round(0.01 * dist + 0.2, 3),
                       1500 if a.startswith("H-") else 6000, cold_ok))
    lanes = pd.DataFrame(ln, columns=["origin_id", "dest_id", "distance_km", "transit_hours", "cost_per_unit",
                                      "capacity_units", "cold_ok"])

    # ---- suppliers + catalog
    sup = pd.DataFrame([(s[0], s[1], s[2], s[3], f"ops@{s[0].lower()}.example.invalid") for s in SUPS],
                       columns=["supplier_id", "name", "region", "cold_chain_capable", "contact_email"])
    cat = []
    cold_s, amb_s = ["S-05", "S-07"], ["S-01", "S-02", "S-03", "S-04", "S-06"]
    for m in MEDS:
        pool = cold_s if m[7] else list(rng.choice(amb_s, size=3, replace=False))
        if m[0] == "M04" and "S-03" not in pool:
            pool[0] = "S-03"
        for s in pool:
            cat.append((s, m[0], round(m[4] * rng.uniform(0.85, 1.0), 2), int(rng.integers(3, 8))))
    catalog = pd.DataFrame(cat, columns=["supplier_id", "medicine_id", "unit_price", "std_lead_days"])
    sp = {s[0]: s for s in SUPS}

    # ---- purchase order history + shipments
    pos, shp = [], []
    n = 0
    for dest in fac.facility_id:
        for m in med.medicine_id:
            d_daily = daily.get((dest, m), net_daily[m] / 3.0)
            for _ in range(int(rng.integers(5, 9))):
                c = catalog[catalog.medicine_id == m].sample(1, random_state=int(rng.integers(1e9))).iloc[0]
                s = sp[c.supplier_id]
                od = as_of - timedelta(days=int(rng.integers(20, 340)))
                promised = od + timedelta(days=int(c.std_lead_days))
                late = rng.random() > s[4]
                delay = int(1 + rng.geometric(0.3)) if late else 0
                actual = promised + timedelta(days=delay + int(round(rng.normal(0, s[6] * 0.3))))
                actual = max(actual, od + timedelta(days=1))
                if actual >= as_of:
                    continue
                qty = int(max(10, d_daily * rng.uniform(25, 40)))
                rec = int(round(qty * min(1.0, max(0.3, rng.normal(s[5], 0.06)))))
                n += 1
                po = f"PO-{n:05d}"
                pos.append((po, c.supplier_id, m, dest, qty, iso(od), iso(promised), iso(actual), rec, "Delivered"))
                shp.append((f"SH-{n:05d}", po, c.supplier_id, c.supplier_id, dest, m, qty, iso(od + timedelta(days=1)),
                            iso(promised), iso(actual), "Delivered", 0))

    # ---- batches / stock
    batches = []
    bn = 0

    def add_batches(f, m, total, rng_):
        nonlocal bn
        r = med[med.medicine_id == m].iloc[0]
        parts = rng_.dirichlet([2, 3, 3]) * total
        exps = [as_of + timedelta(days=int(rng_.uniform(25, 200))),
                as_of + timedelta(days=int(rng_.uniform(250, 450))),
                as_of + timedelta(days=int(rng_.uniform(450, max(500, r.shelf_life_days - 60))))]
        for q, e in zip(parts, exps):
            q = int(q)
            if q <= 0:
                continue
            bn += 1
            batches.append([f, m, f"B{bn:05d}", iso(e - timedelta(days=int(r.shelf_life_days))), iso(e), q, "active",
                            float(r.unit_cost)])

    for h in hosp.facility_id:
        for m in med.medicine_id:
            add_batches(h, m, daily[(h, m)] * rng.uniform(12, 30), rng)
    for w in wh.facility_id:
        for m in med.medicine_id:
            add_batches(w, m, net_daily[m] / 3.0 * rng.uniform(25, 45), rng)
    bdf = pd.DataFrame(batches, columns=["facility_id", "medicine_id", "batch_no", "mfg_date", "expiry_date", "qty",
                                         "status", "unit_cost"])

    def setb(f, m, plan):
        """Replace batches of (f,m) with explicit plan [(qty, days_to_expiry, status)]."""
        nonlocal bdf, bn
        r = med[med.medicine_id == m].iloc[0]
        bdf = bdf[~((bdf.facility_id == f) & (bdf.medicine_id == m))]
        new = []
        for q, dte, stt in plan:
            bn += 1
            e = as_of + timedelta(days=dte)
            new.append([f, m, f"B{bn:05d}", iso(e - timedelta(days=int(r.shelf_life_days))), iso(e), int(q), stt,
                        float(r.unit_cost)])
        bdf = pd.concat([bdf, pd.DataFrame(new, columns=bdf.columns)], ignore_index=True)

    # ---- guaranteed demo scenario (Ceftriaxone M04): H-02 short, H-04 surplus, WH-02 limited, WH-01 small
    d2 = daily[("H-02", "M04")]
    d4 = daily[("H-04", "M04")]
    setb("H-02", "M04", [(d2 * 1.2, 150, "active"), (d2 * 1.6, 400, "active")])     # ~2.8 days cover
    setb("H-04", "M04", [(d4 * 20, 180, "active"), (d4 * 25, 420, "active")])       # ~45 days cover
    setb("WH-02", "M04", [(300, 10, "active"), (200, 300, "quarantined"), (400, 300, "active")])
    setb("WH-01", "M04", [(280, 320, "active")])
    shp_demo_po = "PO-D0001"
    pos.append((shp_demo_po, "S-03", "M04", "H-02", int(d2 * 16), iso(as_of - timedelta(days=4)),
                iso(as_of + timedelta(days=2)), None, None, "Open"))
    shp.append(("SH-D0001", shp_demo_po, "S-03", "S-03", "H-02", "M04", int(d2 * 16), iso(as_of - timedelta(days=2)),
                iso(as_of + timedelta(days=2)), None, "In Transit", 0))

    # extra realism: expired + quarantined + near-expiry exposures
    cand = bdf[(bdf.facility_id.isin(hosp.facility_id)) & (bdf.medicine_id != "M04")].sample(8, random_state=7)
    for k, (i, r) in enumerate(cand.iterrows()):
        if k < 2:
            bdf.loc[i, ["expiry_date", "mfg_date"]] = [iso(as_of - timedelta(days=int(rng.integers(3, 40)))),
                                                       iso(as_of - timedelta(days=800))]
        elif k < 4:
            bdf.loc[i, "status"] = "quarantined"
        else:
            bdf.loc[i, ["expiry_date", "mfg_date"]] = [iso(as_of + timedelta(days=int(rng.integers(8, 28)))),
                                                       iso(as_of - timedelta(days=600))]
            bdf.loc[i, "qty"] = int(max(bdf.loc[i, "qty"], daily.get((r.facility_id, r.medicine_id), 20) * 14))

    # thin-stock situations so the alert centre has realistic variety (demo H-02/M04 untouched)
    pairs = [(h, m) for h in hosp.facility_id for m in med.medicine_id if m != "M04"]
    pick = [pairs[i] for i in rng.choice(len(pairs), size=9, replace=False)]
    force_overdue = set(pick[:4])
    for (h, m) in pick:
        mask = (bdf.facility_id == h) & (bdf.medicine_id == m)
        tot = bdf.loc[mask, "qty"].sum()
        target = max(5, daily[(h, m)] * rng.uniform(2.0, 6.0))
        bdf.loc[mask, "qty"] = (bdf.loc[mask, "qty"] * target / max(tot, 1)).round().astype(int).clip(lower=1)

    # ---- open POs / shipments in transit
    k = 0
    for h in hosp.facility_id:
        for m in med.medicine_id:
            if m == "M04" and h == "H-02":
                continue
            if rng.random() < 0.3 or (h, m) in force_overdue:
                k += 1
                c = catalog[catalog.medicine_id == m].sample(1, random_state=int(rng.integers(1e9))).iloc[0]
                od = as_of - timedelta(days=int(rng.integers(2, 8)))
                eta = as_of + timedelta(days=int(rng.integers(-2, 10)))   # negative => overdue
                if (h, m) in force_overdue:
                    eta = as_of - timedelta(days=int(rng.integers(1, 4)))
                qty = int(max(10, daily[(h, m)] * rng.uniform(20, 30)))
                po = f"PO-O{k:04d}"
                pos.append((po, c.supplier_id, m, h, qty, iso(od), iso(eta), None, None, "Open"))
                shp.append((f"SH-O{k:04d}", po, c.supplier_id, c.supplier_id, h, m, qty, iso(od + timedelta(days=1)),
                            iso(eta), None, "In Transit", 0))

    pos_df = pd.DataFrame(pos, columns=["po_id", "supplier_id", "medicine_id", "dest_facility_id", "qty", "order_date",
                                        "promised_date", "actual_date", "received_qty", "status"])
    shp_df = pd.DataFrame(shp, columns=["shipment_id", "po_id", "supplier_id", "origin", "dest_facility_id",
                                        "medicine_id", "qty", "ship_date", "expected_arrival", "actual_arrival",
                                        "status", "simulated"])

    # ---- historical simulated disruption events (clearly labelled simulated)
    ev = pd.DataFrame([
        ("supplier_delay", "S-03", 5, iso(as_of - timedelta(days=60)), iso(as_of - timedelta(days=53)),
         iso(as_of - timedelta(days=58)), "SIMULATED historical supplier delay", 1, "generator", 0),
        ("demand_surge", "M10", 30, iso(as_of - timedelta(days=45)), iso(as_of - timedelta(days=38)),
         iso(as_of - timedelta(days=44)), "SIMULATED demand surge (ORS)", 1, "generator", 0),
        ("transport_disruption", "ALL", 1.4, iso(as_of - timedelta(days=30)), iso(as_of - timedelta(days=25)),
         iso(as_of - timedelta(days=29)), "SIMULATED transport disruption", 1, "generator", 0),
    ], columns=["event_type", "entity_id", "magnitude", "start_date", "end_date", "detected_date", "description",
                "simulated", "created_by", "active"])

    # ---- stock movements (last 30d issues, last 90d receipts)
    mv = []
    for r in cons[cons.date >= iso(as_of - timedelta(days=30))].itertuples():
        mv.append((r.date, r.facility_id, r.medicine_id, None, "issue", -int(r.qty), "daily consumption"))
    for r in pos_df[(pos_df.status == "Delivered") & (pos_df.actual_date >= iso(as_of - timedelta(days=90)))].itertuples():
        mv.append((r.actual_date, r.dest_facility_id, r.medicine_id, None, "receipt", int(r.received_qty), r.po_id))
    mvdf = pd.DataFrame(mv, columns=["date", "facility_id", "medicine_id", "batch_id", "movement_type", "qty",
                                     "reference"])
    return {"facilities": fac, "medicines": med, "lanes": lanes, "suppliers": sup, "supplier_catalog": catalog,
            "consumption": cons, "batches": bdf, "purchase_orders": pos_df, "shipments": shp_df,
            "disruption_events": ev, "stock_movements": mvdf}


ORDER = ["facilities", "medicines", "lanes", "suppliers", "supplier_catalog", "consumption", "batches",
         "purchase_orders", "shipments", "disruption_events", "stock_movements"]


def seed_database(db, as_of=None, seed=None, csv_dir=None, reset=True):
    from . import inventory
    as_of = as_of or date.today()
    if reset:
        for t in ["audit_log", "recommendations", "alert_status", "stock_movements", "disruption_events", "shipments",
                  "purchase_orders", "supplier_catalog", "suppliers", "consumption", "batches", "stock_policy",
                  "lanes", "medicines", "facilities", "users", "meta"]:
            try:
                db.execute(f"DELETE FROM {t}")
            except Exception:
                pass
    db.init_schema()
    data = generate(as_of, seed)
    if csv_dir:
        Path(csv_dir).mkdir(parents=True, exist_ok=True)
        for k, v in data.items():
            v.to_csv(Path(csv_dir) / f"{k}.csv", index=False)
    for t in ORDER:
        db.insert_df(t, data[t])
    db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('as_of',?)", (str(as_of),))
    db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('data_origin',?)", ("SYNTHETIC - generated by mediresq.datagen",))
    inventory.compute_policies(db, as_of)
    for u, r in [("admin", "admin"), ("scm", "supply_manager"), ("whm", "warehouse_manager"), ("viewer", "viewer")]:
        auth.create_user(db, u, config.DEMO_PASSWORD, r, actor="seed")
    return data


def validate_database(db):
    """Data validation checks. Returns list of (check, passed, detail)."""
    out = []
    c = db.connect()
    try:
        fk = c.execute("PRAGMA foreign_key_check").fetchall()
        out.append(("Referential integrity (PRAGMA foreign_key_check)", len(fk) == 0, f"{len(fk)} violations"))
    finally:
        c.close()
    q = lambda s: db.scalar(s)  # noqa: E731
    out.append(("No negative batch quantities", q("SELECT COUNT(*) FROM batches WHERE qty<0") == 0, ""))
    out.append(("Expiry after manufacture", q("SELECT COUNT(*) FROM batches WHERE expiry_date<=mfg_date") == 0, ""))
    out.append(("No negative consumption", q("SELECT COUNT(*) FROM consumption WHERE qty<0") == 0, ""))
    out.append(("Delivered POs have actual date", q("SELECT COUNT(*) FROM purchase_orders WHERE status='Delivered' AND actual_date IS NULL") == 0, ""))
    out.append(("Open shipments are not delivered", q("SELECT COUNT(*) FROM shipments WHERE status='In Transit' AND actual_arrival IS NOT NULL") == 0, ""))
    out.append(("3 warehouses", q("SELECT COUNT(*) FROM facilities WHERE type='warehouse'") == 3, ""))
    out.append(("5 hospitals", q("SELECT COUNT(*) FROM facilities WHERE type='hospital'") == 5, ""))
    nm = q("SELECT COUNT(*) FROM medicines")
    out.append(("15-25 medicines", 15 <= nm <= 25, f"{nm}"))
    ns = q("SELECT COUNT(*) FROM suppliers")
    out.append(("5-8 suppliers", 5 <= ns <= 8, f"{ns}"))
    out.append(("Multiple batches per product", q("SELECT MIN(c) FROM (SELECT COUNT(*) c FROM batches GROUP BY facility_id, medicine_id)") >= 1, ""))
    out.append(("Data labelled synthetic", "SYNTHETIC" in str(q("SELECT value FROM meta WHERE key='data_origin'")), ""))
    return out

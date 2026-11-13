"""Batch & expiry intelligence: FEFO, buckets, wastage risk, safe transfer candidates."""
from datetime import date
import numpy as np
import pandas as pd

from . import config, inventory


def batch_table(db, as_of):
    b = inventory.usable_batches(db, as_of)
    f = db.df("SELECT facility_id, name AS facility FROM facilities")
    m = db.df("SELECT medicine_id, name AS medicine FROM medicines")
    b = b.merge(f, on="facility_id").merge(m, on="medicine_id")
    b["value_inr"] = b.qty * b.unit_cost.fillna(0)
    b["bucket"] = pd.cut(b.days_to_expiry, [-10**6, 0, 30, 60, 90, 10**6], labels=["Expired", "0-30d", "31-60d", "61-90d", ">90d"])
    return b


def fefo(db, facility_id, medicine_id, as_of, min_days=0):
    """Usable batches (never expired/quarantined) in First-Expiry-First-Out order."""
    b = inventory.usable_batches(db, as_of)
    b = b[(b.facility_id == facility_id) & (b.medicine_id == medicine_id) & b.usable & (b.qty > 0) & (b.days_to_expiry >= min_days)]
    return b.sort_values(["expiry_date", "batch_id"])


def wastage_risk(db, as_of, horizon=90):
    """Projected unconsumed quantity per batch at its expiry, using FEFO draw-down at forecast-free average demand.
    Warehouse batches are assumed drawn at their average daily outflow (network share)."""
    b = batch_table(db, as_of)
    pol = db.df("SELECT facility_id, medicine_id, avg_daily_consumption AS d FROM stock_policy")
    b = b.merge(pol, on=["facility_id", "medicine_id"], how="left")
    out = []
    for (f, m), g in b[b.usable].groupby(["facility_id", "medicine_id"]):
        g = g.sort_values("expiry_date")
        cum = 0
        for r in g.itertuples():
            consumable = max(0.0, (r.d or 0) * r.days_to_expiry - cum)
            waste = max(0.0, r.qty - consumable)
            out.append((r.batch_id, waste, waste * (r.unit_cost or 0)))
            cum += r.qty
    w = pd.DataFrame(out, columns=["batch_id", "projected_waste_qty", "projected_waste_inr"])
    b = b.merge(w, on="batch_id", how="left").fillna({"projected_waste_qty": 0, "projected_waste_inr": 0})
    b.loc[~b.usable, "projected_waste_qty"] = b.qty  # expired stock is fully lost value
    b.loc[~b.usable, "projected_waste_inr"] = b.value_inr
    b["projected_waste_qty"] = b.projected_waste_qty.round(0)
    return b


def safe_transfer_candidates(db, as_of):
    """Near-expiry batches (<=60d) with projected waste that can be moved to a facility with low cover,
    arriving with at least MIN_SHELF_AFTER_ARRIVAL days left. Never uses expired/quarantined stock."""
    w = wastage_risk(db, as_of)
    risk = w[(w.usable) & (w.days_to_expiry <= 60) & (w.projected_waste_qty > 0)]
    st = inventory.stock_summary(db, as_of)
    lanes = db.df("SELECT * FROM lanes")
    rows = []
    for r in risk.itertuples():
        tgt = st[(st.medicine_id == r.medicine_id) & (st.type == "hospital") & (st.facility_id != r.facility_id) & (st.days_of_cover < 15)]
        for t in tgt.itertuples():
            ln = lanes[(lanes.origin_id == r.facility_id) & (lanes.dest_id == t.facility_id)]
            if ln.empty:
                continue
            eta_d = ln.iloc[0].transit_hours / 24
            left = r.days_to_expiry - eta_d
            need = max(0, t.avg_daily_consumption * min(left, 30) - t.usable_qty)
            q = int(min(r.projected_waste_qty, r.qty, need))
            if left >= config.MIN_SHELF_AFTER_ARRIVAL and q > 0:
                rows.append((r.batch_no, r.medicine, r.facility_id, t.facility_id, q, int(r.days_to_expiry), round(left, 1),
                             round(q * (r.unit_cost or 0), 2)))
    return pd.DataFrame(rows, columns=["batch_no", "medicine", "from", "to", "qty", "days_to_expiry", "days_left_on_arrival", "value_saved_inr"])

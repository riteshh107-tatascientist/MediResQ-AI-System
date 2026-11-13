"""Inventory management: policies (safety stock / ROP), stock summary, CRUD, movements."""
from datetime import date, timedelta
import re

import numpy as np
import pandas as pd

from . import config


def _d(x):
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def lead_time_stats(db):
    """Historical lead time (order -> actual delivery) per medicine: mean, std (days)."""
    po = db.df("SELECT medicine_id, order_date, actual_date FROM purchase_orders WHERE status='Delivered'")
    if po.empty:
        return pd.DataFrame(columns=["medicine_id", "lt_mean", "lt_std"])
    po["lt"] = (pd.to_datetime(po.actual_date) - pd.to_datetime(po.order_date)).dt.days
    return po.groupby("medicine_id").lt.agg(lt_mean="mean", lt_std="std").fillna(1.0).reset_index()


def avg_daily(db, as_of, window=56):
    """Mean/std daily consumption per (facility, medicine); warehouses = network demand / #warehouses."""
    start = str(_d(as_of) - timedelta(days=window))
    c = db.df("SELECT facility_id, medicine_id, date, qty FROM consumption WHERE date>=? AND date<?", (start, str(_d(as_of))))
    if c.empty:
        return pd.DataFrame(columns=["facility_id", "medicine_id", "mean", "std"])
    g = c.groupby(["facility_id", "medicine_id"]).qty.agg(["mean", "std"]).fillna(0).reset_index()
    net = g.groupby("medicine_id")[["mean"]].sum()
    nw = max(1, db.scalar("SELECT COUNT(*) FROM facilities WHERE type='warehouse'"))
    sd = g.groupby("medicine_id")["std"].apply(lambda s: float(np.sqrt((s ** 2).sum())))
    rows = []
    for w in db.df("SELECT facility_id FROM facilities WHERE type='warehouse'").facility_id:
        for m, r in net.iterrows():
            rows.append((w, m, r["mean"] / nw, sd[m] / nw))
    return pd.concat([g, pd.DataFrame(rows, columns=g.columns)], ignore_index=True)


def compute_policies(db, as_of):
    ad = avg_daily(db, as_of)
    lt = lead_time_stats(db).set_index("medicine_id")
    med = db.df("SELECT medicine_id, criticality FROM medicines").set_index("medicine_id")
    rows = []
    for r in ad.itertuples():
        L = float(lt.lt_mean.get(r.medicine_id, 7.0))
        Ls = float(lt.lt_std.get(r.medicine_id, 1.0))
        z = config.Z_BY_CRITICALITY[int(med.criticality[r.medicine_id])]
        ss = z * np.sqrt(L * r.std ** 2 + (r.mean * Ls) ** 2)
        rop = r.mean * L + ss
        rows.append((r.facility_id, r.medicine_id, round(ss, 1), round(rop + r.mean * 14, 1),
                     round(ss, 1), round(rop, 1), round(r.mean, 2)))
    db.execute("DELETE FROM stock_policy")
    db.executemany("INSERT INTO stock_policy(facility_id,medicine_id,min_stock,max_stock,safety_stock,reorder_point,avg_daily_consumption) VALUES(?,?,?,?,?,?,?)", rows)


def usable_batches(db, as_of):
    b = db.df("SELECT * FROM batches")
    b["days_to_expiry"] = (pd.to_datetime(b.expiry_date) - pd.Timestamp(_d(as_of))).dt.days
    b["usable"] = (b.status == "active") & (b.days_to_expiry > 0)
    return b


def stock_summary(db, as_of):
    """On-hand usable stock vs policy per facility-medicine, with valuation and days of cover."""
    b = usable_batches(db, as_of)
    tot = b.groupby(["facility_id", "medicine_id"]).qty.sum().rename("total_qty")
    use = b[b.usable].groupby(["facility_id", "medicine_id"]).qty.sum().rename("usable_qty")
    val = b[b.usable].assign(v=lambda x: x.qty * x.unit_cost).groupby(["facility_id", "medicine_id"]).v.sum().rename("value_inr")
    s = db.df("SELECT * FROM stock_policy")
    df = s.set_index(["facility_id", "medicine_id"]).join([tot, use, val], how="outer").reset_index()
    df[["total_qty", "usable_qty", "value_inr"]] = df[["total_qty", "usable_qty", "value_inr"]].fillna(0)
    df["days_of_cover"] = np.where(df.avg_daily_consumption > 0, df.usable_qty / df.avg_daily_consumption.replace(0, np.nan), np.nan)
    f = db.df("SELECT facility_id, name AS facility, type FROM facilities")
    m = db.df("SELECT medicine_id, name AS medicine, criticality, unit_cost FROM medicines")
    df = df.merge(f, on="facility_id").merge(m, on="medicine_id")
    df["status"] = np.select([df.usable_qty <= df.safety_stock, df.usable_qty <= df.reorder_point, df.usable_qty > df.max_stock * 1.25],
                             ["Critical", "Reorder", "Overstock"], "OK")
    return df


# ---------------- CRUD (validated) ----------------
def _validate_med(name, unit_cost, criticality, shelf_life_days, cold_chain):
    name = (name or "").strip()
    if not re.fullmatch(r"[\w .,%/()+\-]{2,80}", name):
        raise ValueError("Medicine name must be 2-80 characters (letters, digits and . , % / ( ) + -).")
    if unit_cost is not None and float(unit_cost) < 0:
        raise ValueError("Unit cost cannot be negative.")
    if int(criticality) not in (1, 2, 3):
        raise ValueError("Criticality must be 1, 2 or 3.")
    if shelf_life_days is not None and int(shelf_life_days) <= 0:
        raise ValueError("Shelf life must be positive.")
    return name


def add_medicine(db, medicine_id, name, form="", category="", unit_cost=None, criticality=2, shelf_life_days=None,
                 cold_chain=0, actor="system"):
    name = _validate_med(name, unit_cost, criticality, shelf_life_days, cold_chain)
    if not re.fullmatch(r"[A-Za-z0-9\-]{2,12}", medicine_id or ""):
        raise ValueError("Medicine ID must be 2-12 alphanumeric characters.")
    db.execute("INSERT INTO medicines(medicine_id,name,form,category,unit_cost,criticality,shelf_life_days,cold_chain) VALUES(?,?,?,?,?,?,?,?)",
               (medicine_id, name, form, category, unit_cost, int(criticality), shelf_life_days, int(cold_chain)))
    db.audit(actor, "add_medicine", "medicine", medicine_id, name)


def update_medicine(db, medicine_id, actor="system", **fields):
    allowed = {"name", "form", "category", "unit_cost", "criticality", "shelf_life_days", "cold_chain"}
    cur = db.df("SELECT * FROM medicines WHERE medicine_id=?", (medicine_id,))
    if cur.empty:
        raise ValueError("Medicine not found.")
    merged = {**cur.iloc[0].to_dict(), **{k: v for k, v in fields.items() if k in allowed}}
    _validate_med(merged["name"], merged["unit_cost"], merged["criticality"], merged["shelf_life_days"], merged["cold_chain"])
    db.execute("UPDATE medicines SET name=?,form=?,category=?,unit_cost=?,criticality=?,shelf_life_days=?,cold_chain=? WHERE medicine_id=?",
               (merged["name"], merged["form"], merged["category"], merged["unit_cost"], int(merged["criticality"]),
                merged["shelf_life_days"], int(merged["cold_chain"]), medicine_id))
    db.audit(actor, "update_medicine", "medicine", medicine_id, str(fields))


def delete_medicine(db, medicine_id, actor="system"):
    """Deletes only medicines with no dependent records (FK-protected)."""
    try:
        db.execute("DELETE FROM medicines WHERE medicine_id=?", (medicine_id,))
    except Exception as e:  # sqlite3.IntegrityError
        raise ValueError("Cannot delete: medicine has batches, consumption or orders linked to it.") from e
    db.audit(actor, "delete_medicine", "medicine", medicine_id)


def add_batch(db, facility_id, medicine_id, batch_no, mfg_date, expiry_date, qty, unit_cost=None, status="active", actor="system"):
    if int(qty) < 0:
        raise ValueError("Quantity cannot be negative.")
    if str(expiry_date) <= str(mfg_date):
        raise ValueError("Expiry must be after manufacture date.")
    bid = db.execute("INSERT INTO batches(facility_id,medicine_id,batch_no,mfg_date,expiry_date,qty,status,unit_cost) VALUES(?,?,?,?,?,?,?,?)",
                     (facility_id, medicine_id, batch_no, str(mfg_date), str(expiry_date), int(qty), status, unit_cost))
    db.execute("INSERT INTO stock_movements(date,facility_id,medicine_id,batch_id,movement_type,qty,reference) VALUES(?,?,?,?,?,?,?)",
               (str(date.today()), facility_id, medicine_id, bid, "receipt", int(qty), "manual batch entry"))
    db.audit(actor, "add_batch", "batch", bid, f"{medicine_id}@{facility_id} qty={qty}")
    return bid


def adjust_batch(db, batch_id, delta, reason, actor="system", on=None):
    cur = db.scalar("SELECT qty FROM batches WHERE batch_id=?", (batch_id,))
    if cur is None:
        raise ValueError("Batch not found.")
    if cur + int(delta) < 0:
        raise ValueError("Adjustment would make stock negative.")
    r = db.df("SELECT facility_id, medicine_id FROM batches WHERE batch_id=?", (batch_id,)).iloc[0]
    db.execute("UPDATE batches SET qty=qty+? WHERE batch_id=?", (int(delta), batch_id))
    db.execute("INSERT INTO stock_movements(date,facility_id,medicine_id,batch_id,movement_type,qty,reference) VALUES(?,?,?,?,?,?,?)",
               (str(on or date.today()), r.facility_id, r.medicine_id, batch_id, "adjustment", int(delta), reason))
    db.audit(actor, "adjust_batch", "batch", batch_id, f"delta={delta} reason={reason}")


def set_batch_status(db, batch_id, status, actor="system"):
    if status not in ("active", "quarantined"):
        raise ValueError("Invalid status")
    db.execute("UPDATE batches SET status=? WHERE batch_id=?", (status, batch_id))
    db.audit(actor, "batch_status", "batch", batch_id, status)

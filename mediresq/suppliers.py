"""Supplier intelligence from purchase-order delivery history."""
from datetime import date
import numpy as np
import pandas as pd


def supplier_metrics(db, as_of=None):
    po = db.df("""SELECT p.*, s.name AS supplier FROM purchase_orders p JOIN suppliers s USING(supplier_id)
                  WHERE p.status='Delivered'""")
    sups = db.df("SELECT supplier_id, name AS supplier FROM suppliers")
    if po.empty:
        return sups.assign(orders=0)
    for c in ["order_date", "promised_date", "actual_date"]:
        po[c] = pd.to_datetime(po[c])
    po["delay"] = (po.actual_date - po.promised_date).dt.days.clip(lower=0)
    po["lt"] = (po.actual_date - po.order_date).dt.days
    po["late"] = po.delay > 0
    po["fill"] = (po.received_qty / po.qty).clip(upper=1)
    g = po.groupby("supplier_id").agg(orders=("po_id", "count"), on_time_rate=("late", lambda s: 1 - s.mean()),
                                      delay_freq=("late", "mean"), avg_delay_days=("delay", "mean"),
                                      avg_lead_time=("lt", "mean"), lt_std=("lt", "std"), fulfilment_rate=("fill", "mean")).reset_index()
    g["lt_cv"] = (g.lt_std / g.avg_lead_time).fillna(0)
    g["reliability_score"] = (100 * (0.5 * g.on_time_rate + 0.3 * g.fulfilment_rate + 0.2 * (1 - g.lt_cv.clip(upper=1)))).round(1)
    g["risk"] = pd.cut(g.reliability_score, [-1, 70, 82, 101], labels=["High", "Medium", "Low"])
    g = sups.merge(g, on="supplier_id", how="left")
    # current exposure: open POs past promised date
    asof = pd.Timestamp(as_of or date.today())
    op = db.df("SELECT supplier_id, promised_date FROM purchase_orders WHERE status='Open'")
    op["overdue"] = pd.to_datetime(op.promised_date) < asof
    ex = op.groupby("supplier_id").agg(open_pos=("overdue", "size"), overdue_pos=("overdue", "sum")).reset_index()
    g = g.merge(ex, on="supplier_id", how="left").fillna({"open_pos": 0, "overdue_pos": 0})
    return g


def mean_delay_days(db):
    m = supplier_metrics(db)
    return {r.supplier_id: float(r.avg_delay_days) for r in m.itertuples() if pd.notna(r.avg_delay_days)}

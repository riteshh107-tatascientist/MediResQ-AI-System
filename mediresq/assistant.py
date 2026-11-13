"""MediResQ Intelligence Assistant: rule-based intent routing -> real queries/calculations. No LLM, no invented answers."""
import re
import pandas as pd

from . import analytics, expiry, forecasting, inventory, stockout, suppliers

HELP = ("I can answer from the live database: critical stock, facility risk, expiring batches, supplier delays, "
        "pending recommendations, medicine stock/forecast, and explain the latest recovery recommendation.")


def _med_in(db, q):
    meds = db.df("SELECT medicine_id, name FROM medicines")
    ql = q.lower()
    for r in meds.itertuples():
        if r.name.lower() in ql or r.name.lower().split()[0] in ql:
            return r
    return None


def answer(db, as_of, question, ctx=None):
    q = question.lower().strip()
    k = ctx or analytics.kpis(db, as_of)
    so, summ = k["_so"], k["_summary"]
    if re.search(r"critical.*(stock|medic)|which medicines.*critical", q):
        d = so[so.risk_level.isin(["Critical", "High"])][["facility", "medicine", "on_hand", "days_remaining", "risk_level", "reason"]]
        c = summ[(summ.status == "Critical") & (summ.type == "hospital")][["facility", "medicine", "usable_qty", "safety_stock"]]
        return (f"{len(c)} hospital stock lines are at/below safety stock and {len(d)} lines carry High/Critical stock-out risk.", d if len(d) else c)
    if re.search(r"(greatest|highest|most).*risk.*facilit|facilit.*(greatest|highest|most).*risk|which facility", q):
        g = so.groupby("facility").agg(max_risk=("risk_score", "max"), avg_risk=("risk_score", "mean"),
                                       high_critical_lines=("risk_level", lambda s: int(s.isin(["Critical", "High"]).sum()))).sort_values(["high_critical_lines", "max_risk"], ascending=False).round(1)
        return (f"{g.index[0]} has the greatest stock-out exposure ({int(g.iloc[0].high_critical_lines)} High/Critical lines).", g.reset_index())
    if re.search(r"expir", q):
        days = 60 if "60" in q else 90 if "90" in q else 30
        if "month" in q or "30" in q:
            days = 30
        w = expiry.wastage_risk(db, as_of)
        d = w[(w.usable) & (w.days_to_expiry <= days) & (w.qty > 0)][["facility", "medicine", "batch_no", "expiry_date", "days_to_expiry", "qty", "value_inr", "projected_waste_qty"]].sort_values("days_to_expiry")
        return (f"{len(d)} active batches expire within {days} days (value INR {d.value_inr.sum():,.0f}).", d)
    if re.search(r"supplier.*(delay|late|worst|risk)|highest delay", q):
        s = k["_suppliers"].sort_values("avg_delay_days", ascending=False)[["supplier", "on_time_rate", "avg_delay_days", "fulfilment_rate", "reliability_score", "risk", "overdue_pos"]].round(2)
        return (f"{s.iloc[0].supplier} has the highest average delay ({s.iloc[0].avg_delay_days:.1f} days, on-time {s.iloc[0].on_time_rate:.0%}).", s)
    if re.search(r"recommend|recovery|explain", q):
        r = db.df("SELECT r.*, m.name medicine FROM recommendations r JOIN medicines m USING(medicine_id) ORDER BY rec_id DESC LIMIT 1")
        if r.empty:
            return ("No recommendations exist yet. Run the Recovery Planner first.", None)
        x = r.iloc[0]
        return (f"Latest recommendation #{x.rec_id} ({x.rec_type}, {x.status}): {x.qty} x {x.medicine} -> {x.dest_id}"
                f"{' from ' + x.source_id if x.source_id else ''}. Why: {x.reasoning}", None)
    if re.search(r"pending|approval", q):
        p = db.df("SELECT rec_id, rec_type, medicine_id, source_id, dest_id, qty, priority_score FROM recommendations WHERE status='Pending' ORDER BY priority_score DESC")
        return (f"{len(p)} recommendations await human approval.", p)
    m = _med_in(db, q)
    if m is not None and re.search(r"forecast|demand|predict", q):
        r = forecasting.run_forecast(db, "ALL", m.medicine_id, as_of)
        f = r["forecast"]
        return (f"Network demand forecast for {m.name} (best validated model: {r['eval']['best_model']}): "
                f"next 7 days {f.forecast[:7].sum():.0f} units, 30 days {f.forecast.sum():.0f}.", f.head(14).round({"forecast": 1, "lower_80": 1, "upper_80": 1}))
    if m is not None:
        d = summ[summ.medicine_id == m.medicine_id][["facility", "usable_qty", "total_qty", "days_of_cover", "status"]].round(1)
        return (f"Stock position for {m.name}.", d)
    if re.search(r"resilien|summary|overview", q):
        return (f"Resilience index {k['resilience_index']}/100 (heuristic). {k['predicted_stockouts']} predicted stock-outs, "
                f"{k['near_expiry_batches']} near-expiry batches, {k['pending_decisions']} pending decisions.", None)
    return (HELP, None)

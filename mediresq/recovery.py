"""AI Recovery Planner: fuses forecasting, stockout risk, supplier risk, disruptions and the optimizer
into prioritised actions. Persists them as PENDING recommendations (human approval required)."""
from datetime import datetime
import pandas as pd

from . import optimizer, stockout, suppliers
from .state import State


def _best_supplier(db, medicine_id, eff, sm):
    cat = db.df("SELECT * FROM supplier_catalog WHERE medicine_id=?", (medicine_id,)).merge(
        sm[["supplier_id", "reliability_score", "supplier"]], on="supplier_id")
    if cat.empty:
        return None
    cat["adj"] = cat.reliability_score - cat.supplier_id.map(lambda s: 20 * eff.supplier_delay.get(s, 0))
    cat.loc[cat.supplier_id.isin(eff.partial_fill), "adj"] -= 25
    return cat.sort_values("adj", ascending=False).iloc[0]


def generate(db, as_of, effects=None, persist=True, tag="", state=None):
    st = state or State(db, as_of, effects)
    eff = st.effects
    so = stockout.compute(db, as_of, state=st)
    opt = optimizer.build_plan(db, as_of, state=st)
    sm = suppliers.supplier_metrics(db, as_of)
    acts = []
    for r in opt["plan"].itertuples():
        acts.append({"rec_type": "TRANSFER", "medicine_id": r.medicine_id, "medicine": r.medicine, "source_id": r.source,
                     "dest_id": r.destination, "supplier_id": None, "qty": int(r.qty), "est_cost": float(r.est_cost_inr),
                     "eta_hours": float(r.eta_hours), "priority_score": 10.0 * r.priority_weight + max(0, 15 - r.first_shortage_day),
                     "reasoning": r.reasoning + f" Batches (FEFO): {r.batches_fefo}."})
    covered = {(a["dest_id"], a["medicine_id"]) for a in acts}
    need = so[(so.reorder_qty > 0) | (so.risk_level.isin(["Critical", "High"]))]
    unmet = {(u.destination, u.medicine_id): u.unmet_units for u in opt["unmet"].itertuples()} if len(opt["unmet"]) else {}
    for r in need.itertuples():
        qty = int(max(r.reorder_qty, unmet.get((r.facility_id, r.medicine_id), 0)))
        if qty <= 0:
            continue
        s = _best_supplier(db, r.medicine_id, eff, sm)
        if s is None:
            continue
        why = (f"{r.reason}. Replenish {qty} units; chosen supplier {s.supplier} (reliability {s.reliability_score}, "
               f"std lead {int(s.std_lead_days)}d)")
        if s.supplier_id in eff.supplier_delay:
            why += " - NOTE: supplier has an active (simulated) delay"
        acts.append({"rec_type": "PROCURE", "medicine_id": r.medicine_id, "medicine": r.medicine, "source_id": None,
                     "dest_id": r.facility_id, "supplier_id": s.supplier_id, "qty": qty, "est_cost": float(qty * s.unit_price),
                     "eta_hours": float(s.std_lead_days * 24), "priority_score": float(r.risk_score + 5 * r.criticality
                                                                                       - (8 if (r.facility_id, r.medicine_id) in covered else 0)),
                     "reasoning": why})
    df = pd.DataFrame(acts)
    if len(df):
        df = df.sort_values("priority_score", ascending=False).reset_index(drop=True)
    if persist and len(df):
        now = datetime.now().isoformat(timespec="seconds")
        for r in df.itertuples():
            src = r.source_id if isinstance(r.source_id, str) else None
            sup_id = r.supplier_id if isinstance(r.supplier_id, str) else None
            dup = db.scalar("""SELECT COUNT(*) FROM recommendations WHERE status='Pending' AND rec_type=? AND medicine_id=?
                               AND COALESCE(source_id,'')=? AND dest_id=? AND COALESCE(scenario_tag,'')=?""",
                            (r.rec_type, r.medicine_id, src or "", r.dest_id, tag))
            if dup:
                continue
            db.execute("""INSERT INTO recommendations(created_at,rec_type,medicine_id,source_id,dest_id,supplier_id,qty,est_cost,eta_hours,priority_score,reasoning,status,scenario_tag)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,'Pending',?)""",
                       (now, r.rec_type, r.medicine_id, src, r.dest_id, sup_id, r.qty, r.est_cost, r.eta_hours,
                        r.priority_score, r.reasoning, tag))
        db.audit("planner", "plan_generated", "recommendation", "", f"{len(df)} actions; tag={tag}")
    return {"actions": df, "stockout": so, "optimizer": opt}

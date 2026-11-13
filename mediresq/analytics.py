"""KPIs, resilience index, historical analytics and controlled policy-comparison simulation."""
from datetime import date, timedelta
import numpy as np
import pandas as pd

from . import alerts as alerts_mod, expiry, inventory, logistics, stockout, suppliers
from .state import State


def kpis(db, as_of, effects=None, state=None):
    st = state or State(db, as_of, effects)
    so = stockout.compute(db, as_of, state=st)
    al = alerts_mod.build(db, as_of, state=st, so=so)
    summ = inventory.stock_summary(db, as_of)
    w = expiry.wastage_risk(db, as_of)
    sm = suppliers.supplier_metrics(db, as_of)
    sh = logistics.shipments_status(db, as_of, st.effects)
    pend = int(db.scalar("SELECT COUNT(*) FROM recommendations WHERE status='Pending'") or 0)
    hosp = summ[summ.type == "hospital"]
    crit_share = float((hosp.status == "Critical").mean())
    risk_share = float(so.risk_level.isin(["Critical", "High"]).mean()) if len(so) else 0.0
    sup_rel = float(sm.reliability_score.mean() / 100) if sm.reliability_score.notna().any() else 0.5
    tot_val = float(summ.value_inr.sum()) or 1.0
    near_val = float(w[(w.days_to_expiry <= 30)].value_inr.sum())
    transit = sh[sh.transport_status != "Delivered"]
    ship_ok = float(1 - (transit.transport_status == "Delayed").mean()) if len(transit) else 1.0
    idx = 100 * (0.30 * (1 - crit_share) + 0.25 * (1 - risk_share) + 0.20 * sup_rel
                 + 0.15 * (1 - min(1.0, near_val / tot_val * 10)) + 0.10 * ship_ok)
    return {
        "total_medicines": int(db.scalar("SELECT COUNT(*) FROM medicines")),
        "total_facilities": int(db.scalar("SELECT COUNT(*) FROM facilities WHERE type='hospital'")),
        "total_warehouses": int(db.scalar("SELECT COUNT(*) FROM facilities WHERE type='warehouse'")),
        "inventory_value": float(summ.value_inr.sum()),
        "critical_alerts": int((al.severity == "Critical").sum()) if len(al) else 0,
        "predicted_stockouts": int(so.risk_level.isin(["Critical", "High"]).sum()),
        "near_expiry_batches": int(((w.days_to_expiry <= 90) & (w.days_to_expiry > 0) & (w.qty > 0)).sum()),
        "supplier_risks": int((sm.risk == "High").sum()),
        "pending_decisions": pend,
        "resilience_index": round(idx, 1),
        "_so": so, "_alerts": al, "_summary": summ, "_suppliers": sm, "_wastage": w, "_shipments": sh, "_state": st,
    }


def historical_metrics(db, as_of):
    c = db.df("SELECT date, facility_id, medicine_id, qty, unmet_qty FROM consumption")
    tot, unmet = c.qty.sum(), c.unmet_qty.sum()
    sd = int((c.groupby(["date", "facility_id", "medicine_id"]).unmet_qty.sum() > 0).sum())
    summ = inventory.stock_summary(db, as_of)
    cost = db.df("SELECT medicine_id, unit_cost FROM medicines").set_index("medicine_id").unit_cost
    ann_val = float((c.groupby("medicine_id").qty.sum() * cost).sum())
    inv_val = float(summ[summ.type == "hospital"].value_inr.sum()) or 1.0
    sm = suppliers.supplier_metrics(db, as_of)
    w = expiry.wastage_risk(db, as_of)
    return {"demand_fulfilment_pct": round(float(100 * (1 - unmet / tot)), 2), "stockout_days_recorded": sd,
            "stock_availability_pct": round(100 * float((summ[summ.type == 'hospital'].usable_qty > 0).mean()), 1),
            "inventory_turnover_x": round(ann_val / inv_val, 2),
            "expired_stock_value_inr": round(float(w[~w.usable].value_inr.sum()), 2),
            "projected_wastage_value_inr": round(float(w[w.usable].projected_waste_inr.sum()), 2),
            "supplier_on_time_pct": round(100 * float(sm.on_time_rate.mean()), 1),
            "lead_time_variability_cv": round(float(sm.lt_cv.mean()), 3),
            "detection": logistics.detection_time_stats(db)}


def policy_comparison(db, as_of, n_runs=20, days=90, seed=11, shock_days=7):
    """Controlled Monte-Carlo comparison with common random numbers.
    A = static min/max (no safety stock, no forecast adaptation, no transfers).
    B = adaptive: trailing-28d demand + safety stock + overdue-order expediting + hospital-to-hospital balancing.
    Demand is bootstrapped from history; lead times from historical POs; a supplier shock hits 5 random medicines.
    SIMULATION on SYNTHETIC data - not real hospital outcomes."""
    rng = np.random.default_rng(seed)
    cons = db.df("SELECT date, facility_id, medicine_id, qty FROM consumption")
    piv = cons.pivot_table(index=["facility_id", "medicine_id"], columns="date", values="qty", aggfunc="sum").fillna(0)
    keys = list(piv.index)
    S = len(keys)
    hist = piv.values[:, -180:]
    meds = sorted({k[1] for k in keys})
    midx = np.array([meds.index(k[1]) for k in keys])
    pol = db.df("SELECT * FROM stock_policy").set_index(["facility_id", "medicine_id"])
    po = db.df("SELECT medicine_id, order_date, actual_date FROM purchase_orders WHERE status='Delivered'")
    po["ltd"] = (pd.to_datetime(po.actual_date) - pd.to_datetime(po.order_date)).dt.days
    lts = {m: po[po.medicine_id == m].ltd.values for m in meds}
    mu = hist.mean(1)
    Lm = np.array([lts[k[1]].mean() for k in keys])
    ss_b = np.array([pol.loc[k].safety_stock for k in keys])
    start = mu * 20
    uv = db.df("SELECT medicine_id, unit_cost FROM medicines").set_index("medicine_id").unit_cost
    ucost = np.array([uv[k[1]] for k in keys])
    res = {"A": [], "B": []}
    for run in range(n_runs):
        dem = hist[np.arange(S)[:, None], rng.integers(0, hist.shape[1], size=(S, days))]
        lt_draw = np.stack([rng.choice(lts[k[1]], size=days) for k in keys]).astype(int)
        shocked = rng.choice(len(meds), size=5, replace=False)
        shock = np.isin(midx, shocked)
        for pname in ("A", "B"):
            stock = start.copy()
            arr = np.zeros((S, days + 60))
            pipe = np.zeros(S)
            sold_t = dem_t = so_days = 0.0
            hold = trans = 0.0
            hist_run = list(hist.T[-28:])
            for t in range(days):
                stock += arr[:, t]
                pipe = np.maximum(0, pipe - arr[:, t])
                s = np.minimum(stock, dem[:, t])
                stock -= s
                sold_t += s.sum()
                dem_t += dem[:, t].sum()
                so_days += float((dem[:, t] > s + 1e-9).sum())
                hist_run.append(dem[:, t])
                if pname == "B":
                    m28 = np.mean(hist_run[-28:], axis=0)
                    rop = m28 * Lm + ss_b
                    for mi in range(len(meds)):    # balance between hospitals
                        ix = np.where(midx == mi)[0]
                        need = ix[stock[ix] < m28[ix] * 2]
                        give = ix[stock[ix] > m28[ix] * 12]
                        for n in need:
                            for g in give:
                                q = min(m28[n] * 5, stock[g] - m28[g] * 10)
                                if q > 1:
                                    stock[g] -= q
                                    arr[n, t + 1] += q
                                    trans += q * 0.6
                else:
                    rop = mu * Lm
                    m28 = mu
                pos = stock + pipe
                order = pos <= rop
                qty = np.where(order, rop + m28 * 14 - pos, 0)
                lead = lt_draw[:, t] + np.where(shock & (20 <= t) & (t <= 20 + 4 * shock_days // 2), shock_days, 0)
                for i in np.where(order)[0]:
                    if t + lead[i] < days + 59:
                        arr[i, t + lead[i]] += qty[i]
                pipe += qty
                hold += float((stock * ucost).sum())
            res[pname].append({"fill_rate_pct": 100 * sold_t / dem_t, "stockout_series_days": so_days / S,
                               "avg_inventory_value_inr": hold / days, "transfer_cost_inr": trans})
    out = pd.DataFrame({k: pd.DataFrame(v).mean() for k, v in res.items()}).T
    out.index = ["A: Static min/max policy", "B: Intelligent (adaptive + balancing)"]
    sd = {k: pd.DataFrame(v).std() for k, v in res.items()}
    out["fill_rate_sd"] = [sd["A"].fill_rate_pct, sd["B"].fill_rate_pct]
    return out.round(2)

"""Stockout early-warning. risk_score is a HEURISTIC index (0-100). p_stockout is a Monte-Carlo
probability from a normal demand-noise model: model-based, NOT empirically calibrated."""
import math
import numpy as np
import pandas as pd

from .state import State


def _score(cover_ratio, shortage_day, unmet, avg_d, crit):
    s1 = float(np.clip(1 - cover_ratio / 2, 0, 1))
    s2 = 0.0 if (shortage_day is None or shortage_day > 14) else float(np.clip(1 - (shortage_day - 1) / 14, 0.3, 1))
    s3 = float(np.clip(unmet / max(14 * avg_d, 1e-9), 0, 1))
    return float(min(100, 100 * (0.45 * s1 + 0.35 * s2 + 0.20 * s3) * (0.7 + 0.1 * crit)))


def _level(score, crit, shortage_day, lt):
    lv = "Critical" if score >= 70 else "High" if score >= 45 else "Medium" if score >= 25 else "Low"
    if crit == 3 and shortage_day is not None and shortage_day <= lt and lv in ("Low", "Medium"):
        lv = "High"
    return lv


def compute(db, as_of, effects=None, state=None, n_sims=400, seed=7):
    st = state or State(db, as_of, effects)
    rng = np.random.default_rng(seed)
    rows = []
    for f in st.hospitals:
        for m, mr in st.med.iterrows():
            d = st.demand(f, m)
            if d.sum() <= 0:
                continue
            oh = st.on_hand(f, m)
            L = st.lead_time(m)
            W = max(1, int(math.ceil(L)))
            avg14 = float(d[:14].mean())
            sim = st.simulate(f, m)
            un = sim["unmet"]
            sd = int(np.argmax(un > 1e-6)) + 1 if (un > 1e-6).any() else None
            inb_all = st.inbound_for(f, m)
            on_order = sum(x["qty"] for x in inb_all)
            pol = st.policy.get((f, m))
            ss = pol.safety_stock * st.effects.demand_factor(m) if pol else 0.0
            ltd = float(d[:W].sum())
            rop = ltd + ss
            ip = oh + on_order
            max_lvl = rop + avg14 * 14
            reorder_qty = float(max(0, max_lvl - ip)) if ip <= rop else 0.0
            days_rem = oh / avg14 if avg14 > 0 else float("inf")
            cover_eff = (sd - 1) if sd else 30.0   # days until projected stock-out, counting inbound shipments
            cover_ratio = cover_eff / max(L, 1)
            unmet14 = float(un[:14].sum())
            score = _score(cover_ratio, sd, unmet14, avg14, int(mr.criticality))
            lvl = _level(score, int(mr.criticality), sd, L)
            # Monte-Carlo probability of stock running out within one lead time (existing inbound counted)
            sig = st.sigma(f, m)
            draws = np.maximum(0, rng.normal(d[:W], max(sig, 1e-9), size=(n_sims, W)))
            arr = np.zeros(W)
            for x in inb_all:
                if x["day"] <= W:
                    arr[x["day"] - 1] += x["qty"]
            pos = oh + np.cumsum(arr)[None, :] - np.cumsum(draws, axis=1)
            p = float((pos.min(axis=1) < 0).mean())
            reasons = []
            if sd is not None:
                reasons.append(f"projected shortage in {sd} day(s) (unmet {unmet14:.0f} units in 14d)")
            if days_rem < L and sd is not None:
                reasons.append(f"only {days_rem:.1f} days of on-hand cover vs {L:.1f}-day supplier lead time")
            if ip <= rop:
                reasons.append("inventory position below reorder point")
            late = [x for x in inb_all if x["overdue"]]
            if late:
                reasons.append(f"{len(late)} inbound shipment(s) overdue")
            if st.effects.supplier_delay and any(x["supplier_id"] in st.effects.supplier_delay for x in inb_all):
                reasons.append("inbound delayed by active (simulated) supplier disruption")
            if int(mr.criticality) == 3:
                reasons.append("life-saving / criticality 3")
            rows.append({"facility_id": f, "facility": st.fac.loc[f, "name"], "medicine_id": m, "medicine": mr["name"],
                         "criticality": int(mr.criticality), "on_hand": round(oh), "inbound_qty": round(on_order),
                         "avg_daily_forecast": round(avg14, 1), "days_remaining": round(days_rem, 1),
                         "lead_time_days": round(L, 1), "lead_time_demand": round(ltd), "inventory_position": round(ip),
                         "reorder_point": round(rop), "reorder_qty": round(reorder_qty),
                         "shortage_in_days": sd, "shortage_date": str(st.as_of + pd.Timedelta(days=sd - 1)) if sd else None,
                         "unmet_14d": round(unmet14), "risk_score": round(score, 1), "risk_level": lvl,
                         "p_stockout_lt_model": round(p, 3), "reason": "; ".join(reasons) if reasons else "adequate cover"})
    df = pd.DataFrame(rows)
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return df.sort_values(["risk_level", "risk_score"], key=lambda s: s.map(order) if s.name == "risk_level" else -s).reset_index(drop=True)

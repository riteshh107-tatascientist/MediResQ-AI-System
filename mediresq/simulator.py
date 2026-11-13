"""What-if scenario simulator: baseline vs disrupted vs recovered (deterministic projection from forecasts).
All outputs are SIMULATED projections, not observed outcomes."""
import numpy as np
import pandas as pd

from . import forecasting, optimizer
from .effects import Effects
from .state import State


def _metrics(st, extra=None, meds=None):
    rows = []
    agg_stock = np.zeros(st.H)
    for f in st.hospitals:
        for m in st.med.index:
            if meds and m not in meds:
                continue
            ei, eo = (extra or {}).get((f, m), ([], []))
            sim = st.simulate(f, m, extra_in=ei, extra_out=eo, replenish=True)
            dem = sim["demand"].sum()
            if dem <= 0:
                continue
            rows.append({"facility_id": f, "medicine_id": m, "medicine": st.med.loc[m, "name"],
                         "criticality": int(st.med.loc[m, "criticality"]), "demand": dem, "unmet": sim["unmet"].sum(),
                         "stockout_days": int((sim["unmet"] > 1e-6).sum()), "min_stock": sim["stock"].min(),
                         "end_stock": sim["stock"][-1]})
    return pd.DataFrame(rows)


def _summ(name, d, cost=0.0):
    crit = d[d.criticality == 3]
    return {"scenario": name, "series_with_stockout": int((d.stockout_days > 0).sum()),
            "total_stockout_days": int(d.stockout_days.sum()),
            "fill_rate_pct": round(100 * (1 - d.unmet.sum() / d.demand.sum()), 2),
            "critical_med_fill_rate_pct": round(100 * (1 - crit.unmet.sum() / max(crit.demand.sum(), 1e-9)), 2),
            "unmet_units": round(d.unmet.sum()), "recovery_cost_inr": round(cost, 2)}


def run(db, as_of, effects, horizon=30, meds=None, forecasts=None):
    fc = forecasts or forecasting.fast_forecast_all(db, as_of, horizon)
    base = State(db, as_of, Effects(), horizon, fc)
    dis = State(db, as_of, effects, horizon, fc)
    d0 = _metrics(base, meds=meds)
    d1 = _metrics(dis, meds=meds)
    opt = optimizer.build_plan(db, as_of, state=dis, only_medicines=meds)
    extra, cost = {}, 0.0
    for r in opt["plan"].itertuples():
        extra.setdefault((r.destination, r.medicine_id), ([], []))[0].append((r.arrival_day, r.qty))
        if r.source in dis.hospitals:
            extra.setdefault((r.source, r.medicine_id), ([], []))[1].append((1, r.qty))
        cost += r.est_cost_inr
    d2 = _metrics(dis, extra, meds=meds)
    summary = pd.DataFrame([_summ("Baseline (no disruption)", d0), _summ("Disrupted (no response)", d1),
                            _summ("Recovered (optimized transfers)", d2, cost)])
    detail = d0[["facility_id", "medicine", "criticality", "stockout_days", "unmet"]].merge(
        d1[["facility_id", "medicine", "stockout_days", "unmet", "min_stock"]], on=["facility_id", "medicine"], suffixes=("_base", "_disrupted")).merge(
        d2[["facility_id", "medicine", "stockout_days", "unmet"]].rename(columns={"stockout_days": "stockout_days_recovered", "unmet": "unmet_recovered"}),
        on=["facility_id", "medicine"])
    return {"summary": summary, "detail": detail, "optimizer": opt, "states": (base, dis, extra)}


def stock_curves(states, medicine_id):
    base, dis, extra = states
    out = {}
    for name, st, ex in (("Baseline", base, None), ("Disrupted", dis, None), ("Recovered", dis, extra)):
        tot = np.zeros(st.H)
        for f in st.hospitals:
            ei, eo = (ex or {}).get((f, medicine_id), ([], []))
            tot += st.simulate(f, medicine_id, extra_in=ei, extra_out=eo, replenish=True)["stock"]
        out[name] = tot
    return pd.DataFrame(out, index=pd.date_range(pd.Timestamp(base.as_of), periods=base.H)).rename_axis("date").reset_index()

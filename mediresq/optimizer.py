"""Inventory redistribution optimizer.
Model (integer program, per planning horizon):
  x[s,d,m] >= 0 integer = units of medicine m moved from source s to destination d
  u[d,m]   >= 0         = unmet shortage left at d
  min  sum cost[s,d,m]*x + sum penalty[d,m]*u
  s.t. sum_s x[s,d,m] + u[d,m] = shortage[d,m]          (cover shortage)
       sum_d x[s,d,m] <= surplus[s,m]                    (min reserve respected)
       x[s,d,m] <= eligible[s,d,m]                       (expiry/quarantine/shelf-life-on-arrival)
       sum_m x[s,d,m] <= lane_capacity[s,d]              (transfer capacity)
       x = 0 if lane unusable (down warehouse, cold-chain mismatch, arrives after shortage window)
Backends: OR-Tools (preferred, CP-SAT-free MIP via pywraplp) or SciPy HiGHS MILP (fallback)."""
import math
from collections import defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd

from . import config
from .state import State


def _solver_backend():
    try:
        from ortools.linear_solver import pywraplp  # noqa: F401
        return "ortools"
    except Exception:
        return "scipy"


def _solve(n_x, n_u, cost, pen, ub_x, eq_rows, le_rows, backend):
    """Variables: [x..., u...]. eq_rows/le_rows: list of (coef_dict, rhs)."""
    nv = n_x + n_u
    obj = np.concatenate([cost, pen])
    ub = np.concatenate([ub_x, np.full(n_u, 1e9)])
    if backend == "ortools":
        from ortools.linear_solver import pywraplp
        sv = pywraplp.Solver.CreateSolver("SCIP") or pywraplp.Solver.CreateSolver("CBC")
        vs = [sv.IntVar(0, float(ub[i]), f"v{i}") for i in range(nv)]
        for co, rhs in eq_rows:
            sv.Add(sum(c * vs[i] for i, c in co.items()) == rhs)
        for co, rhs in le_rows:
            sv.Add(sum(c * vs[i] for i, c in co.items()) <= rhs)
        sv.Minimize(sum(obj[i] * vs[i] for i in range(nv)))
        st = sv.Solve()
        if st not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return None
        return np.array([v.solution_value() for v in vs])
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix
    cons = []
    for rows, lo_is_rhs in ((eq_rows, True), (le_rows, False)):
        if not rows:
            continue
        A = lil_matrix((len(rows), nv))
        rhs = np.zeros(len(rows))
        for r, (co, b) in enumerate(rows):
            for i, c in co.items():
                A[r, i] = c
            rhs[r] = b
        cons.append(LinearConstraint(A.tocsr(), rhs if lo_is_rhs else -np.inf, rhs))
    res = milp(c=obj, constraints=cons, integrality=np.ones(nv), bounds=Bounds(np.zeros(nv), ub))
    return res.x if res.success else None


def build_plan(db, as_of, effects=None, state=None, backend=None, only_medicines=None):
    """Returns dict(plan=DataFrame, unmet=DataFrame, notes=list, summary=dict)."""
    st = state or State(db, as_of, effects)
    eff = st.effects
    backend = backend or _solver_backend()
    H = config.PLAN_HORIZON_DAYS
    net = defaultdict(float)
    for (f, m) in st.forecasts:
        net[m] += st.forecasts[(f, m)]["mean"][:7].mean()
    nw = max(1, len(st.warehouses))

    # ---- shortages at hospitals
    short = {}
    meta = {}
    for f in st.hospitals:
        for m, mr in st.med.iterrows():
            if only_medicines and m not in only_medicines:
                continue
            sim = st.simulate(f, m, H=H)
            q = float(sim["unmet"].sum())
            if q >= 1:
                first = int(np.argmax(sim["unmet"] > 1e-6)) + 1
                if first > math.ceil(st.lead_time(m)) + 2:
                    continue   # normal re-ordering can resolve it; handled by PROCURE recommendations
                last = H - int(np.argmax(sim["unmet"][::-1] > 1e-6))
                short[(f, m)] = int(math.ceil(q))
                meta[(f, m)] = {"first": first, "last": last, "w": int(mr.criticality) * int(st.fac.loc[f, "priority"]),
                                "avg": float(st.demand(f, m)[:H].mean())}
    # ---- surplus at sources
    surplus = {}
    for m, mr in st.med.iterrows():
        if only_medicines and m not in only_medicines:
            continue
        for s in st.hospitals + st.warehouses:
            if s in eff.warehouse_down:
                continue
            oh = st.on_hand(s, m)
            if oh <= 0:
                continue
            if s in st.hospitals:
                sim = st.simulate(s, m, H=H)
                pol = st.policy.get((s, m))
                ss = pol.safety_stock * eff.demand_factor(m) if pol else 0
                sp = float(max(0, sim["stock"].min() - ss)) if (sim["unmet"].sum() < 1) else 0.0
            else:
                reserve = config.WH_RESERVE_DAYS * net[m] * eff.demand_factor(m) / nw
                sp = max(0.0, oh - reserve)
            if sp >= 1:
                surplus[(s, m)] = int(sp)

    lanes = {(r.origin_id, r.dest_id): r for r in st.lanes.itertuples()}
    notes, X = [], []   # X entries: (s,d,m,eligible,cost,eta_h)
    why = defaultdict(list)
    for (d, m), need in short.items():
        mr = st.med.loc[m]
        win_last = meta[(d, m)]["last"]
        got = False
        for (s, mm), sp in surplus.items():
            if mm != m or s == d:
                continue
            ln = lanes.get((s, d))
            if ln is None:
                continue
            if s in eff.warehouse_down:
                continue
            if int(mr.cold_chain) and not ln.cold_ok:
                why[(d, m)].append(f"{s}->{d}: lane not cold-chain capable")
                continue
            eta_h = ln.transit_hours * eff.transit_mult
            arrive_day = int(math.ceil(eta_h / 24.0)) + 1
            if arrive_day > win_last:
                why[(d, m)].append(f"{s}->{d}: arrives day {arrive_day}, after shortage window (day {win_last})")
                continue
            b = st.batches[(st.batches.facility_id == s) & (st.batches.medicine_id == m) & st.batches.usable]
            ok = b[b.days_to_expiry - eta_h / 24.0 >= config.MIN_SHELF_AFTER_ARRIVAL]
            elig = int(min(ok.qty.sum(), sp))
            if elig <= 0:
                why[(d, m)].append(f"{s}: no batch keeps >= {config.MIN_SHELF_AFTER_ARRIVAL}d shelf life on arrival (or only quarantined/expired stock)")
                continue
            cpu = ln.cost_per_unit * eff.transport_cost_mult * (1.25 if int(mr.cold_chain) else 1.0)
            X.append((s, d, m, elig, cpu, eta_h, int(ln.capacity_units)))
            got = True
        if not got and not why[(d, m)]:
            why[(d, m)].append("no facility holds surplus of this medicine above its minimum reserve")

    if not short:
        return {"plan": pd.DataFrame(), "unmet": pd.DataFrame(), "notes": ["No projected shortages in the planning horizon."],
                "summary": {"shortage_units": 0, "covered_units": 0, "unmet_units": 0, "total_cost": 0, "backend": backend, "status": "no_shortage"}}

    keys = list(short.keys())
    nx = len(X)
    cost = np.array([x[4] for x in X]) if nx else np.zeros(0)
    ubx = np.array([x[3] for x in X], dtype=float) if nx else np.zeros(0)
    pen = np.array([100.0 * meta[k]["w"] for k in keys])
    eq, le = [], []
    for j, k in enumerate(keys):
        co = {i: 1 for i, x in enumerate(X) if (x[1], x[2]) == k}
        co[nx + j] = 1
        eq.append((co, short[k]))
    by_src = defaultdict(dict)
    for i, x in enumerate(X):
        by_src[(x[0], x[2])][i] = 1
    for key, co in by_src.items():
        le.append((co, surplus[key]))
    by_lane = defaultdict(dict)
    for i, x in enumerate(X):
        by_lane[(x[0], x[1])][i] = 1
    for key, co in by_lane.items():
        le.append((co, X[next(iter(co))][6]))
    sol = _solve(nx, len(keys), cost, pen, ubx, eq, le, backend)
    if sol is None:
        return {"plan": pd.DataFrame(), "unmet": pd.DataFrame(), "notes": ["Solver found no feasible solution."],
                "summary": {"status": "infeasible", "backend": backend}}
    xs = np.round(sol[:nx]).astype(int)
    us = np.round(sol[nx:]).astype(int)
    rows = []
    alloc_left = {}
    for i, x in enumerate(X):
        q = int(xs[i])
        if q <= 0:
            continue
        s, d, m, _el, cpu, eta_h, _cap = x
        # FEFO batch allocation honouring shelf-life-on-arrival
        b = st.batches[(st.batches.facility_id == s) & (st.batches.medicine_id == m) & st.batches.usable].sort_values("expiry_date")
        left, parts = q, []
        for r in b.itertuples():
            if r.days_to_expiry - eta_h / 24 < config.MIN_SHELF_AFTER_ARRIVAL:
                continue
            avail = r.qty - alloc_left.get((s, m, r.batch_id), 0)
            take = int(min(avail, left))
            if take > 0:
                parts.append(f"{r.batch_no}:{take} (exp {r.expiry_date})")
                alloc_left[(s, m, r.batch_id)] = alloc_left.get((s, m, r.batch_id), 0) + take
                left -= take
            if left <= 0:
                break
        mt = meta[(d, m)]
        timely = int(math.ceil(eta_h / 24)) + 1 <= mt["first"]
        rows.append({"medicine_id": m, "medicine": st.med.loc[m, "name"], "source": s, "destination": d,
                     "qty": q, "est_cost_inr": round(q * cpu, 2), "eta_hours": round(eta_h, 1),
                     "arrival_day": int(math.ceil(eta_h / 24)) + 1, "first_shortage_day": mt["first"], "timely": timely,
                     "batches_fefo": "; ".join(parts),
                     "priority_weight": mt["w"],
                     "reasoning": (f"{d} projected to be short {short[(d, m)]} units from day {mt['first']}; {s} holds surplus "
                                   f"above its reserve; lane {eta_h:.0f}h at INR {cpu:.2f}/unit; FEFO batches keep >= "
                                   f"{config.MIN_SHELF_AFTER_ARRIVAL}d shelf life on arrival"
                                   + ("" if timely else "; arrives after first stock-out day (partial relief)"))})
    plan = pd.DataFrame(rows)
    un_rows = []
    for j, k in enumerate(keys):
        if us[j] > 0:
            reason = why.get(k) or ["lane capacity or reserve limits exhausted"]
            un_rows.append({"destination": k[0], "medicine_id": k[1], "medicine": st.med.loc[k[1], "name"],
                            "shortage_units": short[k], "unmet_units": int(us[j]), "why_not_covered": " | ".join(dict.fromkeys(reason))})
    unmet = pd.DataFrame(un_rows)
    tot_short = int(sum(short.values()))
    summary = {"shortage_units": tot_short, "unmet_units": int(us.sum()), "covered_units": tot_short - int(us.sum()),
               "total_cost": float(plan.est_cost_inr.sum()) if len(plan) else 0.0, "backend": backend,
               "status": "feasible" if us.sum() == 0 else ("partial" if len(plan) else "infeasible")}
    if summary["status"] == "infeasible":
        notes.append("No feasible redistribution: " + "; ".join(sorted({r for v in why.values() for r in v})[:5]))
    return {"plan": plan, "unmet": unmet, "notes": notes, "summary": summary}

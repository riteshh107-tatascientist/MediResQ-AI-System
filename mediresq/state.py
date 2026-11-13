"""Operational snapshot (stock, inbound, demand forecast) + day-by-day inventory projection."""
from datetime import date, timedelta
import math

import numpy as np
import pandas as pd

from . import forecasting, inventory, suppliers
from .effects import Effects


def _d(x):
    return x if isinstance(x, date) else date.fromisoformat(str(x))


class State:
    def __init__(self, db, as_of, effects=None, horizon=30, forecasts=None):
        self.db, self.as_of, self.H = db, _d(as_of), horizon
        self.effects = effects or Effects()
        self.fac = db.df("SELECT * FROM facilities").set_index("facility_id")
        self.med = db.df("SELECT * FROM medicines").set_index("medicine_id")
        b = inventory.usable_batches(db, self.as_of)
        self.batches = b
        u = b[b.usable].groupby(["facility_id", "medicine_id"]).qty.sum()
        self.usable = {k: float(v) for k, v in u.items()}
        pol = db.df("SELECT * FROM stock_policy")
        self.policy = {(r.facility_id, r.medicine_id): r for r in pol.itertuples()}
        self.forecasts = forecasts if forecasts is not None else forecasting.fast_forecast_all(db, self.as_of, horizon)
        self.lt = inventory.lead_time_stats(db).set_index("medicine_id")
        self.lanes = db.df("SELECT * FROM lanes")
        self.hospitals = [f for f, r in self.fac.iterrows() if r.type == "hospital"]
        self.warehouses = [f for f, r in self.fac.iterrows() if r.type == "warehouse"]
        self.sup_delay = suppliers.mean_delay_days(db)
        self.inbound = self._inbound()
        cat = db.df("SELECT c.supplier_id, c.medicine_id, c.std_lead_days, COUNT(p.po_id) n FROM supplier_catalog c "
                    "LEFT JOIN purchase_orders p ON p.supplier_id=c.supplier_id AND p.medicine_id=c.medicine_id "
                    "GROUP BY c.supplier_id, c.medicine_id, c.std_lead_days ORDER BY n DESC")
        self.primary = {r.medicine_id: (r.supplier_id, int(r.std_lead_days)) for r in cat.drop_duplicates("medicine_id").itertuples()}

    # ---- inputs
    def lead_time(self, m):
        return float(self.lt.lt_mean.get(m, 7.0))

    def demand(self, f, m):
        fc = self.forecasts.get((f, m))
        base = fc["mean"][: self.H] if fc else np.zeros(self.H)
        return base * self.effects.demand_factor(m)

    def sigma(self, f, m):
        fc = self.forecasts.get((f, m))
        return (fc["sigma"] if fc else 0.0) * self.effects.demand_factor(m)

    def on_hand(self, f, m):
        return self.usable.get((f, m), 0.0)

    def _inbound(self):
        sh = self.db.df("SELECT * FROM shipments WHERE status='In Transit'")
        out = []
        for r in sh.itertuples():
            exp = _d(r.expected_arrival)
            overdue = exp < self.as_of
            if overdue:
                arr = self.as_of + timedelta(days=max(1, math.ceil(self.sup_delay.get(r.supplier_id, 1.0))))
            else:
                arr = exp
            arr = arr + timedelta(days=int(math.ceil(self.effects.supplier_delay.get(r.supplier_id, 0))))
            day = max(1, (arr - self.as_of).days + 1)
            q = r.qty * self.effects.partial_fill.get(r.supplier_id, 1.0)
            out.append({"shipment_id": r.shipment_id, "f": r.dest_facility_id, "m": r.medicine_id, "qty": q,
                        "day": day, "supplier_id": r.supplier_id, "overdue": overdue, "arrival_date": arr})
        return out

    def inbound_for(self, f, m):
        return [x for x in self.inbound if x["f"] == f and x["m"] == m]

    # ---- projection
    def simulate(self, f, m, extra_in=(), extra_out=(), H=None, with_inbound=True, replenish=False):
        """Projected end-of-day stock, unmet demand per day. extra_in/out: iterable of (day, qty).
        replenish=True applies the standing reorder-point policy (orders arrive after the primary supplier's
        lead time plus any active disruption delay)."""
        H = H or self.H
        d = self.demand(f, m)[:H]
        arr = np.zeros(H + 2)
        if with_inbound:
            for x in self.inbound_for(f, m):
                if x["day"] <= H:
                    arr[x["day"]] += x["qty"]
        for day, q in extra_in:
            if 1 <= day <= H:
                arr[int(day)] += q
        out = np.zeros(H + 2)
        for day, q in extra_out:
            if 1 <= day <= H:
                out[int(day)] += q
        stock = self.on_hand(f, m)
        ends, unmet, sold = [], [], []
        pol = self.policy.get((f, m))
        sup, lead = self.primary.get(m, (None, int(self.lead_time(m))))
        extra_delay = int(math.ceil(self.effects.supplier_delay.get(sup, 0)))
        fill = self.effects.partial_fill.get(sup, 1.0)
        pipeline = float(arr[1:].sum())
        for t in range(1, H + 1):
            if replenish and pol is not None:
                rop = pol.reorder_point * self.effects.demand_factor(m)
                pos = stock + pipeline - out[t:].sum() * 0
                if pos <= rop:
                    qty = rop + 14 * float(d.mean()) - pos
                    at = t + lead + extra_delay
                    if at <= H:
                        arr[at] += qty * fill
                    pipeline += qty * fill
            stock = max(0.0, stock + arr[t] - out[t])
            pipeline = max(0.0, pipeline - arr[t])
            s = min(stock, d[t - 1])
            sold.append(s)
            unmet.append(d[t - 1] - s)
            stock -= s
            ends.append(stock)
        return {"stock": np.array(ends), "unmet": np.array(unmet), "sold": np.array(sold), "demand": d}

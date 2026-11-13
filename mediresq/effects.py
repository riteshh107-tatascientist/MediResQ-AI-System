"""Disruption effects applied on top of the baseline state (never mutates stored data)."""
from dataclasses import dataclass, field
import pandas as pd


@dataclass
class Effects:
    supplier_delay: dict = field(default_factory=dict)      # supplier_id -> extra days
    demand_mult: dict = field(default_factory=dict)         # medicine_id | 'ALL' -> multiplier
    warehouse_down: set = field(default_factory=set)        # facility ids unavailable
    transport_cost_mult: float = 1.0
    transit_mult: float = 1.0
    partial_fill: dict = field(default_factory=dict)        # supplier_id -> delivered fraction
    labels: list = field(default_factory=list)

    def demand_factor(self, med):
        return self.demand_mult.get(med, 1.0) * self.demand_mult.get("ALL", 1.0)

    def is_empty(self):
        return not (self.supplier_delay or self.demand_mult or self.warehouse_down or self.partial_fill
                    or self.transport_cost_mult != 1.0 or self.transit_mult != 1.0)

    def describe(self):
        out = [f"Supplier {s}: +{d:g} day delay" for s, d in self.supplier_delay.items()]
        out += [f"Demand x{v:g} ({k})" for k, v in self.demand_mult.items()]
        out += [f"Warehouse {w} disrupted" for w in sorted(self.warehouse_down)]
        out += [f"Supplier {s}: partial delivery {v:.0%}" for s, v in self.partial_fill.items()]
        if self.transport_cost_mult != 1.0:
            out.append(f"Transport cost x{self.transport_cost_mult:g}")
        if self.transit_mult != 1.0:
            out.append(f"Transit time x{self.transit_mult:g}")
        return out


def from_events(db, as_of):
    """Build Effects from disruption_events active on as_of (all such events are labelled simulated)."""
    ev = db.df("SELECT * FROM disruption_events WHERE active=1 AND start_date<=? AND end_date>=?",
               (str(as_of), str(as_of)))
    e = Effects()
    for r in ev.itertuples():
        t = r.event_type
        if t == "supplier_delay":
            e.supplier_delay[r.entity_id] = max(e.supplier_delay.get(r.entity_id, 0), r.magnitude)
        elif t == "demand_surge":
            e.demand_mult[r.entity_id] = e.demand_mult.get(r.entity_id, 1.0) * (1 + r.magnitude / 100.0)
        elif t == "warehouse_disruption":
            e.warehouse_down.add(r.entity_id)
        elif t == "transport_disruption":
            e.transport_cost_mult *= r.magnitude
            e.transit_mult *= max(1.0, r.magnitude * 0.5 + 0.5)
        elif t == "partial_delivery":
            e.partial_fill[r.entity_id] = min(e.partial_fill.get(r.entity_id, 1.0), r.magnitude)
    e.labels = [f"[SIMULATED] {r.event_type} {r.entity_id}" for r in ev.itertuples()]
    return e


def merge(a, b):
    """Combine two Effects (b layered on a)."""
    m = Effects()
    m.supplier_delay = dict(a.supplier_delay)
    for k, v in b.supplier_delay.items():
        m.supplier_delay[k] = m.supplier_delay.get(k, 0) + v
    m.demand_mult = dict(a.demand_mult)
    for k, v in b.demand_mult.items():
        m.demand_mult[k] = m.demand_mult.get(k, 1.0) * v
    m.warehouse_down = set(a.warehouse_down) | set(b.warehouse_down)
    m.transport_cost_mult = a.transport_cost_mult * b.transport_cost_mult
    m.transit_mult = a.transit_mult * b.transit_mult
    m.partial_fill = {**a.partial_fill, **b.partial_fill}
    m.labels = a.labels + b.labels
    return m

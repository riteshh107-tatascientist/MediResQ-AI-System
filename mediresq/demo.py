"""One-click end-to-end demo: 7-day supplier delay -> hospital shortage -> optimizer -> pending approval."""
from . import logistics, recovery, simulator
from .effects import from_events


def run_demo(db, as_of, actor="demo"):
    eid = logistics.inject_event(db, "supplier_delay", "S-03", 7, as_of, 14, actor,
                                 "Demo: Nova Generic Healthcare 7-day delay (Ceftriaxone inbound to Civil Hospital Beta)", detected_after_days=0)
    eff = from_events(db, as_of)
    sim = simulator.run(db, as_of, eff, horizon=30)
    rec = recovery.generate(db, as_of, eff, persist=True, tag="demo")
    return {"event_id": eid, "effects": eff, "simulation": sim, "recovery": rec}

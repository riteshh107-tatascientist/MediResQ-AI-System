"""Shipment tracking, disruption injection (always labelled simulated) and detection-time metrics."""
from datetime import date, timedelta
import pandas as pd

EVENT_TYPES = ["supplier_delay", "demand_surge", "warehouse_disruption", "transport_disruption", "partial_delivery"]


def _d(x):
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def shipments_status(db, as_of, effects=None):
    s = db.df("""SELECT sh.*, f.name AS destination, m.name AS medicine, su.name AS supplier
                 FROM shipments sh JOIN facilities f ON f.facility_id=sh.dest_facility_id
                 JOIN medicines m USING(medicine_id) LEFT JOIN suppliers su ON su.supplier_id=sh.supplier_id""")
    a = pd.Timestamp(_d(as_of))
    s["expected"] = pd.to_datetime(s.expected_arrival)
    extra = s.supplier_id.map(lambda x: (effects.supplier_delay.get(x, 0) if effects else 0)).astype(float)
    s["effective_expected"] = s.expected + pd.to_timedelta(extra, unit="D")
    act = pd.to_datetime(s.actual_arrival)
    s["delay_days"] = (act - s.expected).dt.days.clip(lower=0)
    t = s.status == "In Transit"
    s.loc[t, "delay_days"] = (a - s.effective_expected[t]).dt.days.clip(lower=0) + extra[t]
    s["transport_status"] = "Delivered"
    s.loc[t, "transport_status"] = "In Transit"
    s.loc[t & (s.delay_days > 0), "transport_status"] = "Delayed"
    s["origin_label"] = s.origin
    return s


def inject_event(db, event_type, entity_id, magnitude, as_of, duration_days, actor, description="", detected_after_days=0):
    if event_type not in EVENT_TYPES:
        raise ValueError("Unknown event type")
    if event_type == "partial_delivery" and not (0 < magnitude <= 1):
        raise ValueError("Partial delivery fraction must be in (0,1].")
    if duration_days < 1 or duration_days > 90:
        raise ValueError("Duration must be 1-90 days")
    start = _d(as_of)
    eid = db.execute("""INSERT INTO disruption_events(event_type,entity_id,magnitude,start_date,end_date,detected_date,description,simulated,created_by,active)
                        VALUES(?,?,?,?,?,?,?,1,?,1)""",
                     (event_type, entity_id, float(magnitude), str(start), str(start + timedelta(days=duration_days)),
                      str(start + timedelta(days=detected_after_days)), "SIMULATED: " + (description or event_type), actor))
    db.audit(actor, "inject_event", "disruption", eid, f"{event_type} {entity_id} mag={magnitude} (simulated)")
    return eid


def clear_event(db, event_id, actor):
    db.execute("UPDATE disruption_events SET active=0 WHERE event_id=?", (int(event_id),))
    db.audit(actor, "clear_event", "disruption", event_id)


def events(db):
    return db.df("SELECT * FROM disruption_events ORDER BY start_date DESC")


def detection_time_stats(db):
    e = events(db)
    if e.empty:
        return {"events": 0, "mean_detection_days": None}
    d = (pd.to_datetime(e.detected_date) - pd.to_datetime(e.start_date)).dt.days
    return {"events": len(e), "mean_detection_days": float(d.mean()), "max_detection_days": float(d.max())}

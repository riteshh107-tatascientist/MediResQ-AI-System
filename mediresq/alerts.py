"""Alert centre: every alert is derived from data and carries a reason + recommended action."""
import hashlib
from datetime import date, datetime, timedelta
import pandas as pd

from . import expiry, inventory, logistics, stockout
from .state import State


def _key(*p):
    return hashlib.md5("|".join(map(str, p)).encode()).hexdigest()[:12]


def build(db, as_of, effects=None, state=None, so=None):
    st = state or State(db, as_of, effects)
    so = so if so is not None else stockout.compute(db, as_of, state=st)
    ts = datetime.combine(st.as_of, datetime.min.time()).isoformat(timespec="minutes")
    A = []

    def add(t, sev, fac, med, reason, action, ref=""):
        A.append({"alert_key": _key(t, fac, med, ref), "type": t, "severity": sev, "facility": fac, "medicine": med,
                  "timestamp": ts, "reason": reason, "recommended_action": action})

    summ = inventory.stock_summary(db, as_of)
    for r in summ[(summ.status == "Critical") & (summ.type == "hospital")].itertuples():
        add("Critical Stock", "Critical", r.facility, r.medicine,
            f"usable stock {r.usable_qty:.0f} <= safety stock {r.safety_stock:.0f} ({r.days_of_cover:.1f} days cover)",
            "Request transfer from surplus site or expedite replenishment", "cs")
    for r in so[so.risk_level.isin(["Critical", "High"])].itertuples():
        add("Predicted Stockout", r.risk_level, r.facility, r.medicine,
            f"{r.reason} (heuristic risk {r.risk_score}; model P={r.p_stockout_lt_model:.2f})",
            "Generate recovery plan and review in Approval Centre", "ps")
    w = expiry.wastage_risk(db, as_of)
    for r in w[(w.days_to_expiry <= 30) & (w.projected_waste_qty > 0) & (w.qty > 0)].itertuples():
        exp_ = "expired" if r.days_to_expiry <= 0 else f"expires in {r.days_to_expiry}d"
        add("Expiry Risk", "Critical" if r.days_to_expiry <= 0 else "High", r.facility, r.medicine,
            f"batch {r.batch_no} {exp_}; projected waste {r.projected_waste_qty:.0f} units (INR {r.projected_waste_inr:,.0f})",
            "Quarantine/dispose if expired; otherwise redistribute under FEFO", r.batch_no)
    sh = logistics.shipments_status(db, as_of, st.effects)
    for r in sh[sh.transport_status == "Delayed"].itertuples():
        add("Shipment Disruption", "High" if r.delay_days >= 3 else "Medium", r.destination, r.medicine,
            f"shipment {r.shipment_id} from {r.supplier} delayed {r.delay_days:.0f} day(s)",
            "Contact supplier; check alternative sources", r.shipment_id)
    po = db.df("""SELECT p.*, s.name AS supplier, m.name AS medicine, f.name AS facility FROM purchase_orders p
                  JOIN suppliers s USING(supplier_id) JOIN medicines m USING(medicine_id)
                  JOIN facilities f ON f.facility_id=p.dest_facility_id WHERE p.status='Open' AND p.promised_date<?""", (str(st.as_of),))
    for r in po.itertuples():
        add("Supplier Delay", "Medium", r.facility, r.medicine,
            f"PO {r.po_id} past promised date {r.promised_date} ({r.supplier})", "Escalate with supplier; consider alternate supplier", r.po_id)
    for s, d in st.effects.supplier_delay.items():
        add("Supplier Delay", "High", "Network", f"all medicines from {s}", f"[SIMULATED] active supplier delay +{d:g} days",
            "Review Recovery Planner", s)
    for r in summ[(summ.type == "hospital") & (summ.days_of_cover > 60) & (summ.usable_qty > summ.max_stock * 1.25)].itertuples():
        add("Overstock", "Low", r.facility, r.medicine, f"{r.days_of_cover:.0f} days of cover vs max level {r.max_stock:.0f}",
            "Offer surplus to other facilities; pause replenishment", "os")
    un = db.df("""SELECT c.facility_id, c.medicine_id, SUM(unmet_qty) u, MAX(date) d FROM consumption c WHERE unmet_qty>0 AND date>=?
                  GROUP BY c.facility_id, c.medicine_id""", (str(st.as_of - timedelta(days=14)),))
    for r in un.itertuples():
        add("Unfulfilled Demand", "High", st.fac.loc[r.facility_id, "name"], st.med.loc[r.medicine_id, "name"],
            f"{r.u:.0f} units of demand unmet in last 14 days (latest {r.d})", "Investigate cause; replenish", "ud")
    df = pd.DataFrame(A)
    if df.empty:
        return df
    stt = db.df("SELECT alert_key, status, updated_by, updated_at FROM alert_status")
    df = df.merge(stt, on="alert_key", how="left")
    df["status"] = df.status.fillna("Open")
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return df.sort_values("severity", key=lambda s: s.map(order)).reset_index(drop=True)


def set_status(db, alert_key, status, user, note=""):
    if status not in ("Open", "Acknowledged", "Resolved"):
        raise ValueError("Invalid status")
    db.execute("INSERT OR REPLACE INTO alert_status(alert_key,status,updated_by,updated_at,note) VALUES(?,?,?,?,?)",
               (alert_key, status, user["username"], datetime.now().isoformat(timespec="seconds"), note))
    db.audit(user["username"], f"alert_{status.lower()}", "alert", alert_key, note)

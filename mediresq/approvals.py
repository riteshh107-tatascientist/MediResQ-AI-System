"""Human-in-the-loop approval workflow with audit trail. Nothing is procured or moved without approval."""
from datetime import date, datetime, timedelta
import math
import pandas as pd

from . import auth, config, inventory

NEED = {"TRANSFER": "approve_transfer", "PROCURE": "approve_procure"}


def pending(db):
    return db.df("""SELECT r.*, m.name AS medicine FROM recommendations r JOIN medicines m USING(medicine_id)
                    ORDER BY CASE status WHEN 'Pending' THEN 0 ELSE 1 END, priority_score DESC, rec_id DESC""")


def decide(db, rec_id, user, decision, comment="", final_qty=None):
    if decision not in ("Approved", "Rejected", "Modified"):
        raise ValueError("Decision must be Approved, Rejected or Modified.")
    r = db.df("SELECT * FROM recommendations WHERE rec_id=?", (int(rec_id),))
    if r.empty:
        raise ValueError("Recommendation not found.")
    r = r.iloc[0]
    if not auth.can(user, NEED[r.rec_type]):
        raise PermissionError(f"Role '{user['role']}' may not decide {r.rec_type} recommendations.")
    if r.status != "Pending":
        raise ValueError(f"Recommendation already {r.status}.")
    if decision in ("Rejected", "Modified") and not (comment or "").strip():
        raise ValueError("A comment is required when rejecting or modifying.")
    fq = int(r.qty)
    if decision == "Modified":
        if final_qty is None or int(final_qty) <= 0:
            raise ValueError("Modified quantity must be a positive integer.")
        if int(final_qty) > int(r.qty) * 2:
            raise ValueError("Modified quantity may not exceed 2x the recommendation.")
        fq = int(final_qty)
    db.execute("UPDATE recommendations SET status=?, decided_by=?, decided_at=?, comment=?, final_qty=? WHERE rec_id=?",
               (decision, user["username"], datetime.now().isoformat(timespec="seconds"), comment, fq, int(rec_id)))
    db.audit(user["username"], f"recommendation_{decision.lower()}", "recommendation", rec_id,
             f"qty {r.qty}->{fq}; comment={comment}")


def execute(db, rec_id, user, as_of):
    """Executes an APPROVED/MODIFIED recommendation. TRANSFER: moves FEFO batches (booked on execution - transit time
    is not modelled in the DB). PROCURE: creates an open purchase order + in-transit shipment."""
    r = db.df("SELECT * FROM recommendations WHERE rec_id=?", (int(rec_id),))
    if r.empty:
        raise ValueError("Recommendation not found.")
    r = r.iloc[0]
    if not auth.can(user, NEED[r.rec_type]):
        raise PermissionError("Not permitted.")
    if r.status not in ("Approved", "Modified"):
        raise ValueError("Only approved or modified recommendations can be executed.")
    qty = int(r.final_qty or r.qty)
    as_of = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
    if r.rec_type == "TRANSFER":
        eta = (r.eta_hours or 0) / 24
        b = inventory.usable_batches(db, as_of)
        b = b[(b.facility_id == r.source_id) & (b.medicine_id == r.medicine_id) & b.usable & (b.qty > 0)
              & (b.days_to_expiry - eta >= config.MIN_SHELF_AFTER_ARRIVAL)].sort_values("expiry_date")
        if b.qty.sum() < qty:
            raise ValueError("Source no longer holds enough eligible (non-expired, active, shelf-life safe) stock.")
        left = qty
        with db.tx() as c:
            for x in b.itertuples():
                take = min(int(x.qty), left)
                if take <= 0:
                    break
                c.execute("UPDATE batches SET qty=qty-? WHERE batch_id=?", (take, int(x.batch_id)))
                cur = c.execute("SELECT batch_id FROM batches WHERE facility_id=? AND medicine_id=? AND batch_no=?",
                                (r.dest_id, r.medicine_id, x.batch_no)).fetchone()
                if cur:
                    c.execute("UPDATE batches SET qty=qty+? WHERE batch_id=?", (take, cur[0]))
                    nb = cur[0]
                else:
                    nb = c.execute("INSERT INTO batches(facility_id,medicine_id,batch_no,mfg_date,expiry_date,qty,status,unit_cost) VALUES(?,?,?,?,?,?,?,?)",
                                   (r.dest_id, r.medicine_id, x.batch_no, x.mfg_date, x.expiry_date, take, "active", x.unit_cost)).lastrowid
                for fid, bid, mt, q in ((r.source_id, int(x.batch_id), "transfer_out", -take), (r.dest_id, nb, "transfer_in", take)):
                    c.execute("INSERT INTO stock_movements(date,facility_id,medicine_id,batch_id,movement_type,qty,reference) VALUES(?,?,?,?,?,?,?)",
                              (str(as_of), fid, r.medicine_id, bid, mt, q, f"REC-{rec_id}"))
                left -= take
    else:
        sup = r.supplier_id
        lead = db.scalar("SELECT std_lead_days FROM supplier_catalog WHERE supplier_id=? AND medicine_id=?", (sup, r.medicine_id)) or 7
        po = f"PO-R{int(rec_id):04d}"
        db.execute("INSERT INTO purchase_orders(po_id,supplier_id,medicine_id,dest_facility_id,qty,order_date,promised_date,status) VALUES(?,?,?,?,?,?,?,'Open')",
                   (po, sup, r.medicine_id, r.dest_id, qty, str(as_of), str(as_of + timedelta(days=int(lead)))))
        db.execute("INSERT INTO shipments(shipment_id,po_id,supplier_id,origin,dest_facility_id,medicine_id,qty,ship_date,expected_arrival,status,simulated) VALUES(?,?,?,?,?,?,?,?,?,'In Transit',1)",
                   (f"SH-R{int(rec_id):04d}", po, sup, sup, r.dest_id, r.medicine_id, qty, str(as_of), str(as_of + timedelta(days=int(lead)))))
    db.execute("UPDATE recommendations SET status='Executed' WHERE rec_id=?", (int(rec_id),))
    db.audit(user["username"], "recommendation_executed", "recommendation", rec_id, f"{r.rec_type} qty={qty}")


def audit_history(db, limit=500):
    return db.df("SELECT * FROM audit_log ORDER BY audit_id DESC LIMIT ?", (limit,))

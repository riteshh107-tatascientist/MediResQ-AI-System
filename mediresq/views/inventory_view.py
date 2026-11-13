import pandas as pd

from .. import inventory, ui


def render(c):
    st, db = c.st, c.db
    st.markdown(ui.hero_app("Medicine Inventory", desc="Stock monitoring, policies and master data."), unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["Stock monitor", "Medicine master (CRUD)", "Batches & movements"])
    with t1:
        s = inventory.stock_summary(db, c.as_of)
        f1, f2, f3 = st.columns(3)
        fac = f1.multiselect("Facility", sorted(s.facility.unique()))
        q = f2.text_input("Search medicine", "")
        stt = f3.multiselect("Status", ["Critical", "Reorder", "OK", "Overstock"])
        if fac:
            s = s[s.facility.isin(fac)]
        if q:
            s = s[s.medicine.str.contains(q, case=False, na=False)]
        if stt:
            s = s[s.status.isin(stt)]
        cols = ["facility", "medicine", "usable_qty", "total_qty", "min_stock", "max_stock", "safety_stock", "reorder_point",
                "avg_daily_consumption", "days_of_cover", "value_inr", "status"]
        st.dataframe(s[cols].round(1), use_container_width=True, hide_index=True)
        st.caption("Usable = active (not quarantined) and not expired. Value shown only where unit cost exists. Policies are computed from the last 56 days of consumption and historical lead times.")
        st.download_button("Download CSV", s[cols].to_csv(index=False), "stock_monitor.csv", "text/csv")
        mv = db.df("SELECT date, facility_id, medicine_id, movement_type, qty, reference FROM stock_movements ORDER BY movement_id DESC LIMIT 200")
        with st.expander("Recent inventory movements"):
            st.dataframe(mv, use_container_width=True, hide_index=True)
    with t2:
        med = db.df("SELECT * FROM medicines ORDER BY medicine_id")
        st.dataframe(med, use_container_width=True, hide_index=True)
        if not c.can("edit_inventory"):
            st.info("Your role is read-only for inventory.")
        else:
            with st.expander("Add medicine"):
                with st.form("addmed"):
                    a, b = st.columns(2)
                    mid = a.text_input("Medicine ID (e.g. M21)")
                    name = b.text_input("Name")
                    form = a.text_input("Form")
                    cat = b.text_input("Category")
                    cost = a.number_input("Unit cost (INR)", min_value=0.0, value=1.0)
                    crit = b.selectbox("Criticality (3 = life-saving)", [1, 2, 3], index=1)
                    shelf = a.number_input("Shelf life (days)", min_value=1, value=730)
                    cold = b.checkbox("Cold chain")
                    if st.form_submit_button("Add"):
                        try:
                            inventory.add_medicine(db, mid, name, form, cat, cost, crit, int(shelf), int(cold), c.user["username"])
                            inventory.compute_policies(db, c.as_of)
                            c.bump()
                            st.success("Medicine added.")
                        except Exception as e:
                            st.error(f"Could not add: {e}")
            with st.expander("Edit medicine"):
                ids = med.medicine_id.tolist()
                sel = st.selectbox("Medicine", ids, key="editmed")
                row = med[med.medicine_id == sel].iloc[0] if sel else None
                if row is not None:
                    with st.form("editmedf"):
                        name = st.text_input("Name", row["name"])
                        cost = st.number_input("Unit cost (INR)", min_value=0.0, value=float(row.unit_cost or 0))
                        crit = st.selectbox("Criticality", [1, 2, 3], index=int(row.criticality) - 1)
                        if st.form_submit_button("Save changes"):
                            try:
                                inventory.update_medicine(db, sel, c.user["username"], name=name, unit_cost=cost, criticality=crit)
                                c.bump()
                                st.success("Updated.")
                            except Exception as e:
                                st.error(f"Could not update: {e}")
            if c.can("delete_inventory"):
                with st.expander("Delete medicine (administrator)"):
                    did = st.selectbox("Medicine to delete", med.medicine_id.tolist(), key="delmed")
                    if st.button("Delete", key="delbtn"):
                        try:
                            inventory.delete_medicine(db, did, c.user["username"])
                            c.bump()
                            st.success("Deleted.")
                        except Exception as e:
                            st.error(str(e))
    with t3:
        b = db.df("SELECT b.batch_id, b.facility_id, b.medicine_id, b.batch_no, b.expiry_date, b.qty, b.status FROM batches b ORDER BY b.batch_id DESC LIMIT 300")
        st.dataframe(b, use_container_width=True, hide_index=True)
        if c.can("edit_inventory"):
            with st.form("addbatch"):
                a, bb = st.columns(2)
                fac = a.selectbox("Facility", db.df("SELECT facility_id FROM facilities").facility_id.tolist())
                med = bb.selectbox("Medicine", db.df("SELECT medicine_id FROM medicines").medicine_id.tolist())
                bn = a.text_input("Batch no")
                mfg = bb.date_input("Manufacture date", value=c.as_of.replace(year=c.as_of.year - 1))
                exp = a.date_input("Expiry date", value=c.as_of.replace(year=c.as_of.year + 1))
                qty = bb.number_input("Quantity", min_value=0, value=100)
                if st.form_submit_button("Add batch"):
                    try:
                        inventory.add_batch(db, fac, med, bn, mfg, exp, int(qty), db.scalar("SELECT unit_cost FROM medicines WHERE medicine_id=?", (med,)), actor=c.user["username"])
                        c.bump()
                        st.success("Batch added.")
                    except Exception as e:
                        st.error(f"Could not add batch: {e}")
            with st.form("adjust"):
                bid = st.number_input("Batch ID to adjust", min_value=1, value=1)
                dl = st.number_input("Quantity change (+/-)", value=0)
                rs = st.text_input("Reason")
                if st.form_submit_button("Apply adjustment"):
                    try:
                        inventory.adjust_batch(db, int(bid), int(dl), rs or "manual", c.user["username"], c.as_of)
                        c.bump()
                        st.success("Adjusted.")
                    except Exception as e:
                        st.error(str(e))

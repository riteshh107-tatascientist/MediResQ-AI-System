from .. import alerts, approvals, ui


def render(c):
    st, db = c.st, c.db
    st.markdown(ui.hero_app("Alert Centre & Approvals", desc="Explainable alerts and human-in-the-loop decisions with a full audit trail."), unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["Alert centre", "Approval centre", "Audit history"])
    with t1:
        al = c.kpis()["_alerts"]
        if al.empty:
            st.success("No alerts.")
        else:
            f1, f2, f3 = st.columns(3)
            ty = f1.multiselect("Type", sorted(al.type.unique()))
            sv = f2.multiselect("Severity", ["Critical", "High", "Medium", "Low"])
            ss = f3.multiselect("Status", ["Open", "Acknowledged", "Resolved"], default=["Open", "Acknowledged"])
            d = al
            if ty: d = d[d.type.isin(ty)]
            if sv: d = d[d.severity.isin(sv)]
            if ss: d = d[d.status.isin(ss)]
            st.dataframe(d[["severity", "type", "status", "timestamp", "facility", "medicine", "reason", "recommended_action", "alert_key"]], use_container_width=True, hide_index=True)
            if c.can("ack_alerts") and len(d):
                k = st.selectbox("Alert key", d.alert_key.tolist())
                note = st.text_input("Note")
                x, y = st.columns(2)
                if x.button("Acknowledge"):
                    alerts.set_status(db, k, "Acknowledged", c.user, note); c.bump(); st.success("Acknowledged")
                if y.button("Resolve"):
                    alerts.set_status(db, k, "Resolved", c.user, note); c.bump(); st.success("Resolved")
    with t2:
        p = approvals.pending(db)
        st.dataframe(p[["rec_id", "status", "rec_type", "medicine", "source_id", "dest_id", "supplier_id", "qty", "final_qty", "est_cost", "eta_hours",
                        "priority_score", "decided_by", "decided_at", "comment", "reasoning"]], use_container_width=True, hide_index=True)
        pend = p[p.status == "Pending"]
        if len(pend):
            rid = st.selectbox("Pending recommendation", pend.rec_id.tolist())
            row = pend[pend.rec_id == rid].iloc[0]
            st.markdown(f"**{row.rec_type}** {row.qty} x {row.medicine} -> {row.dest_id}  \n{row.reasoning}")
            comment = st.text_area("Comment (required to reject/modify)")
            mq = st.number_input("Modified quantity", min_value=1, value=int(row.qty))
            a, b, d = st.columns(3)
            for col, label, dec in ((a, "Approve", "Approved"), (b, "Reject", "Rejected"), (d, "Modify & approve", "Modified")):
                if col.button(label, key=f"dec_{dec}"):
                    try:
                        approvals.decide(db, rid, c.user, dec, comment, mq if dec == "Modified" else None)
                        c.bump()
                        st.success(f"{dec}.")
                    except Exception as e:
                        st.error(str(e))
        ready = p[p.status.isin(["Approved", "Modified"])]
        if len(ready):
            xid = st.selectbox("Approved item to execute", ready.rec_id.tolist(), key="execsel")
            if st.button("Execute approved action"):
                try:
                    approvals.execute(db, xid, c.user, c.as_of)
                    c.bump()
                    st.success("Executed and logged.")
                except Exception as e:
                    st.error(str(e))
    with t3:
        st.dataframe(approvals.audit_history(db), use_container_width=True, hide_index=True)

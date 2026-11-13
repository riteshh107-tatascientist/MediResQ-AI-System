import plotly.express as px

from .. import logistics, ui


def render(c):
    st, db = c.st, c.db
    st.markdown(ui.hero_app("Supplier & Logistics Monitoring", desc="Reliability, shipments and labelled disruption simulation."), unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["Supplier intelligence", "Shipments", "Disruptions (simulated)"])
    k = c.kpis()
    with t1:
        sm = k["_suppliers"]
        st.dataframe(sm[["supplier_id", "supplier", "orders", "on_time_rate", "delay_freq", "avg_delay_days", "avg_lead_time", "lt_cv",
                         "fulfilment_rate", "reliability_score", "risk", "open_pos", "overdue_pos"]].round(2), use_container_width=True, hide_index=True)
        st.caption("Reliability = 100 x (0.5 on-time + 0.3 fulfilment + 0.2 lead-time consistency). Risk: <70 High, <82 Medium, else Low. Derived from synthetic PO history.")
        st.plotly_chart(ui.style(px.scatter(sm, x="avg_delay_days", y="fulfilment_rate", size="orders", color="risk", hover_name="supplier",
                                            color_discrete_map={"High": ui.RED, "Medium": ui.AMBER, "Low": ui.GREEN}, title="Delay vs fulfilment")), use_container_width=True)
    with t2:
        sh = k["_shipments"]
        s = st.multiselect("Transport status", ["In Transit", "Delayed", "Delivered"], default=["In Transit", "Delayed"])
        d = sh[sh.transport_status.isin(s)] if s else sh
        st.dataframe(d[["shipment_id", "supplier", "origin", "destination", "medicine", "qty", "ship_date", "expected_arrival", "actual_arrival",
                        "transport_status", "delay_days", "simulated"]].head(400), use_container_width=True, hide_index=True)
    with t3:
        st.markdown(ui.sim_badge() + " Events injected here are simulated and clearly labelled; they never overwrite real records.", unsafe_allow_html=True)
        if c.can("inject_events"):
            with st.form("inj"):
                a, b = st.columns(2)
                et = a.selectbox("Event type", logistics.EVENT_TYPES)
                ent = b.text_input("Entity (supplier S-03 / medicine M10 or ALL / warehouse WH-01 / ALL)", "S-03")
                mag = a.number_input("Magnitude (delay days | demand +% | cost multiplier | delivered fraction 0-1)", value=7.0)
                dur = b.number_input("Duration (days)", min_value=1, max_value=90, value=14)
                if st.form_submit_button("Inject simulated event"):
                    try:
                        logistics.inject_event(db, et, ent.strip(), float(mag), c.as_of, int(dur), c.user["username"], et)
                        c.bump()
                        st.success("Simulated event injected.")
                    except Exception as e:
                        st.error(str(e))
            ev = logistics.events(db)
            st.dataframe(ev, use_container_width=True, hide_index=True)
            cid = st.number_input("Event ID to clear", min_value=0, value=0)
            if st.button("Clear event") and cid:
                logistics.clear_event(db, int(cid), c.user["username"]); c.bump(); st.success("Cleared")
        else:
            st.dataframe(logistics.events(db), use_container_width=True, hide_index=True)
        ds = logistics.detection_time_stats(db)
        st.write(f"Disruption detection time (simulated events): mean {ds.get('mean_detection_days')} day(s) over {ds['events']} event(s).")

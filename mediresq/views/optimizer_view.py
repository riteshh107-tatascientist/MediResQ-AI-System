import plotly.graph_objects as go

from .. import demo, effects as fx, logistics, optimizer, recovery, simulator, ui


def _plan_block(st, res):
    s = res["summary"]
    st.write(f"Solver: **{s.get('backend')}** | status: **{s.get('status')}** | shortage {s.get('shortage_units', 0)} units | "
             f"covered {s.get('covered_units', 0)} | unmet {s.get('unmet_units', 0)} | transport cost INR {s.get('total_cost', 0):,.0f}")
    if len(res["plan"]):
        st.dataframe(res["plan"][["medicine", "source", "destination", "qty", "est_cost_inr", "eta_hours", "timely", "batches_fefo", "reasoning"]],
                     use_container_width=True, hide_index=True)
    for n in res["notes"]:
        st.info(n)
    if len(res["unmet"]):
        st.warning("Shortages the optimizer could not fully cover, and why:")
        st.dataframe(res["unmet"], use_container_width=True, hide_index=True)


def render(c):
    st, db = c.st, c.db
    st.markdown(ui.hero_app("Optimization & Recovery", desc="Redistribution optimizer, recovery planner, what-if simulator."), unsafe_allow_html=True)
    t1, t2, t3, t4 = st.tabs(["Redistribution optimizer", "AI recovery planner", "What-if simulator", "Judge demo"])
    with t1:
        st.write("Minimises transport cost + penalty on critical unmet demand, subject to reserves, expiry/quarantine, cold-chain, lane capacity and timing.")
        if st.button("Run optimizer on current state", key="runopt"):
            res = optimizer.build_plan(db, c.as_of, c.eff)
            _plan_block(st, res)
    with t2:
        st.write("Combines forecast, stock-out risk, supplier reliability, disruptions and the optimizer. Actions are saved as **Pending** - nothing executes without approval.")
        if c.can("run_plan"):
            if st.button("Generate recovery plan", key="genplan"):
                out = recovery.generate(db, c.as_of, c.eff, persist=True, tag="manual")
                c.bump()
                st.success(f"{len(out['actions'])} prioritised actions generated (duplicates of pending items skipped).")
                if len(out["actions"]):
                    st.dataframe(out["actions"][["rec_type", "medicine", "source_id", "dest_id", "supplier_id", "qty", "est_cost", "eta_hours", "priority_score", "reasoning"]],
                                 use_container_width=True, hide_index=True)
        else:
            st.info("Your role cannot generate plans.")
    with t3:
        st.markdown(ui.sim_badge() + " Deterministic projection from forecasts; standing reorder policy applied in all three scenarios.", unsafe_allow_html=True)
        a, b = st.columns(2)
        delay = a.selectbox("Supplier delay (days)", [0, 1, 3, 5, 7])
        sup = b.selectbox("Delayed supplier", ["S-03", "S-01", "S-02", "S-04", "S-05", "S-06", "S-07"])
        surge = a.selectbox("Demand increase", ["0%", "10%", "20%", "30%", "Custom"])
        cust = b.number_input("Custom demand increase (%)", min_value=0, max_value=200, value=15)
        wh = a.multiselect("Warehouse disruption", ["WH-01", "WH-02", "WH-03"])
        tc = b.slider("Transport cost multiplier", 0.5, 3.0, 1.0, 0.1)
        part = a.slider("Partial delivery fraction (delayed supplier)", 0.3, 1.0, 1.0, 0.05)
        horizon = b.selectbox("Horizon (days)", [14, 30], index=1)
        pct = cust if surge == "Custom" else int(surge.rstrip("%"))
        e = fx.Effects(supplier_delay={sup: delay} if delay else {}, demand_mult={"ALL": 1 + pct / 100} if pct else {}, warehouse_down=set(wh),
                       transport_cost_mult=tc, partial_fill={sup: part} if part < 1 else {})
        e = fx.merge(c.eff, e)
        if st.button("Run scenario", key="runsim"):
            with st.spinner("Simulating..."):
                r = simulator.run(db, c.as_of, e, horizon=horizon)
            st.write("Scenario:", "; ".join(e.describe()) or "no disruption")
            st.dataframe(r["summary"], use_container_width=True, hide_index=True)
            meds = db.df("SELECT medicine_id, name FROM medicines")
            mid = st.selectbox("Inventory curve for medicine", meds.medicine_id.tolist(), index=3, format_func=lambda x: meds.set_index("medicine_id").name[x])
            cur = simulator.stock_curves(r["states"], mid)
            fig = go.Figure()
            for nm, col in (("Baseline", ui.GREEN), ("Disrupted", ui.RED), ("Recovered", ui.BLUE)):
                fig.add_scatter(x=cur.date, y=cur[nm], name=nm, line=dict(color=col))
            fig.update_layout(title="Projected hospital inventory (units) - SIMULATED")
            st.plotly_chart(ui.style(fig), use_container_width=True)
            _plan_block(st, r["optimizer"])
            st.dataframe(r["detail"].sort_values("unmet_disrupted", ascending=False).head(25).round(1), use_container_width=True, hide_index=True)
    with t4:
        st.write("One click runs the full story: **7-day delay at supplier S-03 -> Civil Hospital Beta (H-02) Ceftriaxone shortage -> surplus at H-05/warehouses -> feasible redistribution -> human approval.**")
        if c.can("inject_events") and c.can("run_plan"):
            if st.button("Run end-to-end demo scenario", type="primary", key="demo"):
                d = demo.run_demo(db, c.as_of, c.user["username"])
                c.bump()
                st.success("Simulated 7-day supplier delay injected; recovery plan generated and queued for approval (Approval Centre).")
                s = d["simulation"]["summary"]
                st.dataframe(s, use_container_width=True, hide_index=True)
                cef = d["recovery"]["optimizer"]
                _plan_block(st, cef)
        else:
            st.info("Requires a Supply Chain Manager or Administrator login.")

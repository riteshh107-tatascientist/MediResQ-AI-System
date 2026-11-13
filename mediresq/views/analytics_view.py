import pandas as pd
import plotly.express as px

from .. import analytics, assistant, forecasting, ui


def render(c):
    st, db = c.st, c.db
    st.markdown(ui.hero_app("Advanced Analytics & Assistant", desc="Measured metrics, controlled policy simulation and a data-grounded assistant."), unsafe_allow_html=True)
    t1, t2, t3, t4 = st.tabs(["Operational metrics", "Policy comparison (simulated)", "Model benchmark", "Intelligence assistant"])
    with t1:
        m = analytics.historical_metrics(db, c.as_of)
        r = pd.DataFrame({"metric": list(m.keys())[:-1], "value": list(m.values())[:-1]})
        st.dataframe(r, use_container_width=True, hide_index=True)
        st.write("Disruption detection:", m["detection"])
        st.caption("Computed from synthetic records. Fulfilment/availability reflect the data generator, not real facilities.")
    with t2:
        st.markdown(ui.sim_badge(), unsafe_allow_html=True)
        st.write("A = static min/max (no safety stock, no adaptation, no transfers) vs B = adaptive reorder points + safety stock + hospital balancing. Common random numbers, bootstrapped demand and lead times, supplier shock on 5 medicines.")
        runs = st.slider("Monte-Carlo runs", 5, 40, 20)
        if st.button("Run controlled simulation"):
            with st.spinner("Simulating..."):
                out = analytics.policy_comparison(db, c.as_of, n_runs=runs)
            st.dataframe(out.reset_index(names="policy"), use_container_width=True, hide_index=True)
            st.warning("Policy B improves service level but carries higher inventory and transfer cost - a trade-off, not a free win. These are simulation results on synthetic data, not hospital outcomes.")
    with t3:
        st.write("Benchmarks every model on the network-level demand of each medicine (chronological hold-out). Takes ~1-2 minutes.")
        if st.button("Run benchmark for all medicines"):
            rows = []
            for mid in db.df("SELECT medicine_id FROM medicines").medicine_id:
                s, _ = forecasting.clean_series(forecasting.load_series(db, "ALL", mid, c.as_of))
                t = forecasting.evaluate_series(s)["table"]
                rows.append(t[t.split == "test"].assign(medicine_id=mid))
            allr = pd.concat(rows)
            agg = allr.groupby("model")[["MAE", "RMSE", "WAPE"]].median().round(3).reset_index()
            st.dataframe(agg, use_container_width=True, hide_index=True)
            st.plotly_chart(ui.style(px.box(allr, x="model", y="WAPE", title="Test WAPE across medicines")), use_container_width=True)
    with t4:
        q = st.text_input("Ask about your supply chain (e.g. 'Which medicines have critical stock?')")
        for ex in ["Which medicines have critical stock?", "Which facility is at greatest risk?", "What batches expire next month?",
                   "Which supplier has the highest delay?", "Explain the latest recovery recommendation"]:
            st.caption("e.g. " + ex)
        if q:
            txt, df = assistant.answer(db, c.as_of, q, c.kpis())
            st.markdown(f"**{txt}**")
            if df is not None:
                st.dataframe(df, use_container_width=True, hide_index=True)

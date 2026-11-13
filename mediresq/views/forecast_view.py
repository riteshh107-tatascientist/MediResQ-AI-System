import pandas as pd
import plotly.graph_objects as go

from .. import forecasting, ui


def render(c):
    st, db = c.st, c.db
    st.markdown(ui.hero_app("AI Demand Forecasting", desc="Real models, chronological evaluation, honest metrics."), unsafe_allow_html=True)
    fac = st.selectbox("Scope", ["ALL"] + db.df("SELECT facility_id FROM facilities WHERE type='hospital'").facility_id.tolist())
    meds = db.df("SELECT medicine_id, name FROM medicines")
    mid = st.selectbox("Medicine", meds.medicine_id.tolist(), format_func=lambda x: meds.set_index("medicine_id").name[x])
    with st.spinner("Running models (cached after first run)..."):
        r = forecasting.run_forecast(db, fac, mid, c.as_of)
    ev, fc, info = r["eval"], r["forecast"], r["info"]
    st.markdown(f"**Data prep:** {info['missing']} missing day(s) imputed (same-weekday median), {info['zero_days']} true zero-demand day(s) kept, {info['outliers_capped']} outlier(s) capped (Q3+3xIQR).")
    t = ev["table"]
    test = t[t.split == "test"].drop(columns="split").round(3)
    val = t[t.split == "validation"].set_index("model").WAPE.round(3)
    st.markdown(f"**Selected model (lowest validation WAPE): {ev['best_model']}** - test-set improvement vs best baseline: "
                f"**{ev['improvement_vs_best_baseline_pct']:.1f}%** (negative = worse than baseline).")
    st.dataframe(test.assign(validation_WAPE=test.model.map(val)), use_container_width=True, hide_index=True)
    st.caption("Split: train -> validation (last 60..30 days, selection) -> test (last 30 days, reporting). Metrics are computed from real hold-out forecasts. WAPE = sum|error| / sum(actual). Data are synthetic, so scores describe the generator, not real hospitals.")
    c1, c2 = st.columns(2)
    hist = r["clean"].tail(90)
    fig = go.Figure()
    fig.add_scatter(x=hist.index, y=hist.values, name="Actual (cleaned)", line=dict(color=ui.BLUE))
    fig.add_scatter(x=ev["test_dates"], y=ev["test_preds"][ev["best_model"]], name="Test-window forecast", line=dict(color=ui.AMBER, dash="dot"))
    fig.add_scatter(x=fc.date, y=fc.upper_80, line=dict(width=0), showlegend=False)
    fig.add_scatter(x=fc.date, y=fc.lower_80, fill="tonexty", fillcolor="rgba(25,181,214,.18)", line=dict(width=0), name="~80% interval (assumption-based)")
    fig.add_scatter(x=fc.date, y=fc.forecast, name="30-day forecast", line=dict(color=ui.CYAN))
    fig.update_layout(title="Demand history, backtest and forecast")
    c1.plotly_chart(ui.style(fig), use_container_width=True)
    h = pd.DataFrame({"horizon": ["7-day", "14-day", "30-day"], "forecast_units": [fc.forecast[:7].sum(), fc.forecast[:14].sum(), fc.forecast.sum()]}).round(0)
    c2.dataframe(h, use_container_width=True, hide_index=True)
    c2.write(f"Weekly autocorrelation (lag 7): **{r['acf7']:.2f}**")
    c2.dataframe(r["dow"].to_frame("day-of-week index").T, use_container_width=True)
    st.caption("Interval = forecast +/- 1.28 x test RMSE (normal-residual assumption; not empirically calibrated).")

import plotly.express as px

from .. import ui


def render(c):
    st = c.st
    st.markdown(ui.hero_app("Stock-out Early Warning", desc="Days remaining, lead-time demand, shortage dates and reasons."), unsafe_allow_html=True)
    so = c.kpis()["_so"]
    f1, f2 = st.columns(2)
    lv = f1.multiselect("Risk level", ["Critical", "High", "Medium", "Low"], default=["Critical", "High", "Medium"])
    fa = f2.multiselect("Facility", sorted(so.facility.unique()))
    d = so[so.risk_level.isin(lv)] if lv else so
    if fa:
        d = d[d.facility.isin(fa)]
    st.dataframe(d[["facility", "medicine", "criticality", "on_hand", "inbound_qty", "avg_daily_forecast", "days_remaining", "lead_time_days",
                    "lead_time_demand", "inventory_position", "reorder_point", "reorder_qty", "shortage_date", "risk_score", "risk_level",
                    "p_stockout_lt_model", "reason"]], use_container_width=True, hide_index=True)
    st.markdown('<div class="note"><b>risk_score</b> is a transparent heuristic index (0-100: cover vs lead time 45%, shortage timing 35%, size of shortfall 20%, scaled by criticality). '
                '<b>p_stockout_lt_model</b> is a Monte-Carlo probability of running out within one supplier lead time under a normal demand-noise model - model-based, '
                '<u>not</u> empirically calibrated.</div>', unsafe_allow_html=True)
    fig = px.scatter(so, x="days_remaining", y="risk_score", color="risk_level", size="criticality", hover_data=["facility", "medicine"],
                     color_discrete_map=ui.SEV_COLOR, title="Risk score vs days of on-hand cover")
    st.plotly_chart(ui.style(fig), use_container_width=True)

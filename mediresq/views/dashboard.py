import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .. import ui


def render(c):
    st, db = c.st, c.db
    st.markdown(ui.hero_app(), unsafe_allow_html=True)
    if not c.eff.is_empty():
        st.warning("Active simulated disruptions: " + "; ".join(c.eff.describe()))
    k = c.kpis()
    cards = [("Medicines", k["total_medicines"], ""), ("Facilities (hospitals)", k["total_facilities"], ""),
             ("Warehouses", k["total_warehouses"], ""), ("Inventory value (INR)", f"{k['inventory_value']/1e6:,.2f} M", ""),
             ("Critical stock alerts", k["critical_alerts"], "red" if k["critical_alerts"] else "green"),
             ("Predicted stock-outs", k["predicted_stockouts"], "red" if k["predicted_stockouts"] else "green"),
             ("Near-expiry batches (<=90d)", k["near_expiry_batches"], "amber"),
             ("High-risk suppliers", k["supplier_risks"], "amber"), ("Pending decisions", k["pending_decisions"], "amber"),
             ("Supply resilience index", f"{k['resilience_index']}/100", "green" if k["resilience_index"] >= 80 else "amber")]
    for row in (cards[:5], cards[5:]):
        cols = st.columns(5)
        for col, (l, v, t) in zip(cols, row):
            col.markdown(ui.kpi(l, v, t), unsafe_allow_html=True)
    st.caption("Resilience index is a transparent heuristic (30% stock availability, 25% low stock-out risk share, 20% supplier reliability, 15% expiry exposure, 10% shipment punctuality) - not a validated benchmark. Data are synthetic.")
    summ, so = k["_summary"], k["_so"]
    c1, c2 = st.columns(2)
    d = db.df("SELECT date, SUM(qty) qty FROM consumption GROUP BY date ORDER BY date").tail(120)
    fc = pd.DataFrame({"date": pd.date_range(c.as_of, periods=14), "forecast": sum(v["mean"][:14] for v in k["_state"].forecasts.values())})
    fig = go.Figure()
    fig.add_scatter(x=pd.to_datetime(d.date), y=d.qty.rolling(7, min_periods=1).mean(), name="Actual demand (7d avg)", line=dict(color=ui.BLUE))
    fig.add_scatter(x=fc.date, y=fc.forecast, name="14-day forecast", line=dict(color=ui.CYAN, dash="dash"))
    fig.update_layout(title="Medicine demand trend (all hospitals, units/day)")
    c1.plotly_chart(ui.style(fig), use_container_width=True)
    h = summ[summ.type == "hospital"].groupby(["facility", "status"]).size().reset_index(name="lines")
    fig = px.bar(h, x="facility", y="lines", color="status", title="Inventory availability by facility (stock lines)",
                 color_discrete_map={"Critical": ui.RED, "Reorder": ui.AMBER, "OK": ui.GREEN, "Overstock": ui.GREY})
    c2.plotly_chart(ui.style(fig), use_container_width=True)
    c3, c4 = st.columns(2)
    r = so.groupby(["facility", "risk_level"]).size().reset_index(name="lines")
    fig = px.bar(r, x="facility", y="lines", color="risk_level", title="Stock-out risk (heuristic level)", color_discrete_map=ui.SEV_COLOR)
    c3.plotly_chart(ui.style(fig), use_container_width=True)
    w = k["_wastage"]
    e = w.groupby("bucket", observed=True).value_inr.sum().reset_index()
    fig = px.bar(e, x="bucket", y="value_inr", title="Expiry exposure (INR value by time to expiry)", color_discrete_sequence=[ui.AMBER])
    c4.plotly_chart(ui.style(fig), use_container_width=True)
    c5, c6 = st.columns(2)
    sm = k["_suppliers"]
    fig = px.bar(sm, x="supplier_id", y="reliability_score", color="risk", title="Supplier performance (reliability score)",
                 color_discrete_map={"High": ui.RED, "Medium": ui.AMBER, "Low": ui.GREEN})
    c5.plotly_chart(ui.style(fig), use_container_width=True)
    fv = summ.groupby("facility").value_inr.sum().reset_index()
    fig = px.bar(fv, x="facility", y="value_inr", title="Facility-level inventory value (INR)", color_discrete_sequence=[ui.BLUE])
    c6.plotly_chart(ui.style(fig), use_container_width=True)
    st.subheader("Alerts and recent activity")
    a, b = st.columns([3, 2])
    al = k["_alerts"]
    a.dataframe(al[["severity", "type", "facility", "medicine", "reason"]].head(12) if len(al) else al, use_container_width=True, hide_index=True)
    b.dataframe(db.df("SELECT ts, actor, action, entity, entity_id FROM audit_log ORDER BY audit_id DESC LIMIT 12"), use_container_width=True, hide_index=True)

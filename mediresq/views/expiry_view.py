import plotly.express as px

from .. import expiry, inventory, ui


def render(c):
    st, db = c.st, c.db
    st.markdown(ui.hero_app("Batch & Expiry Intelligence", desc="FEFO, expiry exposure, wastage risk and safe transfers."), unsafe_allow_html=True)
    w = expiry.wastage_risk(db, c.as_of)
    a, b, d, e = st.columns(4)
    a.markdown(ui.kpi("Expired (still on hand)", int((~w.usable & (w.days_to_expiry <= 0)).sum()), "red"), unsafe_allow_html=True)
    b.markdown(ui.kpi("Expiring <=30d", int(((w.days_to_expiry <= 30) & (w.days_to_expiry > 0)).sum()), "amber"), unsafe_allow_html=True)
    d.markdown(ui.kpi("Near-expiry value (INR)", f"{w[(w.days_to_expiry <= 90) & (w.days_to_expiry > 0)].value_inr.sum():,.0f}", "amber"), unsafe_allow_html=True)
    e.markdown(ui.kpi("Projected waste (INR)", f"{w[w.usable].projected_waste_inr.sum():,.0f}", "red"), unsafe_allow_html=True)
    g = w.groupby("bucket", observed=True).agg(batches=("batch_id", "count"), value=("value_inr", "sum")).reset_index()
    st.plotly_chart(ui.style(px.bar(g, x="bucket", y="value", text="batches", title="Expiry exposure by bucket (INR; label = #batches)", color_discrete_sequence=[ui.BLUE])), use_container_width=True)
    t1, t2, t3 = st.tabs(["Batch register", "FEFO recommendation", "Safe transfers & quarantine"])
    with t1:
        bk = st.multiselect("Bucket", ["Expired", "0-30d", "31-60d", "61-90d", ">90d"], default=["Expired", "0-30d", "31-60d"])
        d = w[w.bucket.astype(str).isin(bk)] if bk else w
        st.dataframe(d[["facility", "medicine", "batch_no", "expiry_date", "days_to_expiry", "qty", "status", "value_inr", "projected_waste_qty", "bucket"]].sort_values("days_to_expiry"),
                     use_container_width=True, hide_index=True)
    with t2:
        f = st.selectbox("Facility", db.df("SELECT facility_id FROM facilities").facility_id.tolist())
        m = st.selectbox("Medicine", db.df("SELECT medicine_id, name FROM medicines").medicine_id.tolist())
        fe = expiry.fefo(db, f, m, c.as_of)
        st.dataframe(fe[["batch_no", "expiry_date", "days_to_expiry", "qty"]], use_container_width=True, hide_index=True)
        st.caption("Issue in this order. Expired and quarantined batches are never recommended.")
    with t3:
        sc = expiry.safe_transfer_candidates(db, c.as_of)
        st.dataframe(sc, use_container_width=True, hide_index=True)
        if sc.empty:
            st.info("No near-expiry batch currently has both projected waste and a shelf-life-safe destination with low cover.")
        if c.can("edit_inventory"):
            bid = st.number_input("Batch ID", min_value=1, value=1)
            x, y = st.columns(2)
            if x.button("Quarantine batch"):
                inventory.set_batch_status(db, int(bid), "quarantined", c.user["username"]); c.bump(); st.success("Quarantined")
            if y.button("Release from quarantine"):
                inventory.set_batch_status(db, int(bid), "active", c.user["username"]); c.bump(); st.success("Released")

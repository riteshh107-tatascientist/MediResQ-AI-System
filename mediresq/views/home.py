from .. import ui


def render(c):
    st = c.st
    st.markdown(ui.hero_home(), unsafe_allow_html=True)
    a, b, _ = st.columns([1, 1, 3])
    if a.button("Enter Dashboard  →", type="primary", use_container_width=True):
        st.session_state["entered"] = True
        st.rerun()
    b.markdown('<span class="sim">Synthetic demo data</span>', unsafe_allow_html=True)
    st.markdown("### What MediResQ AI does")
    feats = [("f_inventory", "Medicine Inventory Intelligence", "Batch-level stock, FEFO, 30/60/90-day expiry alerts, safety stock and reorder points per facility."),
             ("f_forecast", "AI Demand Forecasting", "Baselines vs ETS, Random Forest and Gradient Boosting - chronological evaluation with MAE, RMSE and WAPE."),
             ("f_supplier", "Supplier & Logistics Monitoring", "Reliability scoring, shipment delay tracking and labelled disruption simulation."),
             ("f_recovery", "Intelligent Inventory Recovery", "Integer-programming redistribution that respects reserves, expiry, cold chain and lane capacity.")]
    cols = st.columns(4)
    for col, (img, t, d) in zip(cols, feats):
        col.markdown(f'<div class="card fcard">{ui.img_tag(img, t + " illustration")}<h4>{t}</h4><p>{d}</p></div>', unsafe_allow_html=True)
    st.markdown("### How it works")
    steps = [("Demand Prediction", "Forecast daily demand per facility"), ("Risk Detection", "Stock-out, expiry & supplier risk"),
             ("Optimization", "Minimum-cost redistribution plan"), ("Human Approval", "Approve, modify or reject"), ("Recovery", "Execute & audit the action")]
    html = '<div class="flow">'
    for i, (t, d) in enumerate(steps):
        html += f'<div class="step"><div class="n">{i+1}</div><b>{t}</b><span>{d}</span></div>'
        if i < len(steps) - 1:
            html += '<div class="arrow">&rarr;</div>'
    st.markdown(html + "</div>", unsafe_allow_html=True)
    st.markdown("### The problem and the proposed solution")
    p, s = st.columns(2)
    p.markdown('<div class="card"><h4>The real-world problem</h4><p>Essential medicines run out at one facility while surplus - sometimes close to expiry - sits at another. '
               'Supplier delays, transport disruption and demand surges are noticed late, and recovery is manual. Shortages harm care delivery; expiry wastes scarce budgets. '
               '(Problem framing to be validated with stakeholder interviews - see docs/DESIGN_THINKING.md.)</p></div>', unsafe_allow_html=True)
    s.markdown('<div class="card"><h4>MediResQ AI&rsquo;s proposed solution</h4><p>A decision-support layer that forecasts demand, scores stock-out risk with reasons, '
               'detects supplier/logistics disruption, and computes a feasible, explainable redistribution and replenishment plan. '
               'Every procurement or physical transfer requires human approval and is audit-logged.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="note">Independent hackathon prototype built on <b>synthetic data</b>. It is not endorsed by, partnered with or integrated into SAP, '
                'and no real hospital or supplier is represented. Illustrations are locally generated graphics. Inventory decision support only - not a clinical system.</div>', unsafe_allow_html=True)

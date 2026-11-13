"""MediResQ AI - Streamlit entry point.  Run:  python -m streamlit run app.py"""
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

from mediresq import analytics, auth, config, datagen, effects as fx, ui  # noqa: E402
from mediresq.db import Database  # noqa: E402
from mediresq.views import (admin_view, alerts_view, analytics_view, dashboard, expiry_view, forecast_view, home,  # noqa: E402
                            inventory_view, optimizer_view, risk_view, supply_view)

st.set_page_config(page_title="MediResQ AI | SAP Hackfest 2026", page_icon="💊", layout="wide", initial_sidebar_state="expanded")

PAGES = {
    "Executive Dashboard": (dashboard, "view"),
    "Medicine Inventory": (inventory_view, "view"),
    "Batch & Expiry": (expiry_view, "view"),
    "AI Demand Forecasting": (forecast_view, "view"),
    "Stock-out Early Warning": (risk_view, "view"),
    "Supplier & Logistics": (supply_view, "view"),
    "Optimization & Recovery": (optimizer_view, "view"),
    "Alerts & Approvals": (alerts_view, "view"),
    "Analytics & Assistant": (analytics_view, "view"),
    "Administration": (admin_view, "manage_users"),
}


@st.cache_resource
def get_db():
    db = Database(config.DB_PATH)
    ok = False
    try:
        ok = (db.scalar("SELECT COUNT(*) FROM facilities") or 0) > 0 and (db.scalar("SELECT COUNT(*) FROM users") or 0) > 0
    except Exception:
        ok = False
    if not ok:
        as_of = date.fromisoformat(config.AS_OF) if config.AS_OF else date.today()
        datagen.seed_database(db, as_of, csv_dir=config.CSV_DIR)
    return db


def main():
    ui.inject_css(st)
    db = get_db()
    as_of = date.fromisoformat(db.scalar("SELECT value FROM meta WHERE key='as_of'"))
    ss = st.session_state
    ss.setdefault("ver", 0)
    ss.setdefault("user", None)
    ss.setdefault("entered", False)

    def bump():
        ss["ver"] += 1
        ss.pop("_k", None)

    eff = fx.from_events(db, as_of)

    def kpis():
        key = (ss["ver"], tuple(eff.describe()))
        if ss.get("_k", (None,))[0] != key:
            ss["_k"] = (key, analytics.kpis(db, as_of, eff))
        return ss["_k"][1]

    user = ss["user"]
    ctx = SimpleNamespace(st=st, db=db, as_of=as_of, eff=eff, user=user, kpis=kpis, bump=bump, can=lambda p: auth.can(ss["user"], p))

    if not ss["entered"]:
        home.render(ctx)
        return
    if user is None:
        st.markdown(ui.hero_app(), unsafe_allow_html=True)
        _, mid, _ = st.columns([1, 1.2, 1])
        with mid:
            st.subheader("Sign in")
            with st.form("login"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in", type="primary"):
                    res = auth.authenticate(db, u.strip(), p)
                    if res:
                        ss["user"] = res
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")
            with st.expander("Local demo accounts (synthetic - demo only)"):
                st.write("admin / scm / whm / viewer - password is in README.md (MEDIRESQ_DEMO_PASSWORD).")
            if st.button("← Back to home"):
                ss["entered"] = False
                st.rerun()
        return

    with st.sidebar:
        st.markdown("## 💊 MediResQ AI")
        st.caption("TIT BHOPAL | CSE (DATA SCIENCE)")
        st.write(f"**{user['username']}** - {auth.ROLE_LABEL[user['role']]}")
        st.caption(f"Data snapshot: {as_of} | SYNTHETIC")
        names = [n for n, (_, perm) in PAGES.items() if auth.can(user, perm)]
        page = st.radio("Navigate", names, label_visibility="collapsed")
        if not eff.is_empty():
            st.warning("Simulated disruptions active:\n" + "\n".join(eff.describe()))
        if st.button("Home"):
            ss["entered"] = False
            st.rerun()
        if st.button("Sign out"):
            db.audit(user["username"], "logout", "user", user["username"])
            ss["user"] = None
            st.rerun()
    PAGES[page][0].render(ctx)


main()

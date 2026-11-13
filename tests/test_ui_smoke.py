"""Executes every page's render() against the real engine with a fake Streamlit (see fake_streamlit.py)."""
import importlib
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))


class TestUISmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fake_streamlit
        cls.st = fake_streamlit.install()
        from mediresq import analytics, auth, datagen, effects as fx
        from mediresq.db import Database
        cls.tmp = tempfile.mkdtemp()
        cls.db = Database(os.path.join(cls.tmp, "t.db"))
        cls.as_of = date(2026, 11, 13)
        datagen.seed_database(cls.db, cls.as_of)
        eff = fx.from_events(cls.db, cls.as_of)
        cache = {}
        user = {"username": "admin", "role": "admin"}
        cls.ctx = SimpleNamespace(st=cls.st, db=cls.db, as_of=cls.as_of, eff=eff, user=user,
                                  kpis=lambda: cache.setdefault("k", analytics.kpis(cls.db, cls.as_of, eff)),
                                  bump=lambda: cache.clear(), can=lambda p: auth.can(user, p))

    def _page(self, mod):
        m = importlib.import_module(f"mediresq.views.{mod}")
        m.render(self.ctx)

    def test_pages_render(self):
        for mod in ["home", "dashboard", "inventory_view", "expiry_view", "forecast_view", "risk_view", "supply_view",
                    "optimizer_view", "alerts_view", "analytics_view", "admin_view"]:
            with self.subTest(page=mod):
                self._page(mod)

    def test_click_through_actions(self):
        """All buttons/forms 'pressed' - exercises run/generate/inject/demo branches (errors from empty forms are caught by the views)."""
        st = self.st
        old = (st.button, st.form_submit_button)
        st.button = lambda *a, **k: True
        st.form_submit_button = lambda *a, **k: True
        try:
            for mod in ["optimizer_view", "alerts_view", "supply_view", "expiry_view", "inventory_view", "risk_view"]:
                with self.subTest(page=mod):
                    self._page(mod)
        finally:
            st.button, st.form_submit_button = old

    def test_hero_header_contract(self):
        from mediresq import ui
        h = ui.hero_home()
        for s in ["SAP HACKFEST 2026 | WEST &amp; CENTRAL REGION", "MediResQ AI", "Predict. Protect. Prevent Shortages.",
                  "AI-Powered Essential Medicine Supply Chain Resilience.", "TIT BHOPAL | CSE (DATA SCIENCE)", "alt="]:
            self.assertIn(s, h)
        a = ui.hero_app()
        for s in ["SAP HACKFEST 2026 | WEST &amp; CENTRAL", "Predict. Protect. Resilience in Every Medicine Supply Chain.",
                  "Intelligent forecasting, disruption detection and optimized medicine recovery.", "TIT BHOPAL | CSE (DATA SCIENCE)"]:
            self.assertIn(s, a)

    def test_css_animation_contract(self):
        from mediresq import ui
        css = ui.CSS
        self.assertIn("@keyframes mrq-sweep", css)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("pointer-events:none", css)
        self.assertIn("left:-35%", css)   # starts left ...
        self.assertIn("100%{left:112%}", css)  # ... ends right (left-to-right)


if __name__ == "__main__":
    unittest.main()

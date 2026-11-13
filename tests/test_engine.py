import hashlib
import sqlite3
import unittest

import numpy as np
import pandas as pd

from helpers import AS_OF, fresh_db
from mediresq import (alerts, analytics, approvals, assistant, auth, config, datagen, demo, effects as fx, expiry,
                      forecasting, inventory, logistics, optimizer, recovery, simulator, stockout, suppliers)
from mediresq.state import State
from mediresq.views.admin_view import validate_upload

DEMO_EFF = fx.Effects(supplier_delay={"S-03": 7})


class TestData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fresh_db()

    def test_validation_checks_all_pass(self):
        res = datagen.validate_database(self.db)
        self.assertTrue(all(ok for _, ok, _ in res), [r for r in res if not r[1]])

    def test_dataset_shape(self):
        q = self.db.scalar
        self.assertEqual(q("SELECT COUNT(*) FROM facilities WHERE type='warehouse'"), 3)
        self.assertEqual(q("SELECT COUNT(*) FROM facilities WHERE type='hospital'"), 5)
        self.assertTrue(15 <= q("SELECT COUNT(*) FROM medicines") <= 25)
        self.assertTrue(5 <= q("SELECT COUNT(*) FROM suppliers") <= 8)
        self.assertGreater(q("SELECT COUNT(*) FROM consumption"), 30000)
        self.assertGreater(q("SELECT COUNT(*) FROM purchase_orders WHERE status='Delivered'"), 500)

    def test_generator_deterministic(self):
        a = datagen.generate(AS_OF, 42)["consumption"]
        b = datagen.generate(AS_OF, 42)["consumption"]
        self.assertEqual(hashlib.md5(a.to_csv().encode()).hexdigest(), hashlib.md5(b.to_csv().encode()).hexdigest())

    def test_fk_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO batches(facility_id,medicine_id,batch_no,mfg_date,expiry_date,qty) VALUES('NOPE','M01','X','2025-01-01','2026-01-01',1)")

    def test_csv_upload_validation(self):
        ok, e = validate_upload("consumption", pd.DataFrame({"date": ["2026-01-01"], "facility_id": ["H-01"], "medicine_id": ["M01"], "qty": [5]}), self.db)
        self.assertTrue(ok, e)
        bad, e = validate_upload("consumption", pd.DataFrame({"date": ["not-a-date"], "facility_id": ["X"], "medicine_id": ["M01"], "qty": [-1]}), self.db)
        self.assertFalse(bad)
        self.assertGreaterEqual(len(e), 3)
        bad, e = validate_upload("consumption", pd.DataFrame({"date": ["2026-01-01"]}), self.db)
        self.assertFalse(bad)


class TestInventory(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()

    def test_crud(self):
        inventory.add_medicine(self.db, "M99", "Test Drug 10mg", "Tablet", "Test", 2.5, 2, 365, 0, "tester")
        self.assertEqual(self.db.scalar("SELECT name FROM medicines WHERE medicine_id='M99'"), "Test Drug 10mg")
        with self.assertRaises(Exception):
            inventory.add_medicine(self.db, "M98", "Test Drug 10mg")      # duplicate name
        with self.assertRaises(ValueError):
            inventory.add_medicine(self.db, "M97", "x", criticality=9)    # bad criticality
        with self.assertRaises(ValueError):
            inventory.add_medicine(self.db, "M96", "Neg", unit_cost=-1)
        inventory.update_medicine(self.db, "M99", "tester", unit_cost=3.0, criticality=3)
        self.assertEqual(self.db.scalar("SELECT unit_cost FROM medicines WHERE medicine_id='M99'"), 3.0)
        inventory.delete_medicine(self.db, "M99", "tester")
        self.assertIsNone(self.db.scalar("SELECT 1 FROM medicines WHERE medicine_id='M99'"))
        with self.assertRaises(ValueError):
            inventory.delete_medicine(self.db, "M01", "tester")           # has dependent records
        self.assertGreaterEqual(self.db.scalar("SELECT COUNT(*) FROM audit_log WHERE action LIKE '%medicine%'"), 3)

    def test_batches_and_movements(self):
        bid = inventory.add_batch(self.db, "H-01", "M01", "TESTB1", "2026-01-01", "2027-06-01", 500, 1.2, actor="t")
        inventory.adjust_batch(self.db, bid, -100, "damaged", "t", AS_OF)
        self.assertEqual(self.db.scalar("SELECT qty FROM batches WHERE batch_id=?", (bid,)), 400)
        with self.assertRaises(ValueError):
            inventory.adjust_batch(self.db, bid, -1000, "too much", "t")
        with self.assertRaises(ValueError):
            inventory.add_batch(self.db, "H-01", "M01", "BAD", "2026-01-01", "2025-01-01", 5)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM stock_movements WHERE batch_id=?", (bid,)), 2)

    def test_policies_formula(self):
        p = self.db.df("SELECT * FROM stock_policy")
        self.assertTrue((p.safety_stock >= 0).all())
        self.assertTrue((p.reorder_point >= p.safety_stock).all())
        self.assertTrue((p.max_stock > p.reorder_point).all())
        r = p[(p.facility_id == "H-01") & (p.medicine_id == "M05")].iloc[0]
        self.assertGreater(r.avg_daily_consumption, 0)

    def test_stock_value(self):
        s = inventory.stock_summary(self.db, AS_OF)
        b = inventory.usable_batches(self.db, AS_OF)
        exp = float((b[b.usable].qty * b[b.usable].unit_cost).sum())
        self.assertAlmostEqual(float(s.value_inr.sum()), exp, places=2)


class TestExpiry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fresh_db()

    def test_expired_detected_not_usable(self):
        b = expiry.batch_table(self.db, AS_OF)
        exp = b[b.days_to_expiry <= 0]
        self.assertGreaterEqual(len(exp), 2)
        self.assertFalse(exp.usable.any())
        self.assertTrue((b[b.bucket.astype(str) == "Expired"].days_to_expiry <= 0).all())

    def test_buckets(self):
        b = expiry.batch_table(self.db, AS_OF)
        self.assertTrue(((b.bucket.astype(str) == "0-30d") == ((b.days_to_expiry > 0) & (b.days_to_expiry <= 30))).all())

    def test_fefo_order_and_exclusions(self):
        f = expiry.fefo(self.db, "WH-02", "M04", AS_OF)
        self.assertTrue(f.expiry_date.is_monotonic_increasing)
        self.assertTrue((f.status == "active").all())
        self.assertTrue((f.days_to_expiry > 0).all())
        allb = inventory.usable_batches(self.db, AS_OF)
        quarantined = allb[(allb.facility_id == "WH-02") & (allb.medicine_id == "M04") & (allb.status == "quarantined")].batch_id
        self.assertFalse(f.batch_id.isin(quarantined).any())

    def test_wastage_nonnegative_and_expired_lost(self):
        w = expiry.wastage_risk(self.db, AS_OF)
        self.assertTrue((w.projected_waste_qty >= 0).all())
        e = w[~w.usable & (w.days_to_expiry <= 0)]
        self.assertTrue((e.projected_waste_qty == e.qty).all())
        self.assertGreater(w[w.usable].projected_waste_inr.sum(), 0)

    def test_safe_transfers_never_expired_and_shelf_life(self):
        sc = expiry.safe_transfer_candidates(self.db, AS_OF)
        if len(sc):
            self.assertTrue((sc.days_left_on_arrival >= config.MIN_SHELF_AFTER_ARRIVAL).all())


class TestForecasting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fresh_db()
        s = forecasting.load_series(cls.db, "H-02", "M04", AS_OF)
        cls.clean, cls.info = forecasting.clean_series(s)
        cls.ev = forecasting.evaluate_series(cls.clean)

    def test_metric_definitions(self):
        m = forecasting.metrics(np.array([10, 10]), np.array([8, 12]))
        self.assertAlmostEqual(m["MAE"], 2.0)
        self.assertAlmostEqual(m["RMSE"], 2.0)
        self.assertAlmostEqual(m["WAPE"], 0.2)
        self.assertTrue(np.isnan(forecasting.metrics(np.zeros(3), np.ones(3))["WAPE"]))

    def test_cleaning(self):
        self.assertFalse(self.clean.isna().any())
        self.assertEqual(len(self.clean), 365)
        self.assertIn("outliers_capped", self.info)

    def test_zero_demand_series_handled(self):
        z = pd.Series(np.zeros(120), index=pd.date_range("2026-01-01", periods=120))
        c, i = forecasting.clean_series(z)
        self.assertEqual(i["zero_days"], 120)
        p = forecasting.m_ets(c.values, c.index, 7)
        self.assertTrue(np.all(np.isfinite(p)) and np.all(p >= 0))

    def test_all_models_evaluated_chronologically(self):
        t = self.ev["table"]
        self.assertEqual(set(t.model), {"Moving Average (7d)", "Seasonal Naive (7d)", "Exponential Smoothing (SES + weekly index)", "Random Forest", "Gradient Boosting"})
        self.assertEqual(set(t.split), {"validation", "test"})
        self.assertTrue(np.isfinite(t[["MAE", "RMSE", "WAPE"]].values).all())
        # test window = last 30 days, strictly after the data used to fit
        self.assertEqual(self.ev["test_dates"][-1], self.clean.index[-1])
        self.assertEqual(len(self.ev["test_dates"]), 30)

    def test_reported_metrics_match_recomputation(self):
        t = self.ev["table"]
        for name, p in self.ev["test_preds"].items():
            mine = forecasting.metrics(self.ev["test_actual"], p)
            row = t[(t.model == name) & (t.split == "test")].iloc[0]
            self.assertAlmostEqual(mine["WAPE"], row.WAPE, places=9)
            self.assertAlmostEqual(mine["RMSE"], row.RMSE, places=9)

    def test_selection_uses_validation_not_test(self):
        t = self.ev["table"]
        v = t[t.split == "validation"].set_index("model").WAPE
        self.assertEqual(self.ev["best_model"], v.idxmin())

    def test_horizons_and_interval(self):
        fc = forecasting.final_forecast(self.clean, self.ev["best_model"], self.ev["best_test_rmse"], 30)
        self.assertEqual(len(fc), 30)
        self.assertTrue((fc.lower_80 <= fc.forecast + 1e-9).all() and (fc.upper_80 >= fc.forecast - 1e-9).all())
        self.assertTrue((fc.forecast >= 0).all())

    def test_seasonality_weekly_detected(self):
        dow, mon, acf7 = forecasting.seasonality(self.clean)
        self.assertGreater(dow.max() - dow.min(), 0.1)
        self.assertGreater(acf7, 0.05)

    def test_fast_forecast_covers_all_series(self):
        ff = forecasting.fast_forecast_all(self.db, AS_OF)
        self.assertEqual(len(ff), 100)
        self.assertTrue(all(len(v["mean"]) == 30 and np.all(v["mean"] >= 0) for v in ff.values()))


class TestStockout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fresh_db()
        cls.base = stockout.compute(cls.db, AS_OF)
        cls.dis = stockout.compute(cls.db, AS_OF, DEMO_EFF)

    def test_rows_and_fields(self):
        self.assertEqual(len(self.base), 100)
        for c in ["days_remaining", "lead_time_demand", "inventory_position", "reorder_qty", "shortage_date", "risk_level", "reason", "p_stockout_lt_model"]:
            self.assertIn(c, self.base.columns)
        self.assertTrue(self.base.p_stockout_lt_model.between(0, 1).all())
        self.assertTrue(self.base.risk_score.between(0, 100).all())

    def test_days_remaining_formula(self):
        r = self.base.iloc[0]
        self.assertAlmostEqual(r.days_remaining, r.on_hand / r.avg_daily_forecast, delta=0.2)

    def test_inventory_position(self):
        r = self.base.iloc[3]
        self.assertAlmostEqual(r.inventory_position, r.on_hand + r.inbound_qty, delta=1)

    def test_demo_story(self):
        b = self.base[(self.base.facility_id == "H-02") & (self.base.medicine_id == "M04")].iloc[0]
        d = self.dis[(self.dis.facility_id == "H-02") & (self.dis.medicine_id == "M04")].iloc[0]
        self.assertEqual(b.risk_level, "Low")
        self.assertIn(d.risk_level, ("High", "Critical"))
        self.assertLessEqual(d.shortage_in_days, 4)
        self.assertGreater(d.unmet_14d, 300)
        self.assertIn("delayed", d.reason)

    def test_every_alert_has_reason(self):
        hi = self.dis[self.dis.risk_level.isin(["Critical", "High"])]
        self.assertTrue((hi.reason.str.len() > 10).all())

    def test_ordering(self):
        order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        lv = self.base.risk_level.map(order)
        self.assertTrue(lv.is_monotonic_increasing)


class TestSuppliersLogistics(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()

    def test_supplier_metrics(self):
        m = suppliers.supplier_metrics(self.db, AS_OF).set_index("supplier_id")
        self.assertEqual(len(m), 7)
        self.assertTrue(m.reliability_score.between(0, 100).all())
        self.assertTrue(m.on_time_rate.between(0, 1).all())
        self.assertLess(m.loc["S-03", "reliability_score"], m.loc["S-05", "reliability_score"])
        self.assertEqual(m.loc["S-03", "risk"], "High")

    def test_shipments_delay_detection(self):
        s = logistics.shipments_status(self.db, AS_OF)
        self.assertGreater((s.transport_status == "Delayed").sum(), 0)
        d = s[s.transport_status == "Delayed"]
        self.assertTrue((d.delay_days > 0).all())

    def test_disruption_effect_on_shipments(self):
        a = logistics.shipments_status(self.db, AS_OF)
        b = logistics.shipments_status(self.db, AS_OF, DEMO_EFF)
        sh = a[(a.supplier_id == "S-03") & (a.status == "In Transit")].shipment_id
        self.assertGreater(len(sh), 0)
        x = a.set_index("shipment_id").loc[sh].effective_expected
        y = b.set_index("shipment_id").loc[sh].effective_expected
        self.assertTrue(((y - x).dt.days == 7).all())

    def test_inject_event_validation_and_labeling(self):
        with self.assertRaises(ValueError):
            logistics.inject_event(self.db, "meteor", "X", 1, AS_OF, 3, "t")
        with self.assertRaises(ValueError):
            logistics.inject_event(self.db, "partial_delivery", "S-01", 5, AS_OF, 3, "t")
        with self.assertRaises(ValueError):
            logistics.inject_event(self.db, "supplier_delay", "S-01", 3, AS_OF, 0, "t")
        eid = logistics.inject_event(self.db, "supplier_delay", "S-01", 3, AS_OF, 5, "t")
        row = self.db.df("SELECT * FROM disruption_events WHERE event_id=?", (eid,)).iloc[0]
        self.assertEqual(row.simulated, 1)
        self.assertTrue(row.description.startswith("SIMULATED"))
        e = fx.from_events(self.db, AS_OF)
        self.assertEqual(e.supplier_delay["S-01"], 3)
        logistics.clear_event(self.db, eid, "t")
        self.assertTrue(fx.from_events(self.db, AS_OF).is_empty())

    def test_other_event_types_build_effects(self):
        for t, ent, mag in [("demand_surge", "ALL", 20), ("warehouse_disruption", "WH-01", 1), ("transport_disruption", "ALL", 1.5), ("partial_delivery", "S-03", 0.5)]:
            logistics.inject_event(self.db, t, ent, mag, AS_OF, 7, "t")
        e = fx.from_events(self.db, AS_OF)
        self.assertAlmostEqual(e.demand_mult["ALL"], 1.2)
        self.assertIn("WH-01", e.warehouse_down)
        self.assertEqual(e.partial_fill["S-03"], 0.5)
        self.assertEqual(e.transport_cost_mult, 1.5)


class TestOptimizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fresh_db()
        cls.st = State(cls.db, AS_OF, DEMO_EFF)
        cls.res = optimizer.build_plan(cls.db, AS_OF, state=cls.st)

    def test_demo_feasible_and_covers_h02_ceftriaxone(self):
        self.assertEqual(self.res["summary"]["status"], "feasible")
        p = self.res["plan"]
        m4 = p[(p.destination == "H-02") & (p.medicine_id == "M04")]
        self.assertGreater(len(m4), 0)
        self.assertGreater(m4.qty.sum(), 300)
        self.assertGreater(m4.source.nunique(), 1)      # needs multiple sources (limited eligible stock at WH-02)

    def test_never_uses_expired_or_quarantined_or_short_shelf(self):
        b = inventory.usable_batches(self.db, AS_OF)
        p = self.res["plan"]
        for r in p.itertuples():
            for part in r.batches_fefo.split("; "):
                bn = part.split(":")[0]
                row = b[(b.facility_id == r.source) & (b.medicine_id == r.medicine_id) & (b.batch_no == bn)].iloc[0]
                self.assertEqual(row.status, "active")
                self.assertGreater(row.days_to_expiry - r.eta_hours / 24, config.MIN_SHELF_AFTER_ARRIVAL - 1e-9)

    def test_source_limits_respected(self):
        p = self.res["plan"].groupby(["source", "medicine_id"]).qty.sum()
        for (s, m), q in p.items():
            self.assertLessEqual(q, self.st.on_hand(s, m) + 1e-6)

    def test_reserve_respected_for_hospital_sources(self):
        p = self.res["plan"]
        for r in p[p.source.str.startswith("H-")].itertuples():
            sim = self.st.simulate(r.source, r.medicine_id, extra_out=[(1, r.qty)], H=config.PLAN_HORIZON_DAYS)
            self.assertLess(sim["unmet"].sum(), 1.0, "transfer must not create a new shortage at the source")

    def test_lane_capacity_and_cost(self):
        lanes = self.st.lanes.set_index(["origin_id", "dest_id"])
        p = self.res["plan"]
        for (s, d), g in p.groupby(["source", "destination"]):
            self.assertLessEqual(g.qty.sum(), lanes.loc[(s, d)].capacity_units)
        r = p.iloc[0]
        cpu = lanes.loc[(r.source, r.destination)].cost_per_unit
        cold = int(self.st.med.loc[r.medicine_id, "cold_chain"])
        self.assertAlmostEqual(r.est_cost_inr, r.qty * cpu * (1.25 if cold else 1.0), places=1)

    def test_cost_minimised_vs_naive(self):
        """Optimizer must not be more expensive than shipping the same quantity over the most expensive feasible lane."""
        p = self.res["plan"]
        self.assertLess(p.est_cost_inr.sum(), p.qty.sum() * self.st.lanes.cost_per_unit.max())

    def test_infeasible_has_explanations(self):
        e = fx.Effects(supplier_delay={"S-03": 7}, warehouse_down={"WH-01", "WH-02", "WH-03"}, demand_mult={"ALL": 2.0})
        r = optimizer.build_plan(self.db, AS_OF, e)
        self.assertIn(r["summary"]["status"], ("partial", "infeasible"))
        self.assertGreater(len(r["unmet"]), 0)
        self.assertTrue((r["unmet"].why_not_covered.str.len() > 5).all())
        self.assertTrue((r["plan"].source.str.startswith("H-")).all() if len(r["plan"]) else True)   # no down warehouses used

    def test_no_shortage_message(self):
        r = optimizer.build_plan(self.db, AS_OF, only_medicines=["M09"])
        self.assertIn(r["summary"]["status"], ("no_shortage", "feasible", "partial"))

    def test_backend_reported(self):
        self.assertIn(self.res["summary"]["backend"], ("ortools", "scipy"))


class TestSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fresh_db()
        cls.r = simulator.run(cls.db, AS_OF, DEMO_EFF)

    def test_ordering_baseline_disrupted_recovered(self):
        s = self.r["summary"].set_index("scenario")
        b, d, rc = s.iloc[0], s.iloc[1], s.iloc[2]
        self.assertGreaterEqual(d.unmet_units, b.unmet_units)
        self.assertLess(rc.unmet_units, d.unmet_units)
        self.assertGreater(rc.recovery_cost_inr, 0)
        self.assertEqual(b.recovery_cost_inr, 0)
        self.assertGreaterEqual(b.fill_rate_pct, d.fill_rate_pct)

    def test_demand_surge_hurts(self):
        r = simulator.run(self.db, AS_OF, fx.Effects(demand_mult={"ALL": 1.3}))
        s = r["summary"]
        self.assertGreater(s.unmet_units[1], s.unmet_units[0])

    def test_conservation_of_flow(self):
        st = State(self.db, AS_OF, DEMO_EFF)
        sim = st.simulate("H-02", "M04", replenish=True)
        self.assertTrue(np.all(sim["stock"] >= -1e-9))
        self.assertTrue(np.allclose(sim["sold"] + sim["unmet"], sim["demand"]))

    def test_curves(self):
        c = simulator.stock_curves(self.r["states"], "M04")
        self.assertEqual(list(c.columns), ["date", "Baseline", "Disrupted", "Recovered"])

    def test_policy_comparison_runs_and_reproducible(self):
        a = analytics.policy_comparison(self.db, AS_OF, n_runs=4, seed=3)
        b = analytics.policy_comparison(self.db, AS_OF, n_runs=4, seed=3)
        pd.testing.assert_frame_equal(a, b)
        self.assertTrue(a.fill_rate_pct.between(0, 100).all())


class TestApprovals(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()
        self.rec = recovery.generate(self.db, AS_OF, DEMO_EFF, persist=True, tag="t")
        self.admin = {"username": "admin", "role": "admin"}
        self.viewer = {"username": "viewer", "role": "viewer"}
        self.whm = {"username": "whm", "role": "warehouse_manager"}

    def test_actions_pending_and_prioritised(self):
        r = approvals.pending(self.db)
        self.assertGreater(len(r), 3)
        self.assertTrue((r.status == "Pending").all())
        a = self.rec["actions"]
        self.assertTrue(a.priority_score.is_monotonic_decreasing)
        self.assertTrue((a.reasoning.str.len() > 20).all())

    def test_regeneration_does_not_duplicate(self):
        n = self.db.scalar("SELECT COUNT(*) FROM recommendations")
        recovery.generate(self.db, AS_OF, DEMO_EFF, persist=True, tag="t")
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM recommendations"), n)

    def test_role_enforcement(self):
        rid = int(approvals.pending(self.db).iloc[0].rec_id)
        with self.assertRaises(PermissionError):
            approvals.decide(self.db, rid, self.viewer, "Approved")
        proc = self.db.df("SELECT rec_id FROM recommendations WHERE rec_type='PROCURE' LIMIT 1")
        if len(proc):
            with self.assertRaises(PermissionError):
                approvals.decide(self.db, int(proc.iloc[0].rec_id), self.whm, "Approved")

    def test_reject_modify_rules(self):
        rid = int(approvals.pending(self.db).iloc[0].rec_id)
        with self.assertRaises(ValueError):
            approvals.decide(self.db, rid, self.admin, "Rejected", "")
        q = int(self.db.scalar("SELECT qty FROM recommendations WHERE rec_id=?", (rid,)))
        with self.assertRaises(ValueError):
            approvals.decide(self.db, rid, self.admin, "Modified", "too big", q * 3)
        approvals.decide(self.db, rid, self.admin, "Rejected", "not needed")
        self.assertEqual(self.db.scalar("SELECT status FROM recommendations WHERE rec_id=?", (rid,)), "Rejected")
        with self.assertRaises(ValueError):
            approvals.decide(self.db, rid, self.admin, "Approved")

    def test_execute_requires_approval_and_moves_stock(self):
        tr = self.db.df("SELECT * FROM recommendations WHERE rec_type='TRANSFER' AND medicine_id='M04' AND dest_id='H-02' ORDER BY qty DESC LIMIT 1").iloc[0]
        with self.assertRaises(ValueError):
            approvals.execute(self.db, int(tr.rec_id), self.admin, AS_OF)          # not approved yet
        tot = lambda f: self.db.scalar("SELECT SUM(qty) FROM batches WHERE facility_id=? AND medicine_id='M04'", (f,))
        s0, d0 = tot(tr.source_id), tot("H-02")
        approvals.decide(self.db, int(tr.rec_id), self.admin, "Modified", "reduce slightly", int(tr.qty * 0.9))
        approvals.execute(self.db, int(tr.rec_id), self.admin, AS_OF)
        q = int(tr.qty * 0.9)
        self.assertEqual(tot(tr.source_id), s0 - q)
        self.assertEqual(tot("H-02"), d0 + q)
        self.assertEqual(self.db.scalar("SELECT status FROM recommendations WHERE rec_id=?", (int(tr.rec_id),)), "Executed")
        acts = set(self.db.df("SELECT action FROM audit_log").action)
        self.assertTrue({"recommendation_modified", "recommendation_executed", "plan_generated"} <= acts)
        # never moves quarantined stock
        qb = self.db.df("SELECT SUM(qty) q FROM batches WHERE facility_id='WH-02' AND medicine_id='M04' AND status='quarantined'").iloc[0].q
        self.assertEqual(qb, 200)

    def test_procure_execute_creates_po(self):
        pr = self.db.df("SELECT * FROM recommendations WHERE rec_type='PROCURE' LIMIT 1")
        self.assertGreater(len(pr), 0)
        rid = int(pr.iloc[0].rec_id)
        approvals.decide(self.db, rid, self.admin, "Approved", "ok")
        approvals.execute(self.db, rid, self.admin, AS_OF)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM purchase_orders WHERE po_id=?", (f"PO-R{rid:04d}",)), 1)

    def test_demo_runner(self):
        d = demo.run_demo(self.db, AS_OF, "admin")
        self.assertEqual(self.db.scalar("SELECT simulated FROM disruption_events WHERE event_id=?", (d["event_id"],)), 1)
        self.assertGreater(len(d["recovery"]["actions"]), 0)


class TestDashboardAlertsAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fresh_db()
        cls.k = analytics.kpis(cls.db, AS_OF)

    def test_kpis_match_raw_sql(self):
        q = self.db.scalar
        self.assertEqual(self.k["total_medicines"], q("SELECT COUNT(*) FROM medicines"))
        self.assertEqual(self.k["total_facilities"], q("SELECT COUNT(*) FROM facilities WHERE type='hospital'"))
        self.assertEqual(self.k["total_warehouses"], q("SELECT COUNT(*) FROM facilities WHERE type='warehouse'"))
        b = inventory.usable_batches(self.db, AS_OF)
        self.assertAlmostEqual(self.k["inventory_value"], float((b[b.usable].qty * b[b.usable].unit_cost).sum()), places=1)
        self.assertEqual(self.k["pending_decisions"], q("SELECT COUNT(*) FROM recommendations WHERE status='Pending'"))
        self.assertTrue(0 <= self.k["resilience_index"] <= 100)
        nb = expiry.wastage_risk(self.db, AS_OF)
        self.assertEqual(self.k["near_expiry_batches"], int(((nb.days_to_expiry <= 90) & (nb.days_to_expiry > 0) & (nb.qty > 0)).sum()))

    def test_resilience_falls_under_disruption(self):
        k2 = analytics.kpis(self.db, AS_OF, DEMO_EFF)
        self.assertLess(k2["resilience_index"], self.k["resilience_index"])
        self.assertGreater(k2["predicted_stockouts"], self.k["predicted_stockouts"])

    def test_alert_types_and_fields(self):
        al = self.k["_alerts"]
        for t in ["Critical Stock", "Predicted Stockout", "Expiry Risk", "Shipment Disruption", "Supplier Delay"]:
            self.assertIn(t, set(al.type), t)
        for c in ["status", "timestamp", "reason", "recommended_action"]:
            self.assertTrue(al[c].notna().all(), c)
        self.assertEqual(al.alert_key.nunique(), len(al))

    def test_alert_status_workflow(self):
        al = self.k["_alerts"]
        key = al.iloc[0].alert_key
        alerts.set_status(self.db, key, "Acknowledged", {"username": "scm"}, "looking")
        again = alerts.build(self.db, AS_OF)
        self.assertEqual(again[again.alert_key == key].iloc[0].status, "Acknowledged")
        with self.assertRaises(ValueError):
            alerts.set_status(self.db, key, "Bogus", {"username": "scm"})

    def test_historical_metrics(self):
        m = analytics.historical_metrics(self.db, AS_OF)
        self.assertTrue(90 < m["demand_fulfilment_pct"] <= 100)
        self.assertGreater(m["inventory_turnover_x"], 0)
        self.assertGreater(m["expired_stock_value_inr"], 0)

    def test_assistant_uses_real_data(self):
        t, d = assistant.answer(self.db, AS_OF, "Which supplier has the highest delay?", self.k)
        sm = self.k["_suppliers"].sort_values("avg_delay_days", ascending=False).iloc[0].supplier
        self.assertIn(sm, t)
        t, d = assistant.answer(self.db, AS_OF, "What batches expire next month?", self.k)
        self.assertEqual(len(d), int(t.split()[0]))
        t, d = assistant.answer(self.db, AS_OF, "Which facility is at greatest risk?", self.k)
        self.assertIsNotNone(d)
        t, d = assistant.answer(self.db, AS_OF, "tell me a joke", self.k)
        self.assertEqual(t, assistant.HELP)


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()

    def test_hash_and_verify(self):
        h, s = auth.hash_password("Str0ngPassw0rd")
        self.assertNotIn("Str0ng", h)
        self.assertTrue(auth.verify_password("Str0ngPassw0rd", h, s))
        self.assertFalse(auth.verify_password("wrong", h, s))
        h2, _ = auth.hash_password("Str0ngPassw0rd")
        self.assertNotEqual(h, h2)   # random salt

    def test_login_and_roles(self):
        u = auth.authenticate(self.db, "viewer", config.DEMO_PASSWORD)
        self.assertEqual(u["role"], "viewer")
        self.assertTrue(auth.can(u, "view") and not auth.can(u, "approve_transfer"))
        self.assertIsNone(auth.authenticate(self.db, "viewer", "bad"))
        self.assertIsNone(auth.authenticate(self.db, "ghost", "bad"))
        self.assertTrue(auth.can(auth.authenticate(self.db, "admin", config.DEMO_PASSWORD), "manage_users"))
        self.assertFalse(auth.can(auth.authenticate(self.db, "whm", config.DEMO_PASSWORD), "approve_procure"))
        self.assertGreaterEqual(self.db.scalar("SELECT COUNT(*) FROM audit_log WHERE action='login_failed'"), 2)

    def test_password_not_stored_plain(self):
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM users WHERE password_hash=?", (config.DEMO_PASSWORD,)), 0)

    def test_user_validation(self):
        with self.assertRaises(ValueError):
            auth.create_user(self.db, "x y", "Str0ngPassw0rd", "viewer")
        with self.assertRaises(ValueError):
            auth.create_user(self.db, "newuser", "weak", "viewer")
        with self.assertRaises(ValueError):
            auth.create_user(self.db, "newuser", "Str0ngPassw0rd", "root")
        auth.create_user(self.db, "newuser", "Str0ngPassw0rd", "viewer")


if __name__ == "__main__":
    unittest.main()

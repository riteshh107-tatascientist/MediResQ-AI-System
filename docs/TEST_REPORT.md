# Test Report

Executed: 2026-11-13T05:05:54 | Python 3.12.3 | runner: `python -m unittest` (pytest-compatible) | duration 30.0s
**Result: 69 tests, 0 failures, 0 errors.**

Expected result for every row: the test's assertions hold (see `tests/test_engine.py`, `tests/test_ui_smoke.py`). Actual result is what this run produced.

| Test case | What it checks | Actual | Notes |
|---|---|---|---|
| TestApprovals.test_actions_pending_and_prioritised | actions pending and prioritised | **PASS** |  |
| TestApprovals.test_demo_runner | demo runner | **PASS** |  |
| TestApprovals.test_execute_requires_approval_and_moves_stock | execute requires approval and moves stock | **PASS** |  |
| TestApprovals.test_procure_execute_creates_po | procure execute creates po | **PASS** |  |
| TestApprovals.test_regeneration_does_not_duplicate | regeneration does not duplicate | **PASS** |  |
| TestApprovals.test_reject_modify_rules | reject modify rules | **PASS** |  |
| TestApprovals.test_role_enforcement | role enforcement | **PASS** |  |
| TestAuth.test_hash_and_verify | hash and verify | **PASS** |  |
| TestAuth.test_login_and_roles | login and roles | **PASS** |  |
| TestAuth.test_password_not_stored_plain | password not stored plain | **PASS** |  |
| TestAuth.test_user_validation | user validation | **PASS** |  |
| TestDashboardAlertsAssistant.test_alert_status_workflow | alert status workflow | **PASS** |  |
| TestDashboardAlertsAssistant.test_alert_types_and_fields | alert types and fields | **PASS** |  |
| TestDashboardAlertsAssistant.test_assistant_uses_real_data | assistant uses real data | **PASS** |  |
| TestDashboardAlertsAssistant.test_historical_metrics | historical metrics | **PASS** |  |
| TestDashboardAlertsAssistant.test_kpis_match_raw_sql | kpis match raw sql | **PASS** |  |
| TestDashboardAlertsAssistant.test_resilience_falls_under_disruption | resilience falls under disruption | **PASS** |  |
| TestData.test_csv_upload_validation | csv upload validation | **PASS** |  |
| TestData.test_dataset_shape | dataset shape | **PASS** |  |
| TestData.test_fk_enforced | fk enforced | **PASS** |  |
| TestData.test_generator_deterministic | generator deterministic | **PASS** |  |
| TestData.test_validation_checks_all_pass | validation checks all pass | **PASS** |  |
| TestExpiry.test_buckets | buckets | **PASS** |  |
| TestExpiry.test_expired_detected_not_usable | expired detected not usable | **PASS** |  |
| TestExpiry.test_fefo_order_and_exclusions | fefo order and exclusions | **PASS** |  |
| TestExpiry.test_safe_transfers_never_expired_and_shelf_life | safe transfers never expired and shelf life | **PASS** |  |
| TestExpiry.test_wastage_nonnegative_and_expired_lost | wastage nonnegative and expired lost | **PASS** |  |
| TestForecasting.test_all_models_evaluated_chronologically | all models evaluated chronologically | **PASS** |  |
| TestForecasting.test_cleaning | cleaning | **PASS** |  |
| TestForecasting.test_fast_forecast_covers_all_series | fast forecast covers all series | **PASS** |  |
| TestForecasting.test_horizons_and_interval | horizons and interval | **PASS** |  |
| TestForecasting.test_metric_definitions | metric definitions | **PASS** |  |
| TestForecasting.test_reported_metrics_match_recomputation | reported metrics match recomputation | **PASS** |  |
| TestForecasting.test_seasonality_weekly_detected | seasonality weekly detected | **PASS** |  |
| TestForecasting.test_selection_uses_validation_not_test | selection uses validation not test | **PASS** |  |
| TestForecasting.test_zero_demand_series_handled | zero demand series handled | **PASS** |  |
| TestInventory.test_batches_and_movements | batches and movements | **PASS** |  |
| TestInventory.test_crud | crud | **PASS** |  |
| TestInventory.test_policies_formula | policies formula | **PASS** |  |
| TestInventory.test_stock_value | stock value | **PASS** |  |
| TestOptimizer.test_backend_reported | backend reported | **PASS** |  |
| TestOptimizer.test_cost_minimised_vs_naive | Optimizer must not be more expensive than shipping the same quantity over the most expensive feasible lane. | **PASS** |  |
| TestOptimizer.test_demo_feasible_and_covers_h02_ceftriaxone | demo feasible and covers h02 ceftriaxone | **PASS** |  |
| TestOptimizer.test_infeasible_has_explanations | infeasible has explanations | **PASS** |  |
| TestOptimizer.test_lane_capacity_and_cost | lane capacity and cost | **PASS** |  |
| TestOptimizer.test_never_uses_expired_or_quarantined_or_short_shelf | never uses expired or quarantined or short shelf | **PASS** |  |
| TestOptimizer.test_no_shortage_message | no shortage message | **PASS** |  |
| TestOptimizer.test_reserve_respected_for_hospital_sources | reserve respected for hospital sources | **PASS** |  |
| TestOptimizer.test_source_limits_respected | source limits respected | **PASS** |  |
| TestSimulation.test_conservation_of_flow | conservation of flow | **PASS** |  |
| TestSimulation.test_curves | curves | **PASS** |  |
| TestSimulation.test_demand_surge_hurts | demand surge hurts | **PASS** |  |
| TestSimulation.test_ordering_baseline_disrupted_recovered | ordering baseline disrupted recovered | **PASS** |  |
| TestSimulation.test_policy_comparison_runs_and_reproducible | policy comparison runs and reproducible | **PASS** |  |
| TestStockout.test_days_remaining_formula | days remaining formula | **PASS** |  |
| TestStockout.test_demo_story | demo story | **PASS** |  |
| TestStockout.test_every_alert_has_reason | every alert has reason | **PASS** |  |
| TestStockout.test_inventory_position | inventory position | **PASS** |  |
| TestStockout.test_ordering | ordering | **PASS** |  |
| TestStockout.test_rows_and_fields | rows and fields | **PASS** |  |
| TestSuppliersLogistics.test_disruption_effect_on_shipments | disruption effect on shipments | **PASS** |  |
| TestSuppliersLogistics.test_inject_event_validation_and_labeling | inject event validation and labeling | **PASS** |  |
| TestSuppliersLogistics.test_other_event_types_build_effects | other event types build effects | **PASS** |  |
| TestSuppliersLogistics.test_shipments_delay_detection | shipments delay detection | **PASS** |  |
| TestSuppliersLogistics.test_supplier_metrics | supplier metrics | **PASS** |  |
| TestUISmoke.test_click_through_actions | All buttons/forms 'pressed' - exercises run/generate/inject/demo branches (errors from empty forms are caught by the views). | **PASS** |  |
| TestUISmoke.test_css_animation_contract | css animation contract | **PASS** |  |
| TestUISmoke.test_hero_header_contract | hero header contract | **PASS** |  |
| TestUISmoke.test_pages_render | pages render | **PASS** |  |

## Coverage of the acceptance list
Inventory CRUD (TestInventory) | forecasting (TestForecasting) | stock-out calculations (TestStockout) | expiry detection/FEFO (TestExpiry) | supplier analysis & shipment disruptions (TestSuppliersLogistics) | redistribution optimisation incl. infeasible case (TestOptimizer) | scenario simulation (TestSimulation) | approval workflow & audit (TestApprovals) | dashboard KPI reconciliation, alerts, assistant (TestDashboardAlertsAssistant) | auth/roles (TestAuth) | data validation (TestData) | every Streamlit page's render code against the real engine (TestUISmoke).

## NOT verified in the build sandbox (no internet / no GUI) - run locally
- **Real Streamlit launch and visual check.** Streamlit, Plotly, OR-Tools and pytest could not be installed in the sandbox. Page code was executed against a *fake* Streamlit/Plotly (tests/fake_streamlit.py), which catches Python/data errors but NOT layout, CSS rendering or the header animation in a real browser. Command: `python -m streamlit run app.py`.
- **OR-Tools backend** (the SciPy HiGHS backend was the one tested; same model). Command: `pip install ortools` then rerun the tests - `summary.backend` will read `ortools`.
- **statsmodels Holt-Winters** (optional model, skipped when unavailable).
- **pytest runner**: `python -m pytest -q` (tests are plain `unittest` classes).

## Known limitations
- Synthetic data: metrics describe the generator, not real facilities.
- Single 30-day forecast test window per series.
- Optimizer is single-period; transfers are booked at execution (no in-transit state).
- Heuristic scores/weights are design choices, not validated.
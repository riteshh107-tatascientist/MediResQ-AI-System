# Research Foundation, Assumptions & Differentiation

> Status note: this document records the concepts implemented and the references to read and cite. Reference pages were **not** reproduced or summarised line-by-line here; verify each before quoting in your submission. No statistics, deployments or hospital partnerships are claimed anywhere in this project.

## Reference list (starting points provided + standard texts)
| Topic | Reference |
|---|---|
| SAP IBP features | https://www.sap.com/products/scm/integrated-business-planning/features.html |
| SAP IBP documentation | https://help.sap.com/docs/sap_integrated_business_planning |
| WHO medicines supply | https://www.who.int/teams/health-product-policy-and-standards/medicines-selection-ip-and-affordability/medicines-policy/medicines-supply |
| NHSRC India - IT-enabled medicine supply chain assessment | https://www.nhsrcindia.org/sites/default/files/2025-08/Assessment%20of%20IT-enabled%20Supply%20Chain%20Management%20of%20Medicines.pdf |
| Forecast accuracy (MAE/RMSE/WAPE) | Hyndman & Athanasopoulos, *Forecasting: Principles and Practice* (otexts.com/fpp3) |
| Safety stock / reorder point | Silver, Pyke & Peterson, *Inventory and Production Management in Supply Chains* |

## Concepts implemented
- **FEFO** - issue/transfer the earliest-expiring *usable* batch first; expired and quarantined batches are never recommended.
- **Safety stock** `SS = z * sqrt(L*sigma_d^2 + (d*sigma_L)^2)` with z = 1.28 / 1.65 / 2.05 for criticality 1/2/3 (service-level assumption).
- **Reorder point** `ROP = d*L + SS`; order-up-to `= ROP + 14 days demand` (review-period assumption).
- **Forecasting** - baselines (moving average, seasonal naive) vs SES with weekly index, Random Forest, Gradient Boosting; chronological train/validation/test; WAPE preferred because intermittent demand makes MAPE unstable.
- **Stock-out probability** - Monte-Carlo with normal demand noise (model-based, not calibrated); separate from the heuristic 0-100 risk score.
- **Redistribution** - integer transportation-type program with reserve, expiry/shelf-life, cold-chain, lane-capacity and timing constraints.
- **Scenario simulation** - deterministic projection from forecasts with a standing reorder policy.
- **Policy comparison** - Monte-Carlo with common random numbers (bootstrapped demand and lead times).

## Assumptions
Synthetic data; lead times from synthetic PO history; transfers booked at execution (transit not modelled in the DB); one primary supplier per medicine in simulation; warehouses keep `WH_RESERVE_DAYS` (2) of network demand; transferred batches must keep >= 14 days shelf life on arrival; heuristic weights are design choices.

## Limitations
No real data; ETS is a custom lightweight implementation (statsmodels Holt-Winters optional); prediction intervals are assumption-based; optimizer is single-period (no multi-period flow); no patient-level or clinical logic; resilience index and risk score are heuristics.

## Differentiation
Most dashboards stop at "what is low". MediResQ AI (1) explains *why* each alert fires, (2) separates heuristic scores from model probabilities, (3) produces a *feasible, expiry-safe, cost-minimal* transfer plan or explains infeasibility, (4) requires human approval with an audit trail, (5) quantifies trade-offs (service vs inventory cost) honestly in simulation.

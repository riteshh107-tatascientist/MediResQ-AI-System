# Architecture

```
Streamlit UI (app.py + mediresq/views/*)  --  CSS hero with left-to-right light sweep (mediresq/ui.py)
        |
Services: inventory | expiry | forecasting | stockout | suppliers | logistics | effects
          state (snapshot + projection) | optimizer | recovery | simulator | alerts | approvals | analytics | assistant | demo
        |
Database abstraction (mediresq/db.py, sqlite3; ANSI SQL, FK + CHECK constraints)  -> PostgreSQL-ready by re-implementing Database
        |
SQLite file data/mediresq.db  <- seeded from synthetic generator (mediresq/datagen.py) ; CSV export in data/csv
```
**Data flow:** consumption history -> fast ETS forecasts (`forecasting.fast_forecast_all`) -> `State` (usable stock, inbound shipments with disruption effects, forecasts) -> stockout risk / optimizer / simulator / alerts -> recommendations (Pending) -> human decision -> execution -> audit log.

**Disruptions** are `Effects` objects layered over the baseline; injected events are stored in `disruption_events` with `simulated=1` and never overwrite real shipments.

**Optimizer** (`optimizer.py`): integer program `min sum cost*x + sum penalty*u` s.t. shortage cover, source reserve, expiry/quarantine eligibility, cold-chain lanes, lane capacity, timing. Backend: OR-Tools (SCIP/CBC) when installed, else SciPy HiGHS `milp` - same model, same constraints.

**Security:** PBKDF2-HMAC-SHA256 (200k iterations, per-user salt), role permissions, parameterised SQL, input validation, CSV upload validation (columns, types, ranges, FK sets, size), audit log, `.env` for config, no patient data.

**Deviations from the original brief (disclosed):** `sqlite3` + a thin abstraction instead of SQLAlchemy and plain-Python validation instead of Pydantic (neither could be installed/tested in the build sandbox); FastAPI not used (not needed for a single Streamlit process); ETS implemented directly, statsmodels Holt-Winters optional.

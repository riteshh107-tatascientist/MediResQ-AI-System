# MediResQ AI
**Predict. Protect. Prevent Shortages.** - AI-powered essential medicine supply chain resilience.
SAP Hackfest 2026 - West & Central Region | TIT BHOPAL | CSE (DATA SCIENCE) | Developer: Ritesh Kumar Singh (individual project)

> Independent Python prototype on **synthetic data**. No SAP endorsement, partnership or integration is claimed (see `docs/SAP_ALIGNMENT.md`). Inventory decision support only - not a clinical system; no patient data.

## What's inside
Executive dashboard (10 live KPIs + resilience index) | medicine inventory CRUD | batch/FEFO/expiry intelligence | demand forecasting (Moving Average, Seasonal Naive, ETS, Random Forest, Gradient Boosting; MAE/RMSE/WAPE; chronological split) | stock-out early warning with reasons (heuristic score **and** Monte-Carlo probability, clearly distinguished) | supplier intelligence | shipment & disruption monitoring (simulated events labelled) | **redistribution optimizer** (OR-Tools / SciPy MILP) | AI recovery planner | what-if simulator (baseline vs disrupted vs recovered) | alert centre | approval & audit centre | roles + login | analytics incl. controlled **policy comparison** | data-grounded assistant (no LLM/API) | one-click **Judge demo**.

Extra "winner-level" additions beyond the brief: resilience index, Monte-Carlo stock-out probability, cold-chain and shelf-life-on-arrival constraints, infeasibility explanations, executable approved transfers/POs, policy-comparison simulation with honest trade-offs, CSV upload validation, reproducible data + automated docs/tests.

## Run on Windows (VS Code + PowerShell)
Requires Python 3.10+ (https://python.org, tick "Add to PATH"). Open the `MediResQ-AI` folder in VS Code, then a PowerShell terminal:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```
The database is created and seeded automatically on first launch (or run `python scripts/init_db.py`). Browser opens at http://localhost:8501.

**If activation is blocked** ("running scripts is disabled"): allow scripts for *this PowerShell window only* (no permanent security change):
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```
or skip activation and call the venv directly: `.venv\Scripts\python.exe -m streamlit run app.py`, or activate from Command Prompt with `.venv\Scripts\activate.bat`.

## Demo accounts (local, synthetic - change in `.env`)
| user | role | password |
|---|---|---|
| admin | Administrator | `MediResQ@Demo2026` |
| scm | Supply Chain Manager | same |
| whm | Warehouse Manager | same |
| viewer | Viewer | same |
Override with `MEDIRESQ_DEMO_PASSWORD` in `.env` (copy `.env.example`) before first run.

## Tests
```powershell
python -m unittest discover -s tests -v     # or: python -m pytest -q
python scripts/make_docs.py                  # regenerates docs/TEST_REPORT.md + DATA_DICTIONARY.md from a real run
python scripts/evaluate_models.py            # regenerates docs/MODEL_EVALUATION.md
```
See `docs/TEST_REPORT.md` for what was and was **not** verified in the build sandbox (notably: real Streamlit launch/visual check and OR-Tools backend must be confirmed locally).

## Images
The homepage ships locally generated SVG illustrations (`assets/images/*.svg`, work offline). To use real photos, drop royalty-free images named `hero.jpg`, `f_inventory.jpg`, `f_forecast.jpg`, `f_supplier.jpg`, `f_recovery.jpg` (webp/png also work) into `assets/images/` - the app prefers them automatically. Use only images you have rights to; do not imply any pictured facility is a partner. Regenerate SVGs with `python scripts/make_assets.py`.

## Structure
`app.py` entry | `mediresq/` engine (db, datagen, inventory, expiry, forecasting, state, stockout, suppliers, logistics, optimizer, recovery, simulator, alerts, approvals, analytics, assistant, auth, ui, views/) | `data/csv` synthetic dataset | `docs/` research, architecture, design thinking, BMC, SAP alignment, data dictionary, model evaluation, test report, demo workflow | `tests/` | `scripts/`.

## Known limitations
Synthetic data only; single-period optimizer; transfers booked at execution; heuristic scores/weights unvalidated; prediction intervals assumption-based; SQLite (PostgreSQL via re-implementing `mediresq/db.py`); SQLAlchemy/Pydantic/FastAPI from the original wish-list not used (see `docs/ARCHITECTURE.md`).

## Event note
I could not locate an official SAP Hackfest 2026 West & Central rules page while building. Check the organiser's portal for submission format, **team-size rules (this is a solo entry)**, judging criteria and deadlines (you noted 17 Nov 2026).

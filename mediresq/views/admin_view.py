import io
from datetime import date

import pandas as pd

from .. import auth, config, datagen, ui

REQUIRED = {"consumption": ["date", "facility_id", "medicine_id", "qty"], "batches": ["facility_id", "medicine_id", "batch_no", "mfg_date", "expiry_date", "qty"]}


def validate_upload(table, df, db):
    """Returns (ok, errors). Strict column + type + range + FK checks before any import."""
    errs = []
    if table not in REQUIRED:
        return False, ["Unsupported table"]
    miss = [c for c in REQUIRED[table] if c not in df.columns]
    if miss:
        return False, [f"Missing columns: {miss}"]
    if len(df) > 200_000:
        errs.append("File too large (max 200,000 rows).")
    if pd.to_numeric(df.qty, errors="coerce").isna().any() or (pd.to_numeric(df.qty, errors="coerce") < 0).any():
        errs.append("qty must be numeric and >= 0.")
    for col in [c for c in ("date", "mfg_date", "expiry_date") if c in df.columns]:
        if pd.to_datetime(df[col], errors="coerce").isna().any():
            errs.append(f"{col} has invalid dates.")
    fac = set(db.df("SELECT facility_id FROM facilities").facility_id)
    med = set(db.df("SELECT medicine_id FROM medicines").medicine_id)
    if not set(df.facility_id).issubset(fac):
        errs.append("Unknown facility_id values.")
    if not set(df.medicine_id).issubset(med):
        errs.append("Unknown medicine_id values.")
    if table == "batches" and not errs and (pd.to_datetime(df.expiry_date) <= pd.to_datetime(df.mfg_date)).any():
        errs.append("expiry_date must be after mfg_date.")
    return (not errs), errs


def render(c):
    st, db = c.st, c.db
    st.markdown(ui.hero_app("Administration", desc="Users, data validation and CSV import."), unsafe_allow_html=True)
    if not c.can("manage_users"):
        st.error("Administrator access required.")
        return
    t1, t2, t3 = st.tabs(["Users", "Data validation", "CSV import"])
    with t1:
        st.dataframe(db.df("SELECT user_id, username, role, active, created_at FROM users"), use_container_width=True, hide_index=True)
        with st.form("nu"):
            u = st.text_input("Username")
            p = st.text_input("Password (min 10 chars, upper+lower+digit)", type="password")
            r = st.selectbox("Role", auth.ROLES)
            if st.form_submit_button("Create user"):
                try:
                    auth.create_user(db, u, p, r, c.user["username"]); st.success("User created.")
                except Exception as e:
                    st.error(str(e))
    with t2:
        if st.button("Run data validation checks"):
            for name, ok, det in datagen.validate_database(db):
                (st.success if ok else st.error)(f"{name} {det}")
        st.caption("Data origin: " + str(db.scalar("SELECT value FROM meta WHERE key='data_origin'")))
    with t3:
        tbl = st.selectbox("Target table", list(REQUIRED))
        f = st.file_uploader("CSV file", type=["csv"])
        if f is not None:
            try:
                df = pd.read_csv(io.BytesIO(f.getvalue()))
                ok, errs = validate_upload(tbl, df, db)
                if ok:
                    st.success(f"Validation passed ({len(df)} rows).")
                    if st.button("Import validated rows"):
                        if tbl == "batches":
                            df = df.assign(status="active", unit_cost=None)[["facility_id", "medicine_id", "batch_no", "mfg_date", "expiry_date", "qty", "status", "unit_cost"]]
                        else:
                            df = df.assign(unmet_qty=df["unmet_qty"] if "unmet_qty" in df.columns else 0)[["date", "facility_id", "medicine_id", "qty", "unmet_qty"]]
                        db.insert_df(tbl, df)
                        db.audit(c.user["username"], "csv_import", tbl, "", f"{len(df)} rows")
                        c.bump()
                        st.success("Imported.")
                else:
                    for e in errs:
                        st.error(e)
            except Exception as e:
                st.error(f"Could not read file safely: {e}")

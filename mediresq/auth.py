"""Password hashing (PBKDF2-HMAC-SHA256, stdlib) and role-based permissions."""
import hashlib
import hmac
import os
import re
from datetime import datetime

ITER = 200_000
ROLES = ["admin", "supply_manager", "warehouse_manager", "viewer"]
ROLE_LABEL = {"admin": "Administrator", "supply_manager": "Supply Chain Manager",
              "warehouse_manager": "Warehouse Manager", "viewer": "Viewer"}
PERMS = {
    "admin": {"view", "edit_inventory", "delete_inventory", "approve_transfer", "approve_procure",
              "manage_users", "inject_events", "upload_data", "run_plan", "ack_alerts"},
    "supply_manager": {"view", "edit_inventory", "approve_transfer", "approve_procure",
                       "inject_events", "run_plan", "ack_alerts"},
    "warehouse_manager": {"view", "edit_inventory", "approve_transfer", "ack_alerts"},
    "viewer": {"view"},
}


def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITER).hex()
    return h, salt


def verify_password(password, h, salt):
    cand, _ = hash_password(password, salt)
    return hmac.compare_digest(cand, h)


def validate_new_password(pw):
    if len(pw) < 10:
        return "Password must be at least 10 characters."
    if not (re.search(r"[A-Z]", pw) and re.search(r"[a-z]", pw) and re.search(r"\d", pw)):
        return "Password needs upper-case, lower-case and a digit."
    return None


def create_user(db, username, password, role, actor="system"):
    if role not in ROLES:
        raise ValueError("Invalid role")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username or ""):
        raise ValueError("Username must be 3-32 chars (letters, digits, _ . -)")
    err = validate_new_password(password)
    if err:
        raise ValueError(err)
    h, s = hash_password(password)
    db.execute("INSERT INTO users(username,password_hash,salt,role,active,created_at) VALUES(?,?,?,?,1,?)",
               (username, h, s, role, datetime.now().isoformat(timespec="seconds")))
    db.audit(actor, "create_user", "user", username, f"role={role}")


def authenticate(db, username, password):
    """Returns {'username','role'} or None. Constant-ish time: hashes even for unknown users."""
    df = db.df("SELECT * FROM users WHERE username=? AND active=1", (username or "",))
    if df.empty:
        hash_password(password or "", "00" * 16)
        db.audit(username or "?", "login_failed", "user", username or "?", "unknown user")
        return None
    r = df.iloc[0]
    if verify_password(password or "", r.password_hash, r.salt):
        db.audit(r.username, "login", "user", r.username)
        return {"username": r.username, "role": r.role}
    db.audit(r.username, "login_failed", "user", r.username, "bad password")
    return None


def can(user, perm):
    return bool(user) and perm in PERMS.get(user["role"], set())

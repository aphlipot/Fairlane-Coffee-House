"""Accounts, roles, login, and password reset (email link or security question)."""
import hashlib
import hmac
import re
import secrets as pysecrets
from datetime import timedelta

import streamlit as st

from core import db, hours, mailer
from core.config import secret, secret_section

ROLES = {"customer": "Customer", "staff": "Staff", "manager": "Manager"}
SECURITY_QUESTIONS = [
    "What was the name of your first pet?",
    "What city were you born in?",
    "What was your first car?",
    "What is your favorite coffee drink?",
    "What was the name of your elementary school?",
]
RESET_MINUTES = 30
PUBLIC_FIELDS = "id, username, email, full_name, phone, role, created_at"


# ---------- hashing ----------
def _pbkdf2(value, salt):
    return hashlib.pbkdf2_hmac("sha256", value.encode(), salt.encode(), 200_000).hex()


def hash_secret(value):
    salt = pysecrets.token_hex(16)
    return f"pbkdf2${salt}${_pbkdf2(value, salt)}"


def check_secret(value, stored):
    try:
        _, salt, digest = stored.split("$")
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(_pbkdf2(value, salt), digest)


def _normalize_answer(answer):
    return " ".join((answer or "").lower().split())


def password_problem(pw):
    if len(pw) < 8:
        return "Use at least 8 characters."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Include at least one letter and one number."
    return None


# ---------- seed accounts ----------
@st.cache_resource
def ensure_seed_accounts():
    """Create a manager and a staff login the first time the database is used."""
    seeds = [
        ("manager", secret_section("admin"), "manager", "Fairlane#2026", "manager@fairlanecoffee.example", "Café Manager"),
        ("staff", secret_section("staff"), "barista", "Barista#2026", "barista@fairlanecoffee.example", "Barista"),
    ]
    for role, cfg, user, pw, email, name in seeds:
        username = cfg.get("username", user)
        if db.one("SELECT id FROM users WHERE username = ?", (username,)):
            continue
        db.execute(
            "INSERT INTO users (username, email, full_name, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
            (username, cfg.get("email", email), cfg.get("full_name", name),
             hash_secret(cfg.get("password", pw)), role, hours.iso(hours.now())),
        )
    return True


# ---------- session ----------
def current_user():
    """Logged-in user, refreshed from the database so role changes apply right away."""
    u = st.session_state.get("user")
    if not u:
        return None
    fresh = db.one(f"SELECT {PUBLIC_FIELDS} FROM users WHERE id = ?", (u["id"],))
    if not fresh:
        st.session_state.pop("user", None)
    else:
        st.session_state["user"] = fresh
    return fresh


def find_user(identifier):
    ident = (identifier or "").strip()
    return db.one(
        "SELECT * FROM users WHERE lower(username) = lower(?) OR lower(email) = lower(?)", (ident, ident)
    )


def login(identifier, password):
    row = find_user(identifier)
    if row and check_secret(password, row["password_hash"]):
        user = {k: row[k] for k in PUBLIC_FIELDS.split(", ")}
        st.session_state["user"] = user
        st.session_state["just_logged_in"] = True
        return user
    return None


def logout():
    for key in ["user", "chat_history", "interview", "reset_verified_user"]:
        st.session_state.pop(key, None)


# ---------- registration and profile ----------
def register(username, email, full_name, phone, password, question, answer):
    username, email = username.strip(), email.strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username):
        return False, "Usernames are 3 to 30 characters: letters, numbers, dot, dash, or underscore."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return False, "Enter a valid email address."
    problem = password_problem(password)
    if problem:
        return False, problem
    if not _normalize_answer(answer):
        return False, "Answer the security question. It lets you reset your password without email."
    if db.one("SELECT id FROM users WHERE lower(username) = lower(?)", (username,)):
        return False, "That username is taken."
    if db.one("SELECT id FROM users WHERE lower(email) = lower(?)", (email,)):
        return False, "An account with that email already exists. Try resetting your password."
    db.execute(
        """INSERT INTO users (username, email, full_name, phone, password_hash, role,
           security_question, security_answer_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (username, email, full_name.strip(), phone.strip(), hash_secret(password), "customer",
         question, hash_secret(_normalize_answer(answer)), hours.iso(hours.now())),
    )
    return True, "Account created."


def update_profile(user_id, full_name, email, phone):
    email = email.strip().lower()
    clash = db.one("SELECT id FROM users WHERE lower(email) = ? AND id != ?", (email, user_id))
    if clash:
        return False, "Another account uses that email."
    db.execute("UPDATE users SET full_name = ?, email = ?, phone = ? WHERE id = ?",
               (full_name.strip(), email, phone.strip(), user_id))
    return True, "Profile saved."


def set_password(user_id, new_password):
    problem = password_problem(new_password)
    if problem:
        return False, problem
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_secret(new_password), user_id))
    return True, "Password updated."


def change_password(user_id, current, new):
    row = db.one("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    if not row or not check_secret(current, row["password_hash"]):
        return False, "Current password is incorrect."
    return set_password(user_id, new)


def set_security_question(user_id, question, answer):
    if not _normalize_answer(answer):
        return False, "Enter an answer."
    db.execute("UPDATE users SET security_question = ?, security_answer_hash = ? WHERE id = ?",
               (question, hash_secret(_normalize_answer(answer)), user_id))
    return True, "Security question saved."


def set_role(user_id, role):
    if role in ROLES:
        db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def all_users():
    return db.query(f"SELECT {PUBLIC_FIELDS} FROM users ORDER BY created_at DESC")


# ---------- password reset: email link ----------
def _token_hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def create_reset_token(user_id):
    raw = pysecrets.token_urlsafe(32)
    now = hours.now()
    db.execute("UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0", (user_id,))
    db.execute(
        "INSERT INTO password_resets (user_id, token_hash, expires_at, created_at) VALUES (?,?,?,?)",
        (user_id, _token_hash(raw), hours.iso(now + timedelta(minutes=RESET_MINUTES)), hours.iso(now)),
    )
    return raw


def reset_link(raw):
    base = str(secret("APP_URL", "http://localhost:8501")).rstrip("/")
    return f"{base}/?reset_token={raw}"


def send_reset_email(identifier):
    """Email a reset link. Returns (sent, message). The message never reveals whether the account exists."""
    generic = "If an account matches, a reset link is on its way. The link expires in 30 minutes."
    user = find_user(identifier)
    if not user:
        return True, generic
    raw = create_reset_token(user["id"])
    body = (
        f"Hi {user['full_name'] or user['username']},\n\n"
        "We received a request to reset your Fairlane Coffee House password. "
        f"Open this link within {RESET_MINUTES} minutes to choose a new one:\n\n"
        f"{reset_link(raw)}\n\n"
        "If you did not ask for this, you can ignore this email and your password stays the same.\n\n"
        "Fairlane Coffee House\n19000 Hubbard Drive, Dearborn, MI"
    )
    ok, err = mailer.send(user["email"], "Reset your Fairlane Coffee House password", body)
    if not ok:
        return False, f"The reset email could not be sent. {err}"
    return True, generic


def user_for_token(raw):
    row = db.one(
        "SELECT * FROM password_resets WHERE token_hash = ? AND used = 0", (_token_hash(raw or ""),)
    )
    if not row or hours.parse(row["expires_at"]) < hours.now():
        return None
    return db.one(f"SELECT {PUBLIC_FIELDS} FROM users WHERE id = ?", (row["user_id"],))


def reset_with_token(raw, new_password):
    user = user_for_token(raw)
    if not user:
        return False, "This reset link is invalid or has expired. Request a new one."
    ok, msg = set_password(user["id"], new_password)
    if ok:
        db.execute("UPDATE password_resets SET used = 1 WHERE token_hash = ?", (_token_hash(raw),))
    return ok, msg


# ---------- password reset: security question ----------
def security_question_for(identifier):
    user = find_user(identifier)
    if user and user["security_question"] and user["security_answer_hash"]:
        return user
    return None


def check_security_answer(user, answer):
    return check_secret(_normalize_answer(answer), user["security_answer_hash"])

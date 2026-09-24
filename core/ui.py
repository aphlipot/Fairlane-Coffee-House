"""Shared layout pieces: styles, sidebar login, access checks."""
import streamlit as st

from core import ai, auth, hours

CSS = """
<style>
:root { --um-blue: #00274C; --um-maize: #FFCB05; }
h1, h2, h3 { color: var(--um-blue); letter-spacing: -0.01em; }
.fch-lead { font-size: 1.05rem; color: #3B4A60; max-width: 62ch; margin-top: -0.4rem; }
.fch-status { display: inline-block; padding: 0.35rem 0.85rem; border-radius: 999px; font-weight: 700; font-size: 0.95rem; }
.fch-open { background: var(--um-maize); color: var(--um-blue); }
.fch-closed { background: #E3E8EF; color: var(--um-blue); }
.fch-hero { background: var(--um-blue); color: #fff; padding: 2.4rem 2rem 1.9rem 2rem; border-radius: 0.5rem;
            border-bottom: 6px solid var(--um-maize); margin-bottom: 1.2rem; }
.fch-hero h1 { color: var(--um-maize); font-size: 2.7rem; line-height: 1.08; margin: 0 0 0.6rem 0; }
.fch-hero p { color: #E8EDF4; font-size: 1.15rem; max-width: 52ch; margin: 0; }
.fch-muted { color: #5B6A7E; font-size: 0.9rem; }
[data-testid="stMetric"] { border-left: 4px solid var(--um-maize); padding-left: 0.75rem; }
[data-testid="stMetricValue"] { color: var(--um-blue); }
section[data-testid="stSidebar"] button[kind="primary"],
section[data-testid="stSidebar"] button[kind="primaryFormSubmit"] { color: var(--um-blue) !important; font-weight: 700; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def header(title, lead=None):
    st.title(title)
    if lead:
        st.markdown(f"<p class='fch-lead'>{lead}</p>", unsafe_allow_html=True)


def status_pill():
    is_open, text = hours.status_line()
    cls = "fch-open" if is_open else "fch-closed"
    st.markdown(f"<span class='fch-status {cls}'>{text}</span>", unsafe_allow_html=True)


def money(x):
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def ai_mode_note():
    if not ai.enabled():
        st.caption("Running in basic mode. Add OPENAI_API_KEY to the app secrets to turn on ChatGPT features.")


def require_login(message="Log in to use this page."):
    user = auth.current_user()
    if not user:
        st.info(message)
        c1, c2 = st.columns(2)
        with c1:
            st.page_link("views/account.py", label="Log in or create an account", icon=":material/person:")
        st.stop()
    return user


def require_role(*roles):
    user = require_login()
    if user["role"] not in roles:
        st.error("You don't have access to this page.")
        st.stop()
    return user


def sidebar_account():
    with st.sidebar:
        user = auth.current_user()
        if user:
            st.markdown(f"**{user['full_name'] or user['username']}**")
            st.caption(f"Signed in as {user['username']} ({auth.ROLES[user['role']]})")
            if st.button("Log out", width="stretch"):
                auth.logout()
                st.rerun()
            return
        st.markdown("**Member login**")
        with st.form("sidebar_login"):
            ident = st.text_input("Username or email")
            pw = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")
        if submitted:
            if auth.login(ident, pw):
                st.rerun()
            else:
                st.error("Username or password is incorrect.")
        if st.button("Forgot password?", type="tertiary"):
            st.session_state["account_mode"] = "Reset password"
            st.switch_page("views/account.py")
        if st.button("Create an account", type="tertiary"):
            st.session_state["account_mode"] = "Create account"
            st.switch_page("views/account.py")


def render_token_reset(token):
    """Full-page form shown when someone opens an emailed reset link."""
    st.title("Choose a new password")
    user = auth.user_for_token(token)
    if not user:
        st.error("This reset link is invalid or has expired. Request a new one from the login panel.")
        if st.button("Back to the app"):
            st.query_params.clear()
            st.rerun()
        return
    st.write(f"Resetting the password for **{user['username']}**.")
    with st.form("token_reset"):
        p1 = st.text_input("New password", type="password", help="At least 8 characters with a letter and a number.")
        p2 = st.text_input("Confirm new password", type="password")
        done = st.form_submit_button("Save new password", type="primary")
    if done:
        if p1 != p2:
            st.error("The passwords don't match.")
        else:
            ok, msg = auth.reset_with_token(token, p1)
            if ok:
                st.success("Password saved. You can log in now.")
                st.query_params.clear()
                st.button("Go to the app")
            else:
                st.error(msg)

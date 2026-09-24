import streamlit as st

from core import auth, mailer, ui

user = auth.current_user()

if user:
    ui.header("Account", f"Signed in as {user['username']}.")
    profile, password, security = st.tabs(["Profile", "Password", "Security question"])
    with profile:
        with st.form("profile"):
            full_name = st.text_input("Full name", value=user["full_name"] or "")
            email = st.text_input("Email", value=user["email"])
            phone = st.text_input("Phone", value=user["phone"] or "")
            if st.form_submit_button("Save profile", type="primary"):
                ok, msg = auth.update_profile(user["id"], full_name, email, phone)
                (st.success if ok else st.error)(msg)
    with password:
        with st.form("change_pw", clear_on_submit=True):
            cur = st.text_input("Current password", type="password")
            new = st.text_input("New password", type="password", help="At least 8 characters with a letter and a number.")
            conf = st.text_input("Confirm new password", type="password")
            if st.form_submit_button("Change password", type="primary"):
                if new != conf:
                    st.error("The new passwords don't match.")
                else:
                    ok, msg = auth.change_password(user["id"], cur, new)
                    (st.success if ok else st.error)(msg)
    with security:
        st.caption("Used to reset your password if email isn't available.")
        with st.form("sec_q", clear_on_submit=True):
            q = st.selectbox("Question", auth.SECURITY_QUESTIONS)
            a = st.text_input("Answer", type="password")
            if st.form_submit_button("Save security question"):
                ok, msg = auth.set_security_question(user["id"], q, a)
                (st.success if ok else st.error)(msg)
    st.stop()

ui.header("Account", "Log in, create an account, or reset your password.")
modes = ["Log in", "Create account", "Reset password"]
if st.session_state.get("account_mode") not in modes:
    st.session_state["account_mode"] = "Log in"
mode = st.segmented_control("What do you want to do?", modes, key="account_mode", label_visibility="collapsed")

if mode == "Log in" or mode is None:
    with st.form("page_login"):
        ident = st.text_input("Username or email")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Log in", type="primary"):
            if auth.login(ident, pw):
                st.switch_page("views/home.py")
            st.error("Username or password is incorrect.")

elif mode == "Create account":
    with st.form("register"):
        c1, c2 = st.columns(2)
        username = c1.text_input("Username")
        full_name = c2.text_input("Full name")
        email = c1.text_input("Email")
        phone = c2.text_input("Phone (optional)")
        pw = c1.text_input("Password", type="password", help="At least 8 characters with a letter and a number.")
        pw2 = c2.text_input("Confirm password", type="password")
        q = st.selectbox("Security question", auth.SECURITY_QUESTIONS)
        a = st.text_input("Answer", type="password", help="Lets you reset your password without email.")
        if st.form_submit_button("Create account", type="primary"):
            if pw != pw2:
                st.error("The passwords don't match.")
            else:
                ok, msg = auth.register(username, email, full_name, phone, pw, q, a)
                if ok:
                    auth.login(username, pw)
                    st.switch_page("views/home.py")
                st.error(msg)

else:
    st.subheader("Reset your password")
    if mailer.configured():
        st.markdown("**Get a reset link by email**")
        with st.form("email_reset"):
            ident = st.text_input("Username or email")
            if st.form_submit_button("Email me a reset link", type="primary"):
                ok, msg = auth.send_reset_email(ident)
                (st.success if ok else st.error)(msg)
        st.markdown("**Or answer your security question**")
    else:
        st.caption("Answer the security question you chose when you signed up.")

    attempts = st.session_state.setdefault("reset_attempts", 0)
    verified = st.session_state.get("reset_verified_user")

    if verified:
        with st.form("sq_new_pw"):
            st.write(f"Choose a new password for **{verified['username']}**.")
            p1 = st.text_input("New password", type="password", help="At least 8 characters with a letter and a number.")
            p2 = st.text_input("Confirm new password", type="password")
            if st.form_submit_button("Save new password", type="primary"):
                if p1 != p2:
                    st.error("The passwords don't match.")
                else:
                    ok, msg = auth.set_password(verified["id"], p1)
                    if ok:
                        st.session_state.pop("reset_verified_user", None)
                        st.session_state["reset_attempts"] = 0
                        st.success("Password saved. Log in with your new password.")
                    else:
                        st.error(msg)
    elif attempts >= 5:
        st.error("Too many incorrect answers. Email fairlanecoffeehouse@gmail.com for help, or try again later.")
    else:
        ident = st.text_input("Username or email", key="sq_ident")
        candidate = auth.security_question_for(ident) if ident else None
        if ident and not candidate:
            st.caption("No security question is on file for that account. Use the email link, or contact us.")
        if candidate:
            with st.form("sq_answer"):
                st.write(candidate["security_question"])
                ans = st.text_input("Answer", type="password")
                if st.form_submit_button("Continue"):
                    if auth.check_security_answer(candidate, ans):
                        st.session_state["reset_verified_user"] = {"id": candidate["id"], "username": candidate["username"]}
                        st.rerun()
                    else:
                        st.session_state["reset_attempts"] = attempts + 1
                        st.error("That answer doesn't match.")

import streamlit as st

from core import auth, hours, ui

ui.header("Users and roles", "Give staff access to the Kitchen and Service desk, or make someone a manager.")
me = ui.require_role("manager")

users = auth.all_users()
search = st.text_input("Search by name, username, or email")
if search:
    s = search.lower()
    users = [u for u in users if s in (u["username"] + u["email"] + (u["full_name"] or "")).lower()]

roles = list(auth.ROLES)
for u in users[:100]:
    c = st.columns([3, 3, 2])
    c[0].markdown(f"**{u['full_name'] or u['username']}**  \n{u['username']}")
    c[1].write(f"{u['email']}  \nJoined {hours.fmt_dt(u['created_at'])}")
    new = c[2].selectbox("Role", roles, index=roles.index(u["role"]), format_func=auth.ROLES.get,
                         key=f"role_{u['id']}", disabled=u["id"] == me["id"], label_visibility="collapsed")
    if new != u["role"]:
        auth.set_role(u["id"], new)
        st.toast(f"{u['username']} is now {auth.ROLES[new]}.")
        st.rerun()
st.caption("You can't change your own role, so there is always at least one manager.")

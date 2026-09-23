"""Fairlane Coffee House: Streamlit entry point."""
import streamlit as st

from core import auth, db, ui

st.set_page_config(page_title="Fairlane Coffee House", page_icon="☕", layout="wide")
db.init()
auth.ensure_seed_accounts()
ui.inject_css()

# Emailed reset links land here as ?reset_token=...
token = st.query_params.get("reset_token")
if token:
    ui.render_token_reset(token)
    st.stop()

user = auth.current_user()
role = user["role"] if user else None

cafe = [
    st.Page("views/home.py", title="Home", icon=":material/storefront:", default=True),
    st.Page("views/menu.py", title="Menu", icon=":material/local_cafe:"),
    st.Page("views/order.py", title="Order", icon=":material/shopping_bag:"),
    st.Page("views/reservations.py", title="Reserve a table", icon=":material/table_restaurant:"),
    st.Page("views/assistant.py", title="Ask Fairlane", icon=":material/forum:"),
    st.Page("views/feedback.py", title="Feedback", icon=":material/rate_review:"),
    st.Page("views/careers.py", title="Careers", icon=":material/badge:"),
    st.Page("views/business_model.py", title="Our business model", icon=":material/lightbulb:"),
]
account = [
    st.Page("views/my_orders.py", title="My orders", icon=":material/receipt_long:"),
    st.Page("views/account.py", title="Account", icon=":material/person:"),
]
sections = {"Café": cafe, "You": account}
if role in ("staff", "manager"):
    sections["Staff"] = [
        st.Page("views/kitchen.py", title="Kitchen", icon=":material/coffee_maker:"),
        st.Page("views/service.py", title="Service desk", icon=":material/room_service:"),
    ]
if role == "manager":
    sections["Management"] = [
        st.Page("views/insights.py", title="Insights", icon=":material/insights:"),
        st.Page("views/marketing.py", title="Marketing studio", icon=":material/campaign:"),
        st.Page("views/hiring.py", title="Hiring", icon=":material/group_add:"),
        st.Page("views/team.py", title="Users and roles", icon=":material/admin_panel_settings:"),
    ]

page = st.navigation(sections)
ui.sidebar_account()
page.run()

import streamlit as st

from core import feedback, hours, orders, ui

ui.header("Feedback", "Tell us how we did. A manager reads every comment.")
user = ui.require_login("Log in to leave feedback so we can follow up with you.")

SENTIMENT_TEXT = {"positive": "Positive", "negative": "Negative", "mixed": "Mixed", "neutral": "Neutral"}

with st.form("feedback_form", clear_on_submit=True):
    st.write("How was your visit?")
    stars = st.feedback("stars")
    recent = orders.for_user(user["id"], active=False)[:10] + orders.for_user(user["id"], active=True)
    order_choice = st.selectbox(
        "Related order (optional)", [None] + [o["id"] for o in recent],
        format_func=lambda oid: "None" if oid is None else f"Order #{oid}",
    )
    comment = st.text_area("Comments", placeholder="What did you order, and what stood out?")
    sent = st.form_submit_button("Send feedback", type="primary")

if sent:
    if not comment.strip():
        st.error("Add a comment before sending.")
    else:
        with st.spinner("Reading your feedback"):
            _, a = feedback.save(user, comment, rating=(stars + 1) if stars is not None else None, order_id=order_choice)
        st.success("Thanks. Your feedback is in.")
        with st.container(border=True):
            st.markdown(f"**From the café:** {a['reply']}")

st.caption("Problem with an order right now? Email fairlanecoffeehouse@gmail.com.")

mine = feedback.for_user(user["id"])
if mine:
    st.subheader("Your past feedback")
    for f in mine[:10]:
        with st.container(border=True):
            st.caption(f"{hours.fmt_dt(f['created_at'])}" + (f", {f['rating']} of 5 stars" if f["rating"] else ""))
            st.write(f["comment"])
            if f["reply"]:
                st.markdown(f"_Reply: {f['reply']}_")

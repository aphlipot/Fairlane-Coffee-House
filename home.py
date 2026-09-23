from collections import Counter

import streamlit as st

from core import auth, db, hours, menu, ui

user = auth.current_user()

st.markdown(
    """<div class="fch-hero">
    <h1>Fairlane Coffee House</h1>
    <p>Coffee at Fairlane Center in Dearborn. Order ahead, pull up curbside, or book a table and stay a while.</p>
    </div>""",
    unsafe_allow_html=True,
)
ui.status_pill()
st.write("")

c1, c2, c3 = st.columns(3)
c1.page_link("views/order.py", label="Order ahead", icon=":material/shopping_bag:")
c2.page_link("views/reservations.py", label="Reserve a table", icon=":material/table_restaurant:")
c3.page_link("views/assistant.py", label="Ask what to try", icon=":material/forum:")

# Personal shortcut: the item this customer orders most.
if user:
    rows = db.query(
        """SELECT i.product, i.size, i.flavor, i.quantity FROM order_items i JOIN orders o ON o.id = i.order_id
           WHERE o.user_id = ? AND o.status != 'cancelled'""",
        (user["id"],),
    )
    if rows:
        counts = Counter()
        for r in rows:
            counts[r["product"]] += r["quantity"]
        fav = counts.most_common(1)[0][0]
        with st.container(border=True):
            st.markdown(f"**Welcome back, {user['full_name'] or user['username']}.** Your usual is the {fav}.")
            if st.button(f"Order a {fav}", type="primary"):
                cat, _ = menu.find(fav)
                st.session_state["prefill"] = (cat, fav)
                st.switch_page("views/order.py")

st.divider()
about, hrs, contact = st.columns([1.3, 1, 1])

with about:
    st.subheader("About us")
    st.write(
        "Fairlane Coffee House serves espresso drinks, boba, smoothies, and fresh bakes to the people who study, "
        "work, and meet at Fairlane Center. Our app learns what you like, so your usual can be ready when you pull in. "
        "We track waste closely and brew to demand, which keeps drinks fresh and trims what we throw away."
    )

with hrs:
    st.subheader("Hours")
    today = hours.today().weekday()
    lines = []
    for i, name in enumerate(hours.DAY_NAMES):
        o, c = hours.HOURS[i]
        row = f"{name}: {hours.fmt_time(o)} to {hours.fmt_time(c)}"
        lines.append(f"**{row}**" if i == today else row)
    st.markdown("  \n".join(lines))
    st.caption(f"Today is {hours.now().strftime('%A, %B %d, %Y')}. Local time {hours.fmt_time(hours.now())}.")

with contact:
    st.subheader("Visit or contact us")
    st.write("19000 Hubbard Drive  \nFairlane Center South  \nDearborn, MI 48126")
    st.write("Questions or problems with an order? Email [fairlanecoffeehouse@gmail.com](mailto:fairlanecoffeehouse@gmail.com) "
             "or leave a note on the Feedback page.")

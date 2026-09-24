import streamlit as st

from core import ui

ui.header(
    "Our business model",
    "A café that knows your usual, preps it for when you arrive, and treats its tables as a bookable product.",
)

st.subheader("The idea: a predictive café")
st.write(
    "Most coffee chains, Starbucks included, are built for throughput. A line forms, the bar works through it, "
    "and a points program tries to bring you back. Fairlane starts from the other end: the customer's schedule. "
    "Our regulars are students, faculty, and office tenants at Fairlane Center whose days run on class and meeting "
    "times. If we know what they drink and when they show up, we can have it ready as they walk in, brew closer to "
    "real demand, and sell our space as well as our coffee."
)

st.subheader("How it works")
left, right = st.columns(2)
with left:
    st.markdown("**Fairlane Pass.** A monthly membership that covers one drink a day, priority curbside, and two "
                "table-hours of reserved seating a week. Members give us recurring revenue and a steady read on demand.")
    st.markdown("**Your usual, predicted.** The app learns each member's regular order and arrival window, then "
                "offers a one-tap confirmation before they arrive. The kitchen starts the drink as they pull in or "
                "check in curbside, so the wait is close to zero.")
    st.markdown("**Brew to forecast.** Order history, reservations, and the campus calendar feed a daily demand "
                "forecast. We bake and prep to it, which cuts waste and keeps drinks fresh.")
with right:
    st.markdown("**Tables as a service.** Seating is reservable for study sessions, interviews, and small meetings, "
                "with a food and drink minimum. Slow afternoon hours become booked hours.")
    st.markdown("**Off-peak rewards, not surge pricing.** In slow windows the app offers members a bonus item or "
                "extra table time. We never raise prices at the rush; we fill the gaps instead.")
    st.markdown("**Customers shape the menu.** Every review is scored for sentiment and topic. Complaints route to "
                "the manager the same day, and seasonal drinks are picked from what members ask for.")

st.subheader("Revenue streams")
st.write(
    "Walk-in and order-ahead sales, Fairlane Pass memberships, table reservations with minimums, and group orders "
    "and catering for events at Fairlane Center. Customer data stays with us: it runs the café and is never sold."
)

st.subheader("Try the numbers")
st.caption("A rough monthly view of the membership. Change the inputs to test the model.")
c1, c2, c3, c4 = st.columns(4)
members = c1.number_input("Members", 0, 5000, 300, step=25)
fee = c2.number_input("Monthly fee ($)", 0.0, 200.0, 39.0, step=1.0)
use = c3.slider("Share of days a member redeems", 0.0, 1.0, 0.55, step=0.05)
cost = c4.number_input("Cost per drink ($)", 0.0, 5.0, 1.10, step=0.05)
open_days = 30
drinks = members * open_days * use
revenue = members * fee
drink_cost = drinks * cost
m1, m2, m3 = st.columns(3)
m1.metric("Membership revenue", ui.money(revenue))
m2.metric("Drinks redeemed", f"{drinks:,.0f}")
m3.metric("Margin after drink cost", ui.money(revenue - drink_cost))
st.caption("Members also buy food and extra drinks. Those add-on sales aren't counted here.")

st.subheader("How we'll know it's working")
st.write(
    "Average wait from check-in to handoff, share of orders placed ahead, member retention month to month, "
    "table utilization between 1 and 5 PM, food waste per day, and average sentiment score from reviews."
)

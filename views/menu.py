import json

import streamlit as st

from core import menu, ui

ui.header("Menu", "Prices and calories by size. Tap Order this to start an order with the item selected.")

max_cal = st.slider("Show items up to this many calories", 0, 500, 500, step=25)

for tab, cat in zip(st.tabs(menu.categories()), menu.categories()):
    with tab:
        for p in menu.products(cat):
            cal = menu.calories_for(p, menu.sizes(p)[0] if menu.sizes(p) else None)
            if cal > max_cal:
                continue
            with st.container(border=True):
                left, right = st.columns([3, 2])
                with left:
                    st.markdown(f"**{p['Product Name']}**")
                    st.write(p["Description"])
                    fl = menu.flavors(p)
                    if fl:
                        st.caption("Flavors: " + ", ".join(fl))
                    elif p["Flavor"]:
                        st.caption(p["Flavor"])
                with right:
                    if menu.sizes(p):
                        rows = [{"Size": s, "Calories": c, "Price": ui.money(pr)}
                                for s, c, pr in zip(p["Size"], p["Calorie"], p["Price"])]
                        st.dataframe(rows, hide_index=True, width="stretch")
                    else:
                        size = f"{p['Size']}, " if p["Size"] else ""
                        st.markdown(f"{size}{p['Calorie']} cal, **{ui.money(p['Price'])}**")
                    if st.button("Order this", key=f"menu_{p['Product Name']}"):
                        st.session_state["prefill"] = (cat, p["Product Name"])
                        st.switch_page("views/order.py")

with st.expander("Menu data (JSON)"):
    st.caption("The app reads the menu from data/menu.json. Edit that file to change items, sizes, or prices.")
    st.code(json.dumps(menu.load_menu(), indent=2), language="json")

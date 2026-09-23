import streamlit as st

from core import ai, auth, db, hours, menu, ui

ui.header("Ask Fairlane", "Ask about the menu, get a suggestion, or find out how pickup and reservations work.")
ui.ai_mode_note()
user = auth.current_user()
history = st.session_state.setdefault("chat_history", [])
MAX_TURNS = 40


def order_history_text():
    if not user:
        return ""
    rows = db.query(
        """SELECT i.product, i.size, i.flavor, o.created_at FROM order_items i JOIN orders o ON o.id = i.order_id
           WHERE o.user_id = ? AND o.status != 'cancelled' ORDER BY o.created_at DESC LIMIT 12""",
        (user["id"],),
    )
    return "; ".join(f"{r['product']} {r['size'] or ''} {r['flavor'] or ''}".strip() for r in rows)


def hours_text():
    return "\n".join(f"{n}: {hours.fmt_time(o)} to {hours.fmt_time(c)}" for n, (o, c) in zip(hours.DAY_NAMES, hours.HOURS.values()))


def order_buttons(text, key):
    names = menu.names_in_text(text)[:4]
    if not names:
        return
    cols = st.columns(len(names))
    for col, name in zip(cols, names):
        if col.button(f"Order {name}", key=f"{key}_{name}"):
            st.session_state["prefill"] = (menu.find(name)[0], name)
            st.switch_page("views/order.py")


if not history:
    st.write("Try one of these:")
    starters = ["I like sweet drinks. What should I get?", "Are you open right now?",
                "How does curbside pickup work?", "What's under 200 calories?"]
    cols = st.columns(len(starters))
    for col, s in zip(cols, starters):
        if col.button(s, key=f"start_{s}"):
            st.session_state["pending_prompt"] = s
            st.rerun()

for i, msg in enumerate(history):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and i == len(history) - 1:
            order_buttons(msg["content"], f"hist{i}")

prompt = st.chat_input("Ask about drinks, hours, pickup, or reservations") or st.session_state.pop("pending_prompt", None)
if prompt:
    if len(history) >= MAX_TURNS * 2:
        st.warning("This chat is getting long. Clear it to start a new one.")
        st.stop()
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    status_text = hours.status_line()[1]
    with st.chat_message("assistant"):
        if ai.enabled():
            system = ai.assistant_system_prompt(user and (user["full_name"] or user["username"]), status_text,
                                                hours_text(), order_history_text())
            reply = st.write_stream(ai.stream([{"role": "system", "content": system}] + history[-20:]))
        else:
            reply = ai.basic_reply(prompt, status_text)
            st.markdown(reply)
    history.append({"role": "assistant", "content": reply})
    st.rerun()

if history and st.button("Clear chat", type="tertiary"):
    history.clear()
    st.rerun()

import json

import streamlit as st

from core import ai, auth, db, hours, ui

POSITIONS = {
    "Barista": "Make drinks, run the register, and keep the bar moving during rushes.",
    "Shift Lead": "Run a shift, coach the team, handle customer issues, and close out the day.",
    "Kitchen Prep": "Prep bakes and smoothie fruit, manage inventory, and keep the kitchen clean.",
}
TOTAL_QUESTIONS = 5

ui.header("Careers", "Join the Fairlane team. Apply below and complete a short online interview, about 10 minutes.")
ui.ai_mode_note()
user = auth.current_user()
iv = st.session_state.get("interview")

if not iv:
    for title, desc in POSITIONS.items():
        st.markdown(f"**{title}.** {desc}")
    with st.form("apply"):
        position = st.selectbox("Position", list(POSITIONS))
        name = st.text_input("Full name", value=(user and user["full_name"]) or "")
        email = st.text_input("Email", value=(user and user["email"]) or "")
        agree = st.checkbox("I understand my answers are reviewed by AI and a hiring manager.")
        start = st.form_submit_button("Start interview", type="primary")
    if start:
        if not name.strip() or "@" not in email or not agree:
            st.error("Add your name and email, and check the box to continue.")
        else:
            with st.spinner("Preparing your first question"):
                q = ai.interview_question(position, [], TOTAL_QUESTIONS)
            st.session_state["interview"] = {"position": position, "name": name.strip(), "email": email.strip(),
                                             "transcript": [], "question": q, "done": False}
            st.rerun()
    st.stop()

if iv["done"]:
    st.success(f"Thanks, {iv['name']}. Your interview for {iv['position']} is submitted. We'll email you about next steps.")
    if st.button("Start a new application"):
        st.session_state.pop("interview")
        st.rerun()
    st.stop()

st.subheader(f"{iv['position']} interview")
st.progress(len(iv["transcript"]) / TOTAL_QUESTIONS, text=f"Question {len(iv['transcript']) + 1} of {TOTAL_QUESTIONS}")
for t in iv["transcript"]:
    with st.chat_message("assistant", avatar=":material/badge:"):
        st.write(t["q"])
    with st.chat_message("user"):
        st.write(t["a"])
with st.chat_message("assistant", avatar=":material/badge:"):
    st.write(iv["question"])

answer = st.chat_input("Type your answer")
if answer:
    iv["transcript"].append({"q": iv["question"], "a": answer.strip()})
    if len(iv["transcript"]) >= TOTAL_QUESTIONS:
        with st.spinner("Submitting your interview"):
            ev = ai.evaluate_interview(iv["position"], iv["transcript"])
            summary = ev.get("summary", "")
            extra = []
            if ev.get("strengths"):
                extra.append("Strengths: " + "; ".join(ev["strengths"]))
            if ev.get("concerns"):
                extra.append("Concerns: " + "; ".join(ev["concerns"]))
            db.execute(
                """INSERT INTO interviews (user_id, name, email, position, transcript, score, recommendation, summary, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (user and user["id"], iv["name"], iv["email"], iv["position"], json.dumps(iv["transcript"]),
                 ev.get("score"), ev.get("recommendation"), "\n".join([summary] + extra), hours.iso(hours.now())),
            )
        iv["done"] = True
    else:
        with st.spinner("Next question"):
            iv["question"] = ai.interview_question(iv["position"], iv["transcript"], TOTAL_QUESTIONS)
    st.rerun()

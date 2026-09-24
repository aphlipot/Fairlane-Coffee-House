import json

import streamlit as st

from core import db, hours, ui

ui.header("Hiring", "Online interviews from the Careers page, with AI scores for a first pass. You make the call.")
ui.require_role("manager")

STATUSES = ["new", "contacted", "hired", "declined"]
rows = db.query("SELECT * FROM interviews ORDER BY created_at DESC")
if not rows:
    st.write("No interviews yet. Candidates apply on the Careers page.")
    st.stop()

pos_filter = st.multiselect("Position", sorted({r["position"] for r in rows}))
status_filter = st.multiselect("Status", STATUSES, default=["new", "contacted"])
shown = [r for r in rows if (not pos_filter or r["position"] in pos_filter) and (not status_filter or r["status"] in status_filter)]

st.dataframe(
    [{"ID": r["id"], "Name": r["name"], "Position": r["position"], "AI score": r["score"],
      "Recommendation": r["recommendation"], "Status": r["status"], "Submitted": hours.fmt_dt(r["created_at"])} for r in shown],
    hide_index=True, width="stretch",
)

for r in shown:
    with st.expander(f"{r['name']}, {r['position']}, score {r['score'] if r['score'] is not None else 'n/a'}"):
        st.caption(r["email"])
        st.markdown(r["summary"] or "")
        for t in json.loads(r["transcript"] or "[]"):
            st.markdown(f"**Q.** {t['q']}")
            st.write(t["a"])
        new = st.selectbox("Status", STATUSES, index=STATUSES.index(r["status"]), key=f"st_{r['id']}")
        if new != r["status"]:
            db.execute("UPDATE interviews SET status = ? WHERE id = ?", (new, r["id"]))
            st.rerun()

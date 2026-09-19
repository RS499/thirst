"""thirst -- water-aware scheduling of deferrable compute on the PJM grid.

Pipeline for one request:

    plain-English job  --classify (Nemotron)-->  Classification
                       --place (Python)-------->  PlacementRecord
                       --explain (Nemotron)---->  Explanation      (not wired yet)
                       --verify (Python)------->  shown to user, or fallback

Python owns every number. Nemotron only labels (classify) and narrates
(explain). Every figure on this page is a ``PlacementRecord.display`` string.

    streamlit run app.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from thirst.classify import classify
from thirst.place import place
from thirst.signals import season_of

DIVERGENCE_PNG = Path(__file__).parent / "results" / "divergence.png"
PLACEHOLDER = ("Nightly fine-tuning run. It can pause and resume, "
               "and it needs to be done before the 9am standup.")
OBJECTIVES = {"carbon": "Carbon", "water_withdrawal": "Water withdrawal",
              "water_consumption": "Water consumption"}
BASES = {"average": "average", "marginal_empirical": "marginal-empirical"}
METRICS = {"carbon": "Carbon", "withdrawal": "Water withdrawal",
           "consumption": "Water consumption"}

st.set_page_config(page_title="thirst", page_icon="💧")
st.markdown("<style>#MainMenu, footer, [data-testid='stMainMenu'] {visibility: hidden;}</style>",
            unsafe_allow_html=True)
st.title("thirst")
st.caption("Place a deferrable compute job in the PJM hour that costs less carbon and water, "
           "and see what the choice trades away.")

with st.form("job"):
    description = st.text_area("Describe the job", placeholder=PLACEHOLDER, height=110)
    submitted = st.form_submit_button("Place it", type="primary")

if submitted and description.strip():
    now = datetime.now()
    with st.spinner("Classifying..."):
        # Classify once per submit; the radios below re-run place() only.
        st.session_state["job"] = {
            "c": classify(description, now_hour=now.hour),
            "arrival": now.hour + 1,             # hour-ending of the current hour
            "season": season_of(now.month),
        }

job = st.session_state.get("job")
if job:
    c = job["c"]
    st.markdown(f"**Classification:** `{c.label}`"
                + (f" · window from *“{c.window_phrase}”*" if c.window_phrase else "")
                + (f" · {c.rationale}" if c.rationale else ""))
    if c.error:
        st.warning(f"Classifier fell back to `unclear`: {c.error}")

    if c.label != "deferable" or not c.window_h:
        st.info("Not deferable, so it runs on arrival and there is nothing to place.")
    else:
        # Two separate questions, kept visually apart.
        left, right = st.columns(2)
        with left.container(border=True):
            st.markdown("**What do you want to minimize?**")
            objective = st.radio("Objective", list(OBJECTIVES), format_func=OBJECTIVES.get,
                                 key="objective", label_visibility="collapsed")
        with right.container(border=True):
            st.markdown("**How is it accounted for?**")
            basis = st.radio("Accounting basis", list(BASES), format_func=BASES.get,
                             key="basis", label_visibility="collapsed",
                             help="average: the whole grid mix in that hour (attribution). "
                                  "marginal-empirical: the fuels that respond to an added "
                                  "load (causation).")

        rec = place(job["arrival"], c.window_h, job["season"], basis=basis)[objective]
        d = rec.display
        b = BASES[basis]

        # Same one-decimal test as place._tradeoff, so the banner matches the flag.
        worse = [name for m, name in METRICS.items() if round(getattr(rec, m).delta_pct, 1) < 0]
        if rec.tradeoff == "conflict":
            st.error(f"### ⚠️ Conflict ({b} basis)\nMinimizing {OBJECTIVES[objective].lower()} "
                     f"makes {' and '.join(w.lower() for w in worse)} worse.")
        elif rec.tradeoff == "aligned":
            st.success(f"### ✅ Aligned ({b} basis)\nMinimizing "
                       f"{OBJECTIVES[objective].lower()} improves every metric.")
        else:
            st.warning(f"### ➖ Neutral ({b} basis)\nMoving this job changes little, "
                    "or nothing gets worse.")

        cols = st.columns(4)
        cols[0].metric("Best start", d["placed.hour"],
                       help=f"Arrival {d['arrival.hour']}, shift {d['shift_h']}, "
                            f"window {d['window_h']}.")
        for col, (m, name) in zip(cols[1:], METRICS.items()):
            col.metric(f"{name} ({b} basis)", d[f"{m}.delta_pct"],
                       help=f"{b} basis, per MWh: run on arrival {d[f'{m}.baseline']}, "
                            f"placed {d[f'{m}.placed']}.")
        st.caption(f"% less than running on arrival at {d['arrival.hour']}; negative = worse. "
                   f"{b} basis · season {d['season']} · per {d['energy_mwh']} · "
                   f"source {d['source']}.")

        # Placeholder: the explain -> verify step (Nemotron job #2) goes here.
        with st.container(border=True):
            st.markdown("**Explanation**")
            st.caption("Plain-English explanation coming soon.")

st.divider()
st.image(str(DIVERGENCE_PNG),
         caption="Average basis: the lowest-carbon hour and the lowest-withdrawal hour "
                 "are different hours.")
st.caption("Water withdrawal (water taken in) and water consumption (water not returned) "
           "are separate metrics. They are never added into one water number.")

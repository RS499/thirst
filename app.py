"""thirst -- water-aware scheduling of deferrable compute on the PJM grid.

Pipeline for one request:

    plain-English job  --classify (Nemotron)-->  Classification
                       --place (Python)-------->  PlacementRecord
                       --explain (Nemotron)---->  Explanation
                       --verify (Python)------->  shown to user, or fallback

Python owns every number. Nemotron only labels (classify) and narrates
(explain). Every figure on this page is a ``PlacementRecord.display`` string.

    python3 -m streamlit run app.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from thirst.classify import classify
from thirst.explain import explain
from thirst.place import place
from thirst.signals import season_of

RESULTS = Path(__file__).parent / "results"
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
        c = classify(description, now_hour=now.hour)
        st.session_state["classification"] = {
            "c": c,
            "arrival": c.now_hour + 1,           # hour-ending of the hour the window counts from
            "season": season_of(now.month),
        }

job = st.session_state.get("classification")
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
        better = [name for m, name in METRICS.items() if round(getattr(rec, m).delta_pct, 1) > 0]
        if rec.tradeoff == "conflict":
            st.error(f"### ⚠️ Conflict ({b} basis)\nMinimizing {OBJECTIVES[objective].lower()} "
                     f"makes {' and '.join(w.lower() for w in worse)} worse.")
        elif rec.tradeoff == "aligned":
            st.success(f"### ✅ Aligned ({b} basis)\nMinimizing "
                       f"{OBJECTIVES[objective].lower()} improves "
                       f"{' and '.join(w.lower() for w in better)}, and nothing gets worse.")
        else:
            st.warning(f"### ➖ Neutral ({b} basis)\nMoving this job changes no metric.")

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

        # Explain once per record and basis; flipping the radios back reuses it.
        cache = st.session_state.setdefault("explanations", {})
        key = (rec.job_id, rec.basis, c.window_phrase)
        if key not in cache:
            with st.spinner("Explaining..."):
                cache[key] = explain(rec)
        e = cache[key]
        with st.container(border=True):
            st.markdown(f"**{e.headline}**")
            st.write(e.explanation)
            if e.fallback:
                st.caption("Template fallback: verify() rejected the model's text"
                           + (f" ({e.error})" if e.error else "") + ".")
            else:
                st.caption("Written by Nemotron. verify() checked every number against the "
                           "placement record, sign included.")

st.divider()
st.image(str(RESULTS / "divergence.png"),
         caption="Average basis: the lowest-carbon hour and the lowest-withdrawal hour "
                 "are different hours.")
st.image(str(RESULTS / "basis_flip.png"),
         caption="Average vs marginal-empirical basis: carbon-optimized scheduling costs "
                 "water withdrawal on one basis and saves it on the other.")
st.image(str(RESULTS / "region_reorder.png"),
         caption="Average-basis consumption, weighted by AWARE-US county water stress: "
                 "the ranking of regions changes.")
st.caption("Water withdrawal (water taken in) and water consumption (water not returned) "
           "are separate metrics. They are never added into one water number.")

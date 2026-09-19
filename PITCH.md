# PITCH: 3-minute live judging script

Pace: about 150 spoken words per minute. Each section gives its target clock
time and a word budget. **Bold** is emphasis. `[BRACKETS]` are actions or cues,
not spoken.

## Pre-flight (before the judges arrive)

- [ ] `python3 -m uvicorn api:app --port 8600`, then open `localhost:8600`.
  Fallback: `python3 -m streamlit run app.py` (NOT `streamlit run app.py`).
- [ ] Run the demo job once, so the model endpoint is warm and you've seen the
  verdict yourself.
- [ ] Leave the run-time / power fields **blank**. A stated duration shrinks the
  start window and the numbers below will change.
- [ ] Basis set to **average**, objective set to **carbon** (the defaults).
- [ ] Screenshot of the verdict in both bases, in case the Wi-Fi or the free
  tier dies mid-demo.

The demo numbers are deterministic for the autumn (SON) profile. The text
anchors the time ("It's 10pm now"), so the demo gives the same answer at any
time of day. Verified: 22:00 arrival, 11 h window.

| basis | best start | tradeoff | carbon | withdrawal | consumption |
|---|---|---|---:|---:|---:|
| average | 03:00 | conflict | +6.6 % | −9.1 % | −3.4 % |
| marginal-empirical | 22:00 (now) | neutral | +0.0 % | +0.0 % | +0.0 % |

---

## 0:00–0:30 · The finding (30 s, ~75 words)

> Everyone says: run your compute when the grid is clean.
>
> I measured what that does to water on PJM, the grid under thirteen eastern
> states. Counted the standard way, the average basis, the cleanest hour of the
> day is not the lowest-water hour on **360 of 365 days**. Across the year,
> cleaner hours tend to be *thirstier* hours.
>
> Nobody noticed, because nobody measures both.

## 0:30–1:35 · Live demo (65 s, ~160 words)

`[Page is open. Click into the text box.]`

> So I built **thirst**. I describe a job the way I'd say it in Slack.

`[Paste:]` *It's 10pm now. Nightly fine-tuning run, it can pause and resume, and it needs to be done before the 9am standup.*

`[Click "Place it". About 3 seconds.]`

> Nemotron reads that and gives back one thing: the exact words that set the
> deadline, "before the 9am standup." It never gives me a number. Python turns
> those words into an eleven-hour window.

`[Verdict appears: Conflict. Point at it.]`

> Verdict: **conflict**. Best start, three a.m. On the average basis, carbon
> drops **6.6 percent**, and water withdrawal gets **9.1 percent worse**. The
> cleanest hour is the thirsty hour.

`[Click the basis switch: marginal-empirical. Bars swing through zero.]`

> Now I change one thing: how the electricity is *counted*. On the
> marginal-empirical basis the advice flips to **run it now**. Moving it buys
> nothing, zero on every metric.

> Why? The average basis asks what was in the grid when you ran. That's
> attribution. Marginal asks which plants actually turned up *because* you
> added load. That's causation. Nuclear never turns up for your job, so the
> conflict disappears. Same job, opposite advice. That's why every number on
> this screen names its basis.

## 1:35–2:20 · The evidence (45 s, ~115 words)

> **The classifier:** 0.983 on sixty hand-labeled jobs, against **0.550** for
> always guessing the most common answer. The last jump was me fixing my own
> label definitions, not the model improving. That's in the log.
>
> **The explainer:** 18 of 20 explanations kept every number exact, **0.90**. The
> other two flipped a sign, and both were caught. A verifier checks every number
> the model writes against what Python computed. Anything that doesn't match is
> thrown out for a plain template. A number Python didn't compute *cannot* reach
> the screen.
>
> **A holdout:** thirty jobs, sealed and hashed before my first eval run,
> `[IF OPENED:]` opened exactly once, scoring ___.
> `[IF NOT YET:]` opened exactly once, at the end.
>
> And **seven failures, written down**, including a 40-percent savings result I
> threw out as an artifact.

## 2:20–2:40 · Where it breaks (20 s, ~50 words)

> Where it breaks. My deadline parser scores perfectly, but I built it on those
> same sixty jobs, so that's optimistic. The cross-region pattern rests on five
> grids. And timing is a single-digit lever: a few percent, not a fix.

## 2:40–3:00 · The second finding (20 s, ~50 words)

> One thing I didn't expect. Rank regions by the water they use, and Texas looks
> like the second-best place to run. Weight that water by how scarce it is where
> it's drawn, and Texas is the **worst** of five. Counting gallons sends you to
> the driest places.

`[Stop. Take questions.]`

---

## 60-second cut (short slot, ~150 words)

> Everyone says: run your compute when the grid is clean. On PJM, counted the
> standard way, the cleanest hour isn't the lowest-water hour on **360 of 365
> days**. Nobody noticed, because nobody measures both.

`[Paste the job, click Place it.]`

> I describe a job in plain English. Nemotron quotes the deadline; Python does
> the maths. Verdict: **conflict**. Start at three a.m. and, on the average basis,
> carbon drops 6.6 percent but water withdrawal gets 9.1 percent worse.

`[Flip to marginal-empirical.]`

> Count it by which plants actually respond to my load, the marginal-empirical
> basis, and the advice flips to run it now. Same job, opposite answer. So
> every number here names its basis.
>
> The classifier scores 0.983 against a 0.550 baseline, and a verifier
> guarantees the model can't put a number on screen that Python didn't compute.

## 20-second version (judge already walking away, ~50 words)

> On the PJM grid, the cleanest hour to run your compute isn't the lowest-water
> hour on 360 of 365 days. Nobody noticed, because nobody measures both. I built
> a scheduler that shows the tradeoff, names how it's counted, and can't show a
> number it didn't compute.

---

## If asked

- **"Isn't 98.6 % just chance?"** On its own, nearly: independence would give
  97.1 %. The stronger evidence is that the two are *opposed*. Across the
  year's hours the correlation is −0.465 (average basis), and carbon-optimized
  scheduling raised withdrawal by 0.29 % to 1.87 % in simulation (average
  basis).
- **"Which basis is right?"** Both are right, but they answer different
  questions. Average is attribution (what your kWh contained). Marginal is
  causation (what your load changed). thirst shows both and picks neither
  silently.
- **"How big is the Texas effect?"** Quote the ranking, not the multiple. The
  order holds under both mean and median stress weighting. The size of the gap
  doesn't: a few water-capped counties drive it.
- **"What about withdrawal vs consumption?"** Withdrawal is water taken from a
  river and mostly returned. Consumption is water evaporated and gone. They are
  never added together.

# PITCH: 1:45 live, with slides and `/?demo=1`

Target **1:45**; the hard ceiling is 2:00. The `[CUT]` lines take it to about 1:30.
Pace: about 150 spoken words per minute. `[BRACKETS]` are actions, not spoken.

Tracks: **Beyond the Chatbot** (Nemotron) · **Seed Round** · **Xtract** · **Cold Start**.
The story is one idea: *the advice everyone follows to make computing greener
quietly makes it thirstier, and nobody can see it.*

---

## Pre-flight

- [ ] `python3 -m uvicorn api:app --port 8600`, with `NVIDIA_API_KEY` in `.env`.
- [ ] Open `localhost:8600/?demo=1` in a second window. It auto-plays. **Do not
  let it run through: the full tour is about 2.5 minutes.** Your only job is to
  press a key once results appear (see the demo section).
- [ ] Rehearse the handover once: the tour clicks "Place it" about 20 s in. Press
  any key after the results render. The page stays, and switching the basis
  re-renders locally from cache with no model call.
- [ ] Backup: screenshots of the verdict on both bases, in case anything stalls.

Verified numbers for the demo preset (*"It's 7pm now … done by 7am tomorrow"*,
autumn profile, cached in `static/demo_cache.json` and recomputed from
`place()`, which matches). The row is minimising carbon:

| basis | best start | verdict | carbon | withdrawal | consumption |
|---|---|---|---:|---:|---:|
| average | 03:00 | conflict | +7.3 % | −16.5 % | −8.3 % |
| marginal-empirical | 20:00 | aligned | +9.9 % | +24.7 % | +25.0 % |

(+ = less than running at 7pm; − = more.)

---

## SLIDE 1 · 0:00–0:20 · The hidden cost

> Every AI company is being told the same thing: run your compute when the
> grid is clean. Big clouds already do it.
>
> I measured what that does to **water**. On the PJM grid, which covers
> thirteen eastern states and Northern Virginia's data-centre alley, the
> cleanest hour of the day is not the lowest-water hour on **360 of 365 days**.
> Chase carbon, and you tend to pick a thirstier hour.
>
> Nobody noticed, because nobody measures both.

*Slide: one line, "Greener compute is quietly thirstier", plus the chart where
carbon bottoms out at 1pm and water at 7pm.*

## SLIDE 2 · 0:20–0:35 · Who has this problem (Seed Round)

> Who cares? Anyone running flexible compute: AI labs, cloud providers, and
> data-centre operators facing growing local scrutiny over water.
> Carbon-aware scheduling is already a product category. **Nobody puts water on
> the same screen.** That's the gap.

*Slide: three boxes, no logos: AI teams · data-centre operators · sustainability
reporting. Headline: "Carbon-aware exists. Water-aware doesn't."*
`[CUT → 1:30: drop the first sentence after "Who cares?"]`

## DEMO · 0:35–1:15 · Watch it decide

`[Switch to the /?demo=1 window. It is already running.]`

> Here's thirst. You describe a job the way you'd say it in Slack. *"It's 7pm.
> Overnight fine-tune, can pause and resume, done by 7am."*

`[The tour presses "Place it". Results appear. PRESS ANY KEY: you now drive.]`

> **Nemotron** reads that and pulls out one thing: the exact words that set the
> deadline. Plain code turns those words into a twelve-hour window. No guessing.

`[Point at the verdict.]`

> The verdict: **conflict**. Start at 3am, and on the average basis carbon drops
> 7 percent, but water withdrawal gets **16 percent worse**.

`[Click "marginal-empirical". The bars swing.]`

> Now count the electricity a different way: which power plants actually
> respond to *your* job. On that basis the goals line up. Start at 8pm, and
> carbon and water both improve. Same job, opposite advice. So thirst never shows
> a number without saying how it was counted.

## SLIDE 3 · 1:15–1:35 · Nemotron in the pipeline (Beyond the Chatbot · Xtract)

> Nemotron isn't a chatbot here. It's two parts of the machine. It **classifies**
> messy requests into a structured deadline: **0.952** accuracy on 63 labeled
> jobs, against 0.571 for guessing. And it **explains** the tradeoff, but a
> verifier checks every number it writes against the math. Anything untraceable
> is thrown out, so a number the code didn't compute can never reach the screen.
> Every figure traces back to its source: the exact words quoted, the public
> grid data, the commit.

*Slide: pipeline diagram "plain English → Nemotron: classify → Python: place →
Nemotron: explain → verify". Two numbers under it: 0.952 vs 0.571 · 18/20
explanations exact.*
`[CUT → 1:30: drop the last sentence]`

## SLIDE 4 · 1:35–1:50 · What I learned (Cold Start)

> What I learned this weekend: an AI eval can lie to you. My classifier jumped
> from 67 to 92 percent when I fixed *my own* question, not the model. And the
> same data can give opposite answers depending on how you count. So I wrote
> down every failure: there are seven, in the repo.
>
> Greener computing shouldn't cost the rivers. thirst makes the trade visible.

*Slide: "7 failures, documented" + the closing line.*

---

## Track cheat-sheet (for Q&A)

**Beyond the Chatbot (Nemotron).** Two non-chat jobs in a pipeline.
- **Classify:** plain English → `{label, interruptible, window_phrase}`, with the
  phrase quoted verbatim. Python does all the arithmetic.
- **Explain:** narrates a Python-built record, and `verify()` rejects any
  untraceable number.
- **Evidence:** 0.952 vs 0.571 baseline (63 rows); explainer 18/20 exact, and
  both misses were sign flips caught by the verifier; a sealed, hashed holdout.
- **Failures found:** `/no_think` is ignored by nemotron-3-super, so it needed
  `enable_thinking=False` plus a JSON schema. The specified model was retired
  (HTTP 410).

**Seed Round.** Who pays: AI and cloud teams with sustainability targets, and
data-centre operators under water scrutiny. Wedge: an add-on to the
carbon-aware scheduling people already run. It's a working product, not a deck.
*Don't quote market-size numbers you haven't sourced; say "I'd validate
willingness to pay next".*

**Xtract.** The honest fit is **traceability**: unstructured requests become a
structured signal, each insight links to its source (the verbatim quote, EIA
public data, the pinned commit), and it's shown in a clean UI. *Be candid if
asked: it ingests job requests and grid data, not news or reports.*

**Cold Start.** Things I didn't know on Friday:
- evals measure your labels as much as your model;
- a model being listed doesn't mean you can call it;
- offline tests passed while the live app crashed on every submit.

*Eligibility: at least 75 % of the team first-time hackers, and no
professional software-engineering experience.*

## If asked

- **"Isn't 360/365 just chance?"** The days-differ rate alone is close to chance
  (97.1 %). The stronger evidence is that the two are opposed: across the year,
  cleaner hours tend to be thirstier (r = −0.465, average basis).
- **"Which way of counting is right?"** Both, but they answer different questions.
  Average is what your electricity contained; marginal is what your job changed.
  thirst shows both and never picks one silently.
- **"How big is the win?"** For this one job, up to about 25 % on the
  marginal-empirical basis. Averaged over thousands of simulated jobs, it's
  single digits. Timing is a lever, not a fix.
- **"Does it generalize?"** No, and that's a finding. PJM is the only one of five
  checkable grids with this conflict. And ranking regions by gallons alone sends
  you to the driest places: Texas looks second-best by raw water, and worst once
  local scarcity is counted.

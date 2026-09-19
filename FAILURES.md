# FAILURES

Seven things that went wrong, what they would have cost, and how each was caught.
Logged here rather than silently fixed.

## 1. Solar PV water factor was 26× too high, in the flattering direction

An early draft of the upstream water-factor table carried **26 gal/MWh** for
utility-scale PV consumption, written from memory. The published value is
**1 gal/MWh** (range 0–5; Macknick et al. 2012, ERL 7 045802, Table 2). Solar is
zero-carbon, so an inflated solar water factor makes the cleanest hours look
thirstier. That manufactures exactly the carbon/water divergence the study was
testing for. The value was corrected against the published table before any
result was computed.
Evidence: `pjm-water-carbon/pjmwater/water_factors.py` (verification note),
`results/SUMMARY.md` "Verification findings" #1.

## 2. A 40 % savings result was rejected as a solar-ramp artifact

The first marginal-emissions estimate let all eight fuel types set the margin.
In morning and evening solar-ramp hours, the change in total generation is
dominated by solar while fossil output moves the other way. The regression
therefore gave fossil fuels negative marginal shares, and marginal intensity
went **negative**: −129 gCO₂/kWh and −1,116 gal/MWh. A scheduler then "earned"
negative carbon by parking jobs in those hours, reporting **33–40 % savings**.
That was arbitrage of an estimation artifact, not a real saving. The response
set was restricted to dispatchable fuels (coal, gas, oil, other), which keeps
marginal intensity between the cleanest and dirtiest dispatchable factor.
Evidence: `pjm-water-carbon/pjmwater/marginal.py` docstring ("WHY NOT ALL
FUELS"), `results/SUMMARY.md` "Rejected variant".

## 3. nemotron-3-super ignores `/no_think`

The documented way to turn off reasoning (`/no_think` in the system prompt) did
nothing. The model reasoned in plain text inside `content`, used all 400
`max_tokens` (`finish_reason: "length"`), and emitted no JSON. Every row became
"unclear" with `ValueError: no JSON object in model output`. With reasoning off
via `chat_template_kwargs: {"enable_thinking": false}`, it answered in about 60
tokens, but it emitted invalid JSON: the `rationale` value was unquoted. The fix
needed both: `enable_thinking=False` **plus** a server-side `json_schema`
`response_format`.
Evidence: `thirst/classify.py` `nemotron()`, commit "classify: disable Nemotron
reasoning and constrain output to the schema".

## 4. The specified model had been retired

`nvidia/nvidia-nemotron-nano-9b-v2`, the model named in the build plan, returns
**HTTP 410 Gone**: *"reached its end of life on 2026-08-26T09:00:00Z and is no
longer available."* Of the Nemotron models still listed:
- `nemotron-nano-3-30b-a3b` returned 404 for this account.
- `nemotron-3.5-lightning-30b-a3b` answered, but took 83 s and 150 s per call.
- `nemotron-3-super-120b-a12b` answered in 2.2 s and was adopted.

A listing that includes a model is not evidence the model can be called.
Evidence: `MODEL` comment in `thirst/classify.py`.

## 5. The label definitions asked the wrong question: 0.633 → 0.917

The first classify run scored **0.633**. Four of its 22 misses were transient
HTTP 503s ("Service temporarily overloaded") scored as "unclear". Adding SDK
retries, and correcting two gold labels (L22, L23), gave **0.667**. But the
dominant failure was elsewhere: the model predicted **"unclear" 0 times out of
18**. Its rationales showed why. For "retrain the ranking model sometime soon"
it reasoned "can be started later → deferable". It was answering *could this
job wait?*, while the labels meant *does the text state enough to compute a
window?* Redefining the three labels by what the text contains, plus three
boundary few-shot examples (not drawn from the eval set), took accuracy to
**0.917**. Ambiguous rows went from 0.000 to 0.933, no-deadline rows from 0.400
to 1.000. The retries and relabels moved the number by 0.033; the definition
moved it by 0.250.
Evidence: `results/progress.csv` (three rows), `results/classify_eval.json`.

## 6. Offline tests passed twice while the live app was broken

Offline checks passed twice: imports, `place()`, `verify()` over every record,
and the eval scripts. Meanwhile, every real submit in the Streamlit app crashed.
`st.form("job")` registers the widget key `"job"`, and the app then wrote the
classification to `st.session_state["job"]`. That raised
`StreamlitAPIException` on every submit, a path no offline test exercised. It
was found only by a real Chrome submit against the live Nemotron endpoint, and
fixed by storing the result under its own key.
Evidence: commit `071295c` "app: store classification under its own
session_state key".

## 7. Gold labels did placement arithmetic: 0.917 → 0.983 is a definition change

Three gold rows, L21 ("in 20 minutes"), L26 ("within the hour") and L30 ("in
45 minutes"), were labeled `not_deferable` because their windows (0, 1 and 0
hours) are too short to shift a job. That judgment is arithmetic: whether a
window leaves room to move is `place()`'s job. The classifier's job is only
whether the text states a deadline that resolves to hours. L22 and L23 had
already been relabeled on the same principle. L21, L26 and L30 were relabeled
`deferable`, keeping `window_h` 0, 1 and 0, with the prompt and code unchanged.

**This is a definition change, not a model improvement.** Rescoring the
*before* run's own predictions (commit `f87d959`) against the new labels moves
0.917 → 0.967. The only rows that change are the three relabeled ones, and the
model predicted `deferable` for all three both times. The single live re-run
scored **0.983** (59/60). The extra 0.017 over the rescore is one row: L09,
missed in the before run and correct in this one. That is run-to-run noise, not
the relabel. The majority baseline rises with the relabel too, from 0.500 to
**0.550** (33/60 `deferable`). The one remaining miss is L54 ("Retrain the
model in 2 hours"), which the model calls `deferable`. The gold label is
`unclear` because the run time is unknown.
Evidence: `results/progress.csv` rows `f87d959` (0.9167) and `65b2aa2`
(0.9833); `eval/README.md` labeling conventions.

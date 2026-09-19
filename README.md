# thirst

**Schedule your compute when the grid is less thirsty, and see what that costs
in carbon.**

## The problem

Carbon-aware schedulers move flexible jobs into low-carbon hours. They assume
that a cleaner hour is better on every axis. But power plants also withdraw and
consume water for cooling, and the cleanest hour for carbon is not necessarily
the cleanest hour for water. A scheduler that optimises carbon alone can quietly
raise the water bill. Users usually can't tell, because the answer depends on
an accounting choice they never see.

## The finding

From [`pjm-water-carbon`](../pjm-water-carbon) (PJM balancing authority,
2025-09-17 → 2026-09-16, 8,760 hours):

- **Carbon and water don't bottom out in the same hour.** The min-carbon hour
  differs from the min-consumption hour on 86.0 % of days and from the
  min-withdrawal hour on 98.6 % of days (average-intensity signals).
- **On the average basis, carbon-optimised scheduling increases water
  withdrawal** at every deadline slack tested, by 0.29 % to 1.87 %. The reason:
  PJM's lowest-carbon dispatchable fuel, nuclear, is also its highest-withdrawal
  fuel.
- **On the marginal-empirical basis the conflict disappears.** Once nuclear is
  off the margin, carbon-optimised scheduling at 24 h slack saves 3.05 % carbon
  and 6.37 % withdrawal (marginal-empirical basis).

So whether green scheduling is also water-friendly depends on which accounting
basis you use. thirst names the basis next to every figure and shows both.

## How it works

1. **Classify.** Nemotron reads a plain-English job description and decides
   whether it's deferable, quoting the words that set its deadline.
2. **Place.** Python picks the best feasible start hour from vendored PJM
   carbon, water-withdrawal and water-consumption profiles.
3. **Explain.** Nemotron narrates the tradeoff using only fields Python
   computed. A deterministic verifier rejects any output with a number Python
   didn't produce, or a savings figure without its basis.

## Results

> TODO: fill from `eval/` runs. Every savings cell must name its basis.

| eval | basis | metric | value |
|---|---|---|---:|
| Deferability classification accuracy | n/a | accuracy | TODO |
| Deferability classification | n/a | macro-F1 | TODO |
| Explanation verifier pass rate | n/a | % passing first try | TODO |
| Explanation grounding (numbers traced to record) | n/a | % | TODO |
| Placement savings, carbon | average | % vs. run-on-arrival | TODO |
| Placement savings, withdrawal | average | % vs. run-on-arrival | TODO |
| Placement savings, consumption | average | % vs. run-on-arrival | TODO |
| Placement savings, carbon | marginal-empirical | % vs. run-on-arrival | TODO |
| Placement savings, withdrawal | marginal-empirical | % vs. run-on-arrival | TODO |
| Placement savings, consumption | marginal-empirical | % vs. run-on-arrival | TODO |

## Data

`data/` holds season × hour-of-day and season × hour-of-week profiles vendored
from `pjm-water-carbon` @ `28aecf4`. See [`data/README.md`](data/README.md).
There is no fetching or recomputation at runtime.

## Team

| name | email |
|---|---|
| TODO | TODO |
| TODO | TODO |
| TODO | TODO |

## License

MIT. See [LICENSE](LICENSE).

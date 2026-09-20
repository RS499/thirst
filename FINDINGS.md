# FINDINGS

## Water stress reorders the regions; it does not just rescale them

**Question.** Across the five balancing authorities that passed upstream's
cooling-data coverage gate (PJM, MISO, ERCO, SOCO, BPAT), does weighting water
use by local water stress change the *ranking*, or only the size of the numbers?

**Answer: it reorders them.** On raw consumption, PJM ranks 2nd and ERCO 4th.
After stress weighting, ERCO is 1st and PJM 4th. The new order is identical
whether the regional stress factor is a capacity-weighted mean or a
capacity-weighted median. The *size* of ERCO's lead is not robust; see below.

| region | withdrawal L/MWh | rank | consumption L/MWh | rank | stress factor (mean) | stress-adj. consumption L-eq/MWh | rank | rank with median factor |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PJM  | 30,921 | 1 | 1,094 | 2 | 0.378 |   413 | 4 | 4 |
| MISO | 29,687 | 2 |   842 | 3 | 1.084 |   913 | 2 | 2 |
| ERCO | 10,193 | 3 |   763 | 4 | 7.053 | 5,380 | 1 | 1 |
| SOCO |  8,742 | 4 | 1,291 | 1 | 0.364 |   470 | 3 | 3 |
| BPAT |    502 | 5 |   313 | 5 | 0.446 |   139 | 5 | 5 |

Withdrawal and consumption volumes are annual means on the **average basis**
(generation-weighted mix, EIA-860 fleet cooling, hydro evaporation excluded),
from upstream `results/regions.csv` @ `28aecf4`. Rank 1 = most water per MWh.
Full columns: `results/regional_water_stress.csv`.

**Method.**

- **Factors.** Argonne AWARE-US county characterisation factors (Lee et al.
  2019, *Sci. Total Environ.* 648:1313–1322). There are 3,077 counties in 49
  states. The **6** rows with the no-data sentinel `cf = -1.0` were dropped:
  NY Clinton; VT Chittenden, Franklin, Grand Isle, Lamoille; VA Northampton.
  None of them has capacity in these five regions. The normalized file is
  `data/raw/aware_us_county.csv` (state, county, fips, cf), with FIPS read as
  strings to keep leading zeros.
- **Join.** EIA-860 gives each generator a state and county name but **no
  county FIPS**, so a FIPS join was not possible. The join is on state plus a
  normalised county name, which strips suffixes like "County" and "Parish",
  maps "St." to "Saint", and drops punctuation. That normalisation was needed
  for 18 county names, all verified by eye, e.g. MD "Prince Georges" ↔
  "Prince George's", LA "St Charles" ↔ "St. Charles Parish".
- **Weighting.** Each region's factor is weighted by the nameplate capacity of
  water-consuming thermal units with a cooling loop. That means coal, gas,
  nuclear, oil and other; wind, solar and simple-cycle turbines are excluded.
  This is upstream's `water_stress.regional_stress_factor`, used unchanged.
- **Consumption only.** Stress weighting is applied to consumption, not
  withdrawal. AWARE characterises water *removed* from a basin, and withdrawn
  water that is returned to the same river is not the same impact. Weighting
  withdrawal by it would be a category error. This follows upstream's design,
  so withdrawal is ranked on raw volume only.

**County-match coverage.**

| region | water-consuming capacity | matched to an AWARE county |
|---|---:|---:|
| PJM  | 143,748 MW | 100.0 % |
| MISO | 110,804 MW | 100.0 % |
| ERCO |  71,974 MW | 100.0 % |
| SOCO |  44,130 MW | 100.0 % |
| BPAT |   4,091 MW | 100.0 % |

The threshold for reporting a region was 95 %. All five matched every unit, and
no generator had a blank county. Every region is therefore a result.

**Why the order flips.** The PJM fleet sits in low-stress counties
(capacity-weighted factor 0.378; state medians PA 0.28 vs TX 5.01). ERCO's
thermal fleet includes plants in some of the most water-stressed counties in
the dataset. So a litre consumed in ERCO counts for more than 18 times a litre
consumed in PJM (7.053 vs 0.378), which is enough to overturn PJM's larger raw
volume.

**What is not robust: the size of the effect.**

- **A few counties at AWARE's cap drive the largest factors.** AWARE factors
  are capped at 100.
  - In ERCO, **70.6 %** of the capacity-weighted mean comes from two capped
    counties that hold 5 % of the capacity: Hidalgo (1,881 MW) and Ector
    (1,703 MW).
  - In MISO, **37.5 %** comes from one capped county with 0.4 % of the
    capacity: Mercer, ND (450 MW).
  - With the capacity-weighted **median** instead, ERCO's factor falls from
    7.05 to 1.24 and MISO's from 1.08 to 0.52.
  - **The rank order is unchanged under the median, but ERCO's stress-adjusted
    figure falls from 5,380 to 948 L-eq/MWh.** Quote the ranking, not the
    multiple.
- **Capacity weighting is not generation weighting.** A capped county with a
  lightly run plant pulls the factor as hard as one run at full output. A
  generation-weighted factor would need plant-level generation from EIA-923,
  which isn't in this repo.
- **The factors are annual.** AWARE also provides monthly factors, and summer
  scarcity differs from annual scarcity, especially in ERCO. They were not used
  here.
- **BPAT is small.** It has 4.1 GW of water-consuming thermal capacity, and
  one county (Lewis, WA) holds 32 % of it. Its factor rests on very few plants.

**Consequence for GridShift.** Raw volume and stress-weighted volume answer
different questions. The ranking changes between them, so any cross-region
comparison GridShift makes must say which one it is using, in the same way every
savings figure names its accounting basis.

Reproduce: `PYTHONDONTWRITEBYTECODE=1 python3 data/build_water_stress.py ~/pjm-water-carbon`.
It reads upstream read-only.

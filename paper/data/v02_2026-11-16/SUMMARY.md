# Experiments of version 0.2

Chosen setting: tau 2.5%, three questions per round. Readings as fixed in experiments/PLAN_2026-11-15.md, section "Changes of 16 November 2026": intervals over pairs of products decide, intervals over cases are shown beside them.

## Primary reading

Other product families, expert drawn from the priors, fewer questions than entropy: holds: the interval of entropy minus decision flip lies entirely above zero and the exact test agrees (exact test over pairs: p = 0.0156).

## All blocks (secondary readings)

| Block | Expert | Cases | Pairs | Certified from the priors | Questions: decision flip | Sobol | entropy | random | entropy minus decision flip | 95% by pair | 95% by case | Wrong certified, decision flip | 95% by pair | 95% by case |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| families | prior | 30 | 10 | 11 | 2.91 | 2.89 | 5.01 | 5.62 | 2.11 | 0.83 to 3.57 | 1.30 to 3.02 | 0.2% | 0.0 to 0.7 | 0.0 to 0.6 |
| families | tails | 30 | 10 | 11 | 2.82 | 2.84 | 4.56 | 5.22 | 1.74 | 0.68 to 2.95 | 1.07 to 2.46 | 1.6% | 0.3 to 3.0 | 0.7 to 2.6 |
| bafu12 | prior | 12 | 6 | 7 | 1.94 | 1.93 | 2.50 | 3.84 | 0.56 | 0.05 to 1.32 | 0.10 to 1.09 | 0.3% | 0.0 to 0.8 | 0.0 to 0.8 |
| bafu12 | tails | 12 | 6 | 7 | 1.58 | 1.62 | 2.26 | 3.50 | 0.68 | 0.16 to 1.36 | 0.21 to 1.20 | 4.2% | 1.4 to 7.2 | 1.9 to 6.7 |
| placebo12 | prior | 12 | 6 | 7 | 1.94 | 1.93 | 2.50 | 3.84 | 0.56 | 0.05 to 1.32 | 0.10 to 1.09 | 0.3% | 0.0 to 0.8 | 0.0 to 0.8 |
| placebo12 | tails | 12 | 6 | 7 | 1.58 | 1.62 | 2.26 | 3.50 | 0.68 | 0.16 to 1.36 | 0.21 to 1.20 | 4.2% | 1.4 to 7.2 | 1.9 to 6.7 |
| elcd | prior | 12 | 6 | 7 | 1.72 | 1.71 | 2.36 | 3.36 | 0.64 | 0.08 to 1.32 | 0.12 to 1.27 | 0.3% | 0.0 to 0.8 | 0.0 to 0.8 |
| elcd | tails | 12 | 6 | 7 | 1.92 | 1.81 | 2.50 | 3.44 | 0.59 | 0.16 to 1.07 | 0.18 to 1.02 | 2.8% | 0.8 to 4.7 | 1.1 to 4.7 |
| elcd_ipcc2021 | prior | 12 | 6 | 7 | 1.68 | 1.70 | 2.28 | 3.30 | 0.61 | 0.08 to 1.21 | 0.12 to 1.21 | 0.3% | 0.0 to 0.8 | 0.0 to 0.8 |
| elcd_ipcc2021 | tails | 12 | 6 | 7 | 1.90 | 1.77 | 2.40 | 3.41 | 0.50 | 0.12 to 0.89 | 0.16 to 0.89 | 2.5% | 0.6 to 4.7 | 0.8 to 4.4 |
| cutoff | prior | 18 | 6 | 10 | 2.03 | 2.03 | 2.72 | 4.24 | 0.69 | 0.07 to 1.57 | 0.25 to 1.20 | 0.2% | 0.0 to 0.6 | 0.0 to 0.6 |
| cutoff | tails | 18 | 6 | 10 | 1.77 | 1.81 | 2.40 | 3.80 | 0.63 | 0.13 to 1.27 | 0.27 to 1.02 | 3.1% | 0.9 to 5.4 | 1.5 to 5.0 |
| cff | prior | 18 | 6 | 9 | 2.79 | 2.77 | 4.14 | 5.34 | 1.35 | 0.44 to 2.27 | 0.69 to 2.02 | 0.2% | 0.0 to 0.6 | 0.0 to 0.6 |
| cff | tails | 18 | 6 | 9 | 2.31 | 2.36 | 3.44 | 4.82 | 1.13 | 0.36 to 1.83 | 0.55 to 1.74 | 2.8% | 1.5 to 4.3 | 0.9 to 5.2 |
| uncertainty | prior | 18 | 6 | 3 | 6.62 | 6.33 | 7.13 | 8.94 | 0.51 | 0.12 to 0.88 | 0.12 to 0.88 | 0.3% | 0.0 to 0.9 | 0.0 to 0.8 |
| uncertainty | tails | 18 | 6 | 3 | 6.03 | 5.96 | 7.10 | 7.69 | 1.08 | 0.46 to 1.69 | 0.58 to 1.63 | 0.5% | 0.0 to 1.1 | 0.0 to 1.2 |

**B2, other product families.** Fewer questions than entropy: holds: the interval of entropy minus decision flip lies entirely above zero and the exact test agrees (exact test over pairs: p = 0.0156). Certificate with tail experts: undecided: the interval 0.3 to 3.0% contains 2.5%.

**A3, uncertainty of the datasets.** Fewer questions than entropy: not shown with these cases: the interval contains zero, or the exact test over pairs does not agree (exact test over pairs: p = 0.125). Certificate with tail experts: the target holds: interval 0.0 to 1.1%, entirely at or below 2.5%.

**B3, second database (ELCD hybrid).** Twelve cases in six pairs cannot confirm a statement, so this block is read by the size of the effect. Entropy minus decision flip: 0.64 questions with this database, 0.56 with BAFU on the same 12 cases; difference 0.09 (95% over pairs -0.92 to 1.03): compatible with the base: same sign and the interval of the difference contains zero. Compatible means that no difference was detected, not that the two are equal. Certificate with tail experts, for description: undecided: the interval 0.8 to 4.7% contains 2.5%.

**B3, ELCD hybrid with IPCC 2021.** Twelve cases in six pairs cannot confirm a statement, so this block is read by the size of the effect. Entropy minus decision flip: 0.61 questions with this database, 0.56 with BAFU on the same 12 cases; difference 0.05 (95% over pairs -0.89 to 0.95): compatible with the base: same sign and the interval of the difference contains zero. Compatible means that no difference was detected, not that the two are equal. Certificate with tail experts, for description: undecided: the interval 0.6 to 4.7% contains 2.5%.

## Equivalence with the Sobol index of the impact (new seeds 300 to 329)

- Other product families (the equivalence reading): Sobol of the impact 3.16 questions, decision flip 3.14; difference 0.03 (95% over 10 pairs -0.01 to 0.08): equivalent within 0.5 question, the interval lies inside the margin.
- The 18 benchmark cases: Sobol of the impact 1.98 questions, decision flip 1.99; difference -0.01 (95% over 6 pairs -0.06 to 0.02): equivalent within 0.5 question, the interval lies inside the margin.

## A second wrong expert: beliefs wrong on the side against the verdict (description)

- stress_families: 0.1% of the certified verdicts are wrong (95% over pairs 0.0 to 0.3%), 3.01 questions: not shown to exceed the nominal level.
- stress_bench: 4.8% of the certified verdicts are wrong (95% over pairs 1.9 to 7.8%), 2.41 questions: not shown to exceed the nominal level (the interval contains it).

| Block | Expert | Cases | Pairs | Certified from the priors | Questions: decision flip | Sobol | entropy | random | entropy minus decision flip | 95% by pair | 95% by case | Wrong certified, decision flip | 95% by pair | 95% by case |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stress_families | adverse | 30 | 10 | 11 | 3.01 | 2.99 | 5.09 | 5.81 | 2.08 | 0.98 to 3.32 | 1.37 to 2.85 | 0.1% | 0.0 to 0.3 | 0.0 to 0.3 |
| stress_bench | adverse | 18 | 6 | 10 | 2.41 | 2.40 | 3.26 | 5.54 | 0.86 | 0.22 to 1.57 | 0.38 to 1.37 | 4.8% | 1.9 to 7.8 | 2.0 to 8.3 |

## Illustration on synthetic models (not evidence about real products)

100 synthetic models of 40 choices, 5 sessions each, experts from the priors, tau 2.5%. Intervals: bootstrap over models.

| Questions per round | Decision flip | Sobol of the impact | entropy | Sobol minus decision flip | 95% over models | Models where the two differ | Wrong certified: decision flip | Sobol |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.25 | 5.68 | 21.82 | 0.43 | 0.07 to 0.82 | 76 of 100 | 1.0% | 1.4% |
| 3 | 6.68 | 6.97 | 22.76 | 0.29 | -0.03 to 0.64 | 55 of 100 | 1.0% | 0.8% |

## Sensitivity runs (reported, not read as statements)

| Block | Expert | Cases | Pairs | Certified from the priors | Questions: decision flip | Sobol | entropy | random | entropy minus decision flip | 95% by pair | 95% by case | Wrong certified, decision flip | 95% by pair | 95% by case |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| wash_old | prior | 18 | 6 | 10 | 2.04 | 2.06 | 2.71 | 4.39 | 0.67 | 0.05 to 1.56 | 0.22 to 1.20 | 0.4% | 0.0 to 0.7 | 0.0 to 0.9 |
| wash_old | tails | 18 | 6 | 10 | 1.78 | 1.79 | 2.37 | 3.96 | 0.59 | 0.11 to 1.22 | 0.25 to 0.97 | 3.7% | 1.5 to 5.9 | 2.0 to 5.6 |
| cff_heat_none | prior | 18 | 6 | 9 | 2.84 | 2.83 | 4.13 | 5.41 | 1.29 | 0.42 to 2.18 | 0.66 to 1.94 | 0.2% | 0.0 to 0.6 | 0.0 to 0.6 |
| cff_heat_none | tails | 18 | 6 | 9 | 2.37 | 2.38 | 3.48 | 4.90 | 1.12 | 0.36 to 1.81 | 0.52 to 1.75 | 3.3% | 2.0 to 4.6 | 1.3 to 5.7 |
| cff_heat_district | prior | 18 | 6 | 9 | 2.84 | 2.81 | 4.15 | 5.39 | 1.31 | 0.44 to 2.19 | 0.67 to 1.97 | 0.2% | 0.0 to 0.6 | 0.0 to 0.6 |
| cff_heat_district | tails | 18 | 6 | 9 | 2.33 | 2.37 | 3.51 | 4.82 | 1.17 | 0.37 to 1.89 | 0.55 to 1.83 | 3.3% | 2.2 to 4.4 | 1.5 to 5.6 |
| cff_pet_ssp | prior | 18 | 6 | 9 | 2.77 | 2.78 | 4.12 | 5.31 | 1.34 | 0.44 to 2.27 | 0.68 to 2.02 | 0.0% | 0.0 to 0.7 | 0.0 to 0.7 |
| cff_pet_ssp | tails | 18 | 6 | 9 | 2.29 | 2.36 | 3.40 | 4.79 | 1.11 | 0.36 to 1.79 | 0.54 to 1.71 | 3.0% | 1.9 to 4.3 | 1.1 to 5.4 |
| uncertainty_correlated | prior | 18 | 6 | 8 | 4.23 | 4.28 | 4.79 | 6.01 | 0.56 | 0.18 to 1.00 | 0.26 to 0.93 | 1.2% | 0.2 to 2.1 | 0.2 to 2.3 |
| uncertainty_correlated | tails | 18 | 6 | 8 | 3.50 | 3.50 | 4.11 | 5.11 | 0.61 | 0.14 to 1.23 | 0.24 to 1.10 | 2.9% | 0.4 to 6.7 | 0.4 to 7.2 |

## How much of each prior has a source (benchmark, per region)

The label SOURCE means that the centre has a source. The spread is my choice or my rule in the second column; no prior has an uncertainty that a source measured as such.

| Region | Priors | Assumption | Source for the centre only | Source for the whole distribution |
|---|---|---|---|---|
| PT | 31 | 7 | 22 | 2 |
| DE | 31 | 6 | 22 | 3 |
| BR | 31 | 9 | 20 | 2 |

## Verdict of each case under each model

Lower product at the central value of every choice (A or B), and the share of prior draws in which A is lower.

| Region | A | B | BAFU cut-off | cut-off, washing up to 0.03 kWh | BAFU CFF | CFF, no heat credit | CFF, PET quality 1 | CFF, district heat | ELCD hybrid | ELCD hybrid, IPCC 2021 |
|---|---|---|---|---|---|---|---|---|---|---|
| PT | pet_bottle_1l | glass_refillable_1l | B (0.43) | B (0.41) | B (0.46) | B (0.41) | B (0.47) | B (0.42) | B (0.03) | B (0.03) |
| PT | pet_bottle_1l | aluminium_can_330ml | A (0.99) | A (0.99) | A (1.00) | A (1.00) | A (1.00) | A (1.00) | A (0.87) | A (0.90) |
| PT | pet_bottle_1l | beverage_carton_1l | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) |
| PT | glass_refillable_1l | aluminium_can_330ml | A (0.96) | A (0.97) | A (1.00) | A (1.00) | A (1.00) | A (1.00) | A (1.00) | A (1.00) |
| PT | glass_refillable_1l | beverage_carton_1l | B (0.06) | B (0.07) | B (0.07) | B (0.09) | B (0.07) | B (0.09) | B (0.08) | B (0.06) |
| PT | aluminium_can_330ml | beverage_carton_1l | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) |
| DE | pet_bottle_1l | glass_refillable_1l | A (0.64) | A (0.58) | A (0.73) | A (0.72) | A (0.76) | A (0.72) | B (0.04) | B (0.05) |
| DE | pet_bottle_1l | aluminium_can_330ml | A (1.00) | A (1.00) | A (0.52) | B (0.50) | A (0.58) | B (0.51) | A (0.99) | A (0.99) |
| DE | pet_bottle_1l | beverage_carton_1l | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) |
| DE | glass_refillable_1l | aluminium_can_330ml | A (0.98) | A (0.99) | B (0.28) | B (0.28) | B (0.28) | B (0.28) | A (1.00) | A (1.00) |
| DE | glass_refillable_1l | beverage_carton_1l | B (0.03) | B (0.05) | B (0.00) | B (0.01) | B (0.00) | B (0.01) | B (0.16) | B (0.15) |
| DE | aluminium_can_330ml | beverage_carton_1l | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) |
| BR | pet_bottle_1l | glass_refillable_1l | A (0.65) | A (0.64) | A (0.69) | A (0.68) | A (0.70) | A (0.68) |  |  |
| BR | pet_bottle_1l | aluminium_can_330ml | A (1.00) | A (1.00) | B (0.21) | B (0.21) | B (0.23) | B (0.21) |  |  |
| BR | pet_bottle_1l | beverage_carton_1l | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) | B (0.00) |  |  |
| BR | glass_refillable_1l | aluminium_can_330ml | A (0.88) | A (0.88) | B (0.20) | B (0.20) | B (0.20) | B (0.20) |  |  |
| BR | glass_refillable_1l | beverage_carton_1l | B (0.05) | B (0.05) | B (0.03) | B (0.04) | B (0.03) | B (0.03) |  |  |
| BR | aluminium_can_330ml | beverage_carton_1l | B (0.00) | B (0.00) | B (0.01) | B (0.01) | B (0.01) | B (0.01) |  |  |

Central verdict different from BAFU cut-off under cut-off, washing up to 0.03 kWh: 0 case(s).
Central verdict different from BAFU cut-off under BAFU CFF: 3 case(s): DE glass_refillable_1l against aluminium_can_330ml; BR pet_bottle_1l against aluminium_can_330ml; BR glass_refillable_1l against aluminium_can_330ml.
Central verdict different from BAFU cut-off under CFF, no heat credit: 4 case(s): DE pet_bottle_1l against aluminium_can_330ml; DE glass_refillable_1l against aluminium_can_330ml; BR pet_bottle_1l against aluminium_can_330ml; BR glass_refillable_1l against aluminium_can_330ml.
Central verdict different from BAFU cut-off under CFF, PET quality 1: 3 case(s): DE glass_refillable_1l against aluminium_can_330ml; BR pet_bottle_1l against aluminium_can_330ml; BR glass_refillable_1l against aluminium_can_330ml.
Central verdict different from BAFU cut-off under CFF, district heat: 4 case(s): DE pet_bottle_1l against aluminium_can_330ml; DE glass_refillable_1l against aluminium_can_330ml; BR pet_bottle_1l against aluminium_can_330ml; BR glass_refillable_1l against aluminium_can_330ml.
Central verdict different from BAFU cut-off under ELCD hybrid: 1 case(s): DE pet_bottle_1l against glass_refillable_1l.
Central verdict different from BAFU cut-off under ELCD hybrid, IPCC 2021: 1 case(s): DE pet_bottle_1l against glass_refillable_1l.

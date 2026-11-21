# What the paper states, and what supports it

One row per statement. "Evidence" is a file committed in this repository; "Repeat" is the command that produces it again. The readings were fixed before the runs in [`experiments/record/PLAN_2026-11-13.md`](../experiments/record/PLAN_2026-11-13.md) and [`experiments/record/PLAN_2026-11-15.md`](../experiments/record/PLAN_2026-11-15.md).

Every experiment uses simulated experts on comparisons that I built on real inventory data. The setting is the one of the application: three questions per round and a certificate of 2.5%.

All `Repeat` commands run from the top of the repository and need the unit factors extracted once from openLCA (`python experiments/openlca/extract_factors.py --method "EF 3.1"`). Only the commands marked *openLCA* need openLCA open while they run. `V = bash experiments/benchmark/run_v02_experiments.sh`.

## The method

| # | Statement | Evidence | Repeat |
|---|---|---|---|
| 1 | The expected reduction of p(1 − p) equals p(1 − p) times the first order Sobol index of the verdict; the literal loss min(p, 1 − p) scores zero when no answer can carry p across 1/2; the two losses differ by at most a factor of 2 | [`docs/lemma.md`](lemma.md) | `pytest tests/test_lemma.py` |

## How many questions

| # | Statement | Evidence | Repeat |
|---|---|---|---|
| 2 | **The one confirmatory test.** On 30 cases of ten pairs of packages that the setting was not chosen on, BRANCH asks fewer questions than uncertainty sampling: 2.91 against 5.01, difference 2.11 (95% over pairs 0.83 to 3.57), exact test over pairs p = 0.016 | `paper/data/v02_2026-11-16/families_prior.csv`, `SUMMARY.md` | `V families` |
| 3 | BRANCH asks as many questions as the Sobol index of the impact, within half a question: difference 0.03 (−0.01 to 0.08) on the 30 cases and −0.01 (−0.06 to 0.02) on the 18, on seeds used for nothing else | `paper/data/v02_2026-11-16/eq_families_prior.csv`, `eq_bench_prior.csv` | `V equivalence` |
| 4 | On 100 synthetic models BRANCH asks 0.43 question fewer than the Sobol index of the impact with one question per round (0.07 to 0.82); with three per round the interval contains zero. An illustration, not evidence about real products | `paper/data/v02_2026-11-16/SUMMARY.md` | `V synthetic` |
| 5 | On the 18 beverage cases: 2.06 questions against 2.89 for uncertainty sampling and 4.73 at random. Only 8 cases inform this comparison, so no difference can pass the Holm correction; reported as description | `paper/data/benchmark_tau0.025.csv` | `bash reproduce.sh experiments` |
| 6 | The order of the strategies is the same for acidification, water use and fossil resources; without the location the agent certifies wrongly more often; with uniform priors it asks about one question more | `paper/data/proposal_2026-11-13/` | `bash experiments/benchmark/run_proposal_experiments.sh` |

## The certificate

| # | Statement | Evidence | Repeat |
|---|---|---|---|
| 7 | When the expert answers from the agent's own beliefs, at most 0.9% of the certified verdicts are wrong. This checks the implementation: the mathematics promises it | `paper/data/benchmark.csv`, `benchmark_tau0.025.csv` | as 5 |
| 8 | When the expert answers from the tails of those beliefs, 5.2% of the certificates of the 18 cases are wrong on the seeds that chose the setting, 2.4% on 540 new sessions and 3.3% on 5,400 further sessions, against a target of 2.5%. More questions per round lower the share without bringing it to the target on every run | `paper/data/benchmark_tails_tau0.025.csv`, `benchmark_tails_tau0.025_confirm.csv`, `more_seeds_2026-11-16/` | as 5, then `bash experiments/benchmark/run_more_seeds.sh` |
| 9 | With a second kind of wrong expert (every belief wrong on the side against the verdict): 0.1% wrong in the 30 cases, 4.8% in the 18 (1.9 to 7.8) | `paper/data/v02_2026-11-16/stress_families_adverse.csv`, `stress_bench_adverse.csv` | `V adverse` |

## Robustness

| # | Statement | Evidence | Repeat |
|---|---|---|---|
| 10 | With 21 of 29 unit factors replaced by values from the ELCD 3.2 database, the size of the effect is compatible with the one under BAFU:2026 (difference 0.09 question, −0.92 to 1.03); one central verdict of twelve changes. Twelve cases cannot confirm anything | `paper/data/v02_2026-11-16/elcd_prior.csv`, `bafu12_prior.csv`, `placebo12_prior.csv`, `verdicts.csv`; [`data/second_database/`](../data/second_database/) | `V elcd` |
| 11 | Under the Circular Footprint Formula three central verdicts of the 18 change, all with the can; the heat credit and the quality of recycled PET change at most one more | `paper/data/v02_2026-11-16/cff_prior.csv`, `cff_heat_*`, `cff_pet_ssp_*`, `verdicts.csv` | `V cff` |
| 12 | Widening the washing electricity to include the one published measurement changes no central verdict | `paper/data/v02_2026-11-16/wash_old_prior.csv`, `verdicts.csv` | `V wash` |
| 17 | The third ablation of the proposal. With the spread that the database states for its datasets in the model (the pedigree spreads), the agent certifies 8 of the 18 cases from the priors alone instead of 10 and asks 1.26 questions more (0.37 to 2.36) when the spread goes to the 19 datasets whose runs are consistent, and 3 cases and 4.59 questions more (1.88 to 7.59) when it goes to all 30. 10% and 29% of the sessions then end without a certificate. The effect on wrong certificates has no clear direction (4.7% and 0.5% against 3.1%) | `paper/data/v02_2026-11-16/uncertainty_consistent_*.csv`, `uncertainty_*.csv`, `cutoff_*.csv` | `V uncertainty` (needs the uncertainty in the factor file) |
| 18 | The score of decision flip is a first order index and cannot see a choice that matters only together with another (a test builds such a case). In the 27 cases where the agent asks at the prior, the first order indices of the verdict sum to 0.16 to 0.67, and ranking by the total index gives the same first question in 26 and the same first three in 26. This is measured at the prior only, not after answers | `paper/data/interactions_2026-11-17.csv` | `python experiments/benchmark/interaction_check.py`; `pytest tests/test_probability_checks.py` |

## Correctness of the computation and of the data

| # | Statement | Evidence | Repeat |
|---|---|---|---|
| 13 | BRANCH reproduces openLCA: largest relative difference 3.8 × 10⁻⁹ over the 36 products of the 18 cases and 2.0 × 10⁻⁸ over 166 products in 83 regions. The model it sends, with parameters and formulas, gives the same result in openLCA | `paper/data/validation_openlca.csv`, `validation_all_grids.csv`, `validation_new_materials.csv`, `validation_any_product.csv` | *openLCA:* `python experiments/openlca/validate_openlca.py` and `--all-grids --pairs 1` |
| 20 | The probability of the verdict agrees with openLCA, not only the central value. In 200 worlds drawn from the priors of PET against refillable glass in Portugal, the largest relative difference is 3.2 × 10⁻⁸ and openLCA and BRANCH name the same winner in all 200; openLCA finds PET lower in a share of 0.400 (exact 95% interval 0.332 to 0.471), which contains BRANCH's 0.434 from 20,000 draws. The criteria were fixed before the run (point 17 of `PLAN_2026-11-15.md`) | `paper/data/validation_probability.csv`, `validation_probability_summary.csv` | *openLCA:* `python experiments/openlca/validate_probability.py` |
| 14 | Versions 0.1.1 and 0.1.2 counted secondary aluminium twice. With primary aluminium as the virgin metal one central verdict of 18 changes | `paper/data/aluminium_2026-11-16.csv` | `pytest tests/test_builder.py -k aluminium` |
| 15 | Of the 31 priors of the benchmark in each region, 6 to 9 are assumptions, 20 to 22 have a source for their centre only and 2 or 3 for the whole distribution. Every prior that a published value was checked against contains it | [`data/prior_checks.csv`](../data/prior_checks.csv) | `python experiments/benchmark/prior_sources.py`; `pytest tests/test_prior_checks.py` |
| 16 | In openLCA 2.6.2 the value entered as geometric mean of a lognormal is the mean of the draws, and a negative one gives negative draws | [`experiments/openlca/openlca_lognormal/`](../experiments/openlca/openlca_lognormal/) | the two commands of its README |
| 19 | What the paper says about the database itself: 11,951 processes; 227,083 of the 420,087 exchanges carry a pedigree entry; 14,167 waste outputs carry a lognormal distribution whose geometric mean has the opposite sign of the amount | The database file BAFU:2026 v1.1 (not in this repository: its licence does not allow it) | `python experiments/openlca/read_database.py --db <database folder> counts` and `signs`; each line says whether the number is the one of the paper |

## What the paper does not state

- That BRANCH helps a real person. No one outside the project has used it.
- That BRANCH asks fewer questions than an LCA expert's ranking on real comparisons. It asks as many (row 3).
- That the certificate holds its target when the beliefs are wrong (rows 8 and 9).
- A single number for the uncertainty that the database states for its datasets. Row 17 gives two runs that bound its effect, because 11 of the 30 datasets are reached by the wrong signs of row 16.

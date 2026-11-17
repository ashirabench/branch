# Where each idea of the paper lives in the code

For someone who has read the [paper](../paper/main.pdf) and wants to find, change or check a part of BRANCH. A test reads the tables of this page and fails when a file or a name they cite no longer exists ([`tests/test_review.py`](../tests/test_review.py)), so the page cannot fall behind the code without notice.

## The path of one comparison

```
two product files + region            data/benchmark/*.json, data/examples/, data/regions/*.json
unit impact factors (read once)       data/factors/*.json, never committed
        |
        v
builder.py      completes what the files leave out, from the rules of catalogue.py and regions.py
        |       every completed choice becomes a Choice with a prior and its source
        v
lca_model.py    Model = choices + terms; the difference of impact is a sum of terms
        |
        v
montecarlo.py   State = 20,000 draws of every open choice, and the difference in each draw
        |
        v
agent.py        Session: compute p, certify or ask, take the answer, compute again
        |       query.py scores the open choices; the best three are asked
        v
report.py, manager_report.py, whatif.py     the technical report, the PDF for a manager
olca_bridge.py, formulas.py                 the same model as processes with parameters in openLCA
```

openLCA is used twice and never in between: once to read the unit factors, and at the end to receive the model and recompute it. Nothing in the loop calls openLCA or a language model.

## The agent (paper, Section "Methods")

| Idea of the paper | File | Name in the code |
|---|---|---|
| A modelling choice as a random variable, with its prior and the source of the prior | `branch/beliefs.py` | `Choice` |
| A choice that always stays with the human (value laden) | `branch/beliefs.py` | `value_laden` |
| The answers a person can give, as the agent represents them (the options, or five quantiles) | `branch/beliefs.py` | `answers` |
| The impact as a sum of terms, each an amount times a unit factor | `branch/lca_model.py` | `Term`, `Model` |
| Common random numbers: one set of draws for every candidate question | `branch/lca_model.py` | `sample` |
| Beliefs: the draws, and the difference of impact in each | `branch/montecarlo.py` | `State` |
| The probability that A is lower, and the probability that the verdict is wrong | `branch/montecarlo.py` | `p_a_lower`, `p_flip` |
| What every possible answer to one question would do to the difference | `branch/montecarlo.py` | `conditional_deltas` |
| Revising the beliefs with an answer, or keeping the prior after "I don't know" | `branch/montecarlo.py` | `fix`, `mark_unknown` |
| The loop: compute, certify, ask, reconsider | `branch/agent.py` | `Session`, `next_question`, `answer` |
| The certificate: stop when the probability of a wrong verdict is below the threshold | `branch/agent.py` | `next_question` |
| Value laden choices are asked first and never scored | `branch/agent.py` | `value_laden_first` |
| The person ends the session; the report then says the verdict is not certified | `branch/agent.py` | `finish_early` |
| The whole loop with a simulated expert, for the experiments | `branch/agent.py` | `run_agent` |
| The notice about the critical review of ISO 14044 for public comparisons | `branch/agent.py` | `ISO_PUBLIC_NOTICE` |
| The decision flip score: expected reduction of p(1 − p) | `branch/query.py` | `decision_flip`, `_expected_loss_reduction` |
| The identity with the Sobol index of the verdict (the lemma) | `branch/query.py` | `decision_flip_tp`, `_total_probability_reduction` |
| The baselines: Sobol index of the impact, entropy, least confident, margin, random | `branch/query.py` | `sobol`, `entropy`, `least_confident`, `margin`, `random_strategy` |
| The literal loss min(p, 1 − p) and the entropy of the verdict (ablations) | `branch/query.py` | `decision_flip_min`, `decision_entropy` |
| The setting of the application: certificate of 2.5%, three questions per round | `branch/webapp.py` | `TAU`, `BATCH` |

The proof of the identity is in [`lemma.md`](lemma.md) and its numerical check in `tests/test_lemma.py`.

## From a bill of materials to a model (paper, Section "Materials")

| Idea of the paper | File | Name in the code |
|---|---|---|
| A product described by components, materials and masses; what is not stated becomes a choice | `branch/builder.py` | `load_spec`, `build_model` |
| The life cycle of one product as terms (materials, conversion, transport, washing, disposal) | `branch/builder.py` | `_product_terms` |
| A product described by processes of the database chosen by name | `branch/builder.py` | `process_key`, `_check_exchanges` |
| The rules that complete a silent bill of materials, and the 15 materials | `branch/catalogue.py` | `MATERIALS`, `load_materials` |
| What the location fixes and what it changes in the priors | `branch/regions.py` | `Region`, `load_region` |
| The cut-off rule and the Circular Footprint Formula | `branch/builder.py` | `system_model` |
| The uncertainty that the database states for its datasets (the third ablation) | `branch/builder.py` | `inventory_uncertainty`, `consistent_uncertainty` |
| The 16 impact categories of EF 3.1 | `branch/indicators.py` | `EF31` |
| Reading the unit factors from the open database, once | `branch/olca_extract.py` | `extract`, `unit_impacts` |
| The names of the datasets BRANCH looks for in the database | `branch/olca_extract.py` | `PROCESSES` |
| Loading the factor file; the list of assumptions of a model | `branch/real_cases.py` | `load_factors`, `assumptions` |

## What the person receives (paper, Sections "Outputs and safeguards" and "Validation of the product")

| Idea of the paper | File | Name in the code |
|---|---|---|
| The technical report: verdict, probability of error, who decided each choice | `branch/report.py` | `markdown_report` |
| The report for a manager, one PDF in plain words | `branch/manager_report.py` | `manager_pdf` |
| The smallest single change that reverses the verdict; the stages; all categories | `branch/whatif.py` | `reversals`, `stages`, `indicators` |
| Plain help for every question | `branch/help.py` | `help_for` |
| The page: start a session, record an answer, finish | `branch/webapp.py` | `start_session`, `record_answer`, `finish` |
| The model as processes, parameters and formulas in openLCA | `branch/olca_bridge.py` | `build_objects`, `push_comparison` |
| The amounts as formulas of the choices | `branch/formulas.py` | `trace` |
| The prior of a choice as the uncertainty of a parameter in openLCA | `branch/olca_bridge.py` | `uncertainty_of` |
| openLCA recomputes the model and BRANCH compares | `branch/olca_bridge.py` | `verify_in_openlca` |
| The desktop application and its connection steps | `branch/connector.py` | `checklist`, `send` |

## The experiments (paper, Section "Experiments")

| Idea of the paper | File | Name in the code |
|---|---|---|
| The simulated expert whose answers follow the priors | `branch/cases.py` | `draw_truth` |
| The expert whose answers come from the tails of the priors | `branch/cases.py` | `draw_truth_tails` |
| The expert whose answers are wrong on the side against the verdict | `branch/cases.py` | `draw_truth_adverse` |
| Synthetic models for the illustration | `branch/cases.py` | `synthetic_lca` |
| One session of the benchmark: case, strategy, questions per round, seed | `experiments/benchmark/run_grid.py` | `one_run` |
| The knowledge ablations: no location, uniform priors | `experiments/benchmark/run_grid.py` | `no_location_region`, `make_uniform` |
| The pair of products as the unit; the bootstrap over pairs | `experiments/benchmark/summarize_benchmark.py` | `pair_of`, `pair_index`, `boot_ratio` |
| The exact sign flip test | `experiments/benchmark/summarize_benchmark.py` | `sign_flip_p` |
| The readings fixed before the runs (confirmatory test, equivalence, wrong experts) | `experiments/benchmark/v02_summary.py` | `reading_questions`, `reading_equivalence`, `reading_certificate`, `reading_adverse` |
| First order and total index of the verdict (what the score misses) | `experiments/benchmark/interaction_check.py` | `indices` |
| The probability checked world by world in openLCA | `experiments/openlca/validate_probability.py` | `fixed_world`, `exact_interval`, `summarise` |
| The numbers of the paper, generated from the summaries | `experiments/benchmark/paper_assets.py` | `numbers` |

Which file of results supports which sentence is in [`CLAIMS.md`](CLAIMS.md); the plans written before each run are in [`experiments/record/`](../experiments/record/).

## One question, followed through the code

1. `Session.next_question` in `branch/agent.py` computes the probability that the verdict is wrong (`p_flip`). Below the threshold, or with nothing left to ask, the session ends.
2. Otherwise it calls the strategy. For each open choice, `decision_flip` in `branch/query.py` asks `State.conditional_deltas` what the difference of impact would be under each possible answer, and scores the choice by how much the answers are expected to reduce p(1 − p).
3. `conditional_deltas` in `branch/montecarlo.py` recomputes only the terms that depend on that choice, on the same draws, so the scores of all choices are comparable and take milliseconds.
4. The three best choices are asked. `Session.answer` passes each answer to `State.fix`, which replaces one column of the draws, or to `State.mark_unknown`, which keeps the prior.
5. The loop returns to step 1 with the revised beliefs.

## Where to change what

| To | Change | Then |
|---|---|---|
| Add a material | A file in `data/materials/` (its README gives the fields) | `python experiments/openlca/extract_factors.py --update`, `pytest tests/test_materials.py` |
| Add a region | A file in `data/regions/`, with a source for every number | `pytest tests/test_eu_regions.py tests/test_prior_checks.py` |
| Change a prior | The region file, or the rule in `branch/catalogue.py`; state the source | Every experiment that used the prior is out of date: write the plan first, then run it again |
| Add a way to choose questions | A function in `branch/query.py` and its name in `STRATEGIES` | `pytest tests/test_engine.py`; compare it in `experiments/benchmark/run_grid.py` |
| Use another database | The names in `PROCESSES` of `branch/olca_extract.py` | [`RUNBOOK.md`](RUNBOOK.md), section 4 |
| Publish | Nothing here | [`RUNBOOK.md`](RUNBOOK.md), section 10 |

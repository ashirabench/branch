# Runs fixed in experiments/record/PLAN_2026-11-13.md

Summaries of the runs of 13 November 2026 in the chosen setting (tau 2.5%, three questions per round,
seeds 0 to 29, 18 cases, 540 sessions per row): `<run>_prior.csv` with experts from the priors and
`<run>_tails.csv` with experts from their tails.

- `placebo`: climate change through the new code path. It reproduces `../benchmark_tau0.025.csv` and
  `../benchmark_tails_tau0.025.csv` for batch size 3 exactly.
- `acidification`, `water_use`, `resource_use_fossils`: the verdict settled for another impact category.
- `no_location`, `uniform`: knowledge removed from the agent, verdict for climate change.

The plan reports these runs as descriptive, so the files carry no p values.
Made by `bash experiments/benchmark/run_proposal_experiments.sh` and `python experiments/benchmark/proposal_assets.py`.

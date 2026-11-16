# The larger run of 15 November 2026

Fixed in `experiments/record/PLAN_2026-11-15.md` before it ran: 300 further seeds (2000 to 2299) per case, 5,400 sessions per category, decision flip, three questions per round, tau = 2.5%, experts from the tails.

- `climate_change_tails.csv` and `acidification_tails.csv`: the summaries over the 18 cases.
- `by_case.csv`: sessions, certificates and wrong certificates case by case.

To repeat: `bash experiments/benchmark/run_more_seeds.sh`.

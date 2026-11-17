# Experiments

Four folders, by what a script needs and what it is for.

| Folder | What is in it | Needs openLCA |
|---|---|---|
| [`benchmark/`](benchmark/) | The experiments the paper reports and the scripts that turn them into its tables and figures | no |
| [`openlca/`](openlca/) | Reading unit factors from openLCA and checking BRANCH against it | yes |
| [`data/`](data/) | Building data files from public sources: European regions from Eurostat, the second database from ELCD | no |
| [`record/`](record/) | The plans written before each run, and the scripts of the sessions already run. Kept as a record; nothing here needs running again | |

To repeat everything, use [`reproduce.sh`](../reproduce.sh) at the top of the repository. To see which file supports which statement of the paper, read [`docs/CLAIMS.md`](../docs/CLAIMS.md).

## benchmark

| Script | What it does |
|---|---|
| `run_grid.py` | One comparison: every strategy, batch size and seed, with a simulated expert |
| `run_benchmark.sh` | The 18 cases of the paper (six pairs of four beverage packages in Portugal, Germany and Brazil) |
| `summarize_benchmark.py` | One summary per folder of runs: questions, wrong certificates, intervals over cases and over pairs |
| `run_proposal_experiments.sh` | Other impact categories and the two knowledge ablations |
| `run_more_seeds.sh` | The larger run of 5,400 sessions |
| `run_v02_experiments.sh` | The experiments after the audit of 16 November 2026: other product families, equivalence with the Sobol index, a second wrong expert, a second database, the Circular Footprint Formula, sensitivity runs |
| `v02_summary.py` | Applies to those runs the readings fixed in `record/PLAN_2026-11-15.md` |
| `interaction_check.py` | First order and total index of the verdict for every open choice, to see what the score misses |
| `prior_sources.py` | Counts how much of each prior a source supports |
| `paper_assets.py`, `proposal_assets.py` | Figures, tables and numbers of the paper from the summaries |
| `analyze.py`, `bench_latency.py`, `make_notebook.py` | Plots of one run, time to choose a question, the walkthrough notebook |

## openlca

| Script | What it does |
|---|---|
| `extract_factors.py` | Reads the unit impact factors from the database open in openLCA, once |
| `list_datasets.py`, `audit_factors.py` | Lists what the database offers; checks the reference unit of every factor |
| `validate_openlca.py` | Sends every benchmark case to openLCA and compares its result with BRANCH's |
| `validate_materials.py`, `check_any_product.py`, `check_app_with_openlca.py` | The same check for the added materials, for products described by processes, and through the web application |
| `validate_probability.py` | Checks the probability, not only the central value: 200 random worlds calculated by openLCA, world by world |
| `read_database.py` | Reads a copy of the database file with SQL, without openLCA open: the counts the paper states (processes, exchanges, pedigree entries, lognormal exchanges, lognormal exchanges with the wrong sign) and the exchanges of every dataset BRANCH uses. Needs `pip install -e ".[database]"` |
| `clean_branch_objects.py` | Lists, and with `--delete` removes, the product systems, processes and flows that BRANCH wrote into the open database |
| `extract_uncertainty.py` | Monte Carlo runs of each dataset in openLCA (not used in the results; see the paper) |
| `openlca_lognormal/` | A minimal check of how openLCA draws a lognormal value |

## data

| Script | What it does |
|---|---|
| `make_eu_regions.py` | Writes the 27 European regions from the Eurostat tables in `data/eurostat/` |
| `second_database/read_elcd.py` | Computes 21 unit factors from the ELCD 3.2 database |
| `make_hybrid_factors.py` | Builds the factor file that mixes those 21 factors with BAFU:2026 |

## Names used in the result folders

The result folders keep the short names of the plan. `results/benchmark*` are the 18 cases; `results/proposal` the other categories and ablations; `results/more_seeds` the larger run; and in `results/v02`:

| Name | Meaning |
|---|---|
| `families` | 30 cases of ten other pairs of packages (the confirmatory test) |
| `cutoff`, `cff` | The 18 cases under the cut-off rule and under the Circular Footprint Formula |
| `bafu12`, `placebo12`, `elcd`, `elcd_ipcc2021` | The 12 cases of Portugal and Germany with BAFU factors, with nothing replaced (must equal `bafu12`), with 21 ELCD factors, and with ELCD and IPCC 2021 |
| `eq_families`, `eq_bench` | The equivalence test with the Sobol index of the impact, on new seeds |
| `stress_families`, `stress_bench` | The second wrong expert |
| `wash_old`, `cff_heat_none`, `cff_heat_district`, `cff_pet_ssp` | Sensitivity runs |
| `uncertainty`, `uncertainty_correlated` | Runs with the uncertainty of the datasets (not used in the results) |
| `_prior`, `_tails`, `_adverse` | The simulated expert: drawn from the priors, from their tails, or wrong on the side against the verdict |

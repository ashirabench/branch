# Data

No BAFU data is stored in this repository. The terms of use of the BAFU database allow use in calculators but not redistribution, so every user extracts the unit impact factors locally ([`docs/RUNBOOK.md`](../docs/RUNBOOK.md), section 4). The only LCA values kept here come from ELCD 3.2, whose licence allows distribution with credit: 21 factors (`second_database/`) and the energy recovered per kg burnt (`cff/energy_recovery.json`).

| Folder | Content | In git |
|---|---|---|
| `factors/` | Unit impact factors read from openLCA by `experiments/openlca/extract_factors.py`, one file per database and impact method | No |
| `factors_second/` | Factor files of the second database test, written by `experiments/data/make_hybrid_factors.py`; they carry BAFU values | No |
| `databases/` | The map of each database: which process stands for each thing BRANCH needs, and per which unit. Names only, no values ([`docs/BRING_YOUR_DATABASE.md`](../docs/BRING_YOUR_DATABASE.md)) | Yes |
| `benchmark/` | The four product files of the benchmark: single use PET, refillable glass, aluminium can, beverage carton | Yes |
| `examples/` | Example products for the added materials and for products described by processes | Yes |
| `materials/` | Materials added as data files, one file per material | Yes |
| `regions/` | One file per region with its electricity, transport legs and priors; every prior carries a `SOURCE:` or `ASSUMPTION:` tag | Yes |
| `eurostat/` | Two Eurostat tables read on 15 November 2026 (`env_waspacr`, recycling of packaging waste by material, and `env_wasmun`, municipal waste incinerated and landfilled, 2022 to 2024); `experiments/data/make_eu_regions.py` writes the European region files from them | Yes |
| `cff/` | Parameters of the Circular Footprint Formula from Part C of Annex II of the PEF method, and the energy recovered per kg burnt | Yes |
| `second_database/` | The second database test: which ELCD 3.2 process replaces which BRANCH factor, and the 21 factors computed from it | Yes |
| `prior_checks.csv` | Published values read in the original documents, each with the prior it checks; `tests/test_prior_checks.py` fails when a prior excludes one of them | Yes |

Every result computed from BAFU factors must cite: Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026.

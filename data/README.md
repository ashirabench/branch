# Data

No LCA data is stored in this repository. The terms of use of the BAFU database allow use in calculators but not redistribution, so every user extracts the unit impact factors locally.

| Folder | Content | In git |
|---|---|---|
| `data/factors/` | Unit impact factors extracted from openLCA by `experiments/extract_factors.py` (one JSON per database and LCIA method) | No |
| `data/catalogue_sources/` | Lists of BAFU process names exported from openLCA while the catalogue was built (names and identifiers, no factors) | No |
| `data/regions/` | One file per region with its electricity mix, transport legs and priors; every prior carries a `SOURCE:` or `ASSUMPTION:` tag | Yes |
| `data/materials/` | Materials added as data files, one JSON per material (see its README) | Yes |
| `data/examples/` | Example products for the added materials and for products described by processes | Yes |
| `data/cff/` | Circular Footprint Formula parameters per material, to be copied from PEF Annex C (its README gives the format; no file is filled in yet) | Yes |
| `paper/data/before_disposal_datasets_2026-11-14/` | Summaries of the paper from before PET and polyethylene received their own disposal datasets | Yes |
| `paper/data/more_seeds_2026-11-15/` | The larger run of 5,400 sessions per category fixed in `experiments/PLAN_2026-11-15.md` | Yes |
| `data/prior_checks.csv` | Published values read in the original documents, each with the prior it checks; `tests/test_prior_checks.py` fails when a prior excludes one of them | Yes |
| `data/benchmark/` | Product files (bill of materials) for the benchmark: single use PET, refillable glass, aluminium can, beverage carton. Masses are ASSUMPTION ranges until sourced | Yes |

## Extracting the factors

1. Install openLCA 2.6 and import BAFU:2026 from [openLCA Nexus](https://nexus.openlca.org) together with the free openLCA LCIA methods pack (Environmental Footprint 3.1).
2. Open the database and start the IPC server (Tools > Developer tools > IPC Server, port 8080).
3. Run:

```bash
python experiments/extract_factors.py --methods            # list LCIA methods
python experiments/extract_factors.py --method "EF 3.1"    # writes data/factors/<database>_<method>.json
python experiments/extract_factors.py --update --specs aluminium_can_330ml beverage_carton_1l --region BR-AM
```

## Required citation

Every result computed from these factors must cite: Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026.

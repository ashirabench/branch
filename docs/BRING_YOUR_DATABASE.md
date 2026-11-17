# Using BRANCH with another database

BRANCH does not contain inventory data. It needs, from the database open in your openLCA, one number per impact category for each of about sixty things: a kilogram of bottle grade PET, a kilowatt hour of electricity in a country, a tonne kilometre by lorry, a kilogram of glass sent to landfill. Which process of the database stands for each of these is written in one file, the **map of the database**. To use another database, you write another map. No code changes.

What this page can promise: the map, the extraction that reads it and the checks below exist and are tested. **The whole path has been run with BAFU:2026 only.** The second database of the paper, ELCD 3.2, was read by another route, outside openLCA ([`data/second_database/`](../data/second_database/README.md)). Treat a new database as a new piece of work with its own validation, not as a setting.

## 1. What the map is

[`data/databases/bafu2026.json`](../data/databases/bafu2026.json) is the map of BAFU:2026:

```json
{
  "database": "bafu2026",
  "citation": "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026",
  "location_preference": ["RER", "Europe", "GLO", "Global", "UCTE", "CH", "Switzerland"],
  "grid_name_pattern": "^Electricity, medium voltage, production ([A-Za-z-]+), at grid$",
  "datasets": {
    "pet_granulate_bottle_grade": {
      "names": ["Polyethylene terephthalate, granulate, bottle grade, at plant"],
      "unit": "kg"
    }
  }
}
```

| Field | Meaning |
|---|---|
| `database` | A short name. The factor file is called `data/factors/<database>_<method>.json` |
| `citation` | How every report credits the database. Use the wording its licence asks for |
| `location_preference` | When several processes have the same name and differ only by location, the first location of this list that exists wins |
| `grid_name_pattern` | How the database names the electricity of a country. The part in brackets is the country code. With `--all-grids`, every process that matches becomes the key `electricity_mv_<code>` |
| `datasets` | One entry per thing BRANCH needs. The key is BRANCH's own name for it and must not change |
| `names` | Names of the process in your database, tried in order, without regard to capitals. A name wins when it matches exactly one process |
| `unit` | The unit the factor must be per. BRANCH multiplies the factor by an amount in this unit |
| `note` | Optional: why this dataset, and whether it is a stand-in for something the database lacks |

The key says what is meant only briefly. The entry of the BAFU map says it fully: read the BAFU name and the note, and find the process of your database that describes the same thing, at the same point of the supply chain, per the same unit.

## 2. Write the map of your database

In openLCA, open your database and start the IPC server ([`RUNBOOK.md`](RUNBOOK.md), section 3). Then, in the terminal:

```bash
cp data/databases/bafu2026.json data/databases/mydb.json
python experiments/openlca/list_datasets.py --full          # every process, with unit, to outputs/datasets_<database>.csv
python experiments/openlca/extract_factors.py --find "terephthalate"   # processes whose name contains a text
python experiments/openlca/extract_factors.py --methods     # the impact methods your database has
```

Edit `data/databases/mydb.json`: set `database` and `citation`, and replace the `names` of every entry by the names of your database. You do not need all sixty at once. A comparison needs only the keys of its products and its region:

```bash
python experiments/openlca/extract_factors.py --map mydb --method "EF 3.1" --specs pet_bottle_1l glass_refillable_1l --region DE
```

**It worked when** the last line reads `saved data/factors/mydb_<method>.json: N factors, 0 unresolved`. `? <key>: N candidates` means a name matches several processes: write the exact name. `NOT READ` means no process has that name.

When your database lacks something (BAFU:2026 has no landfill of PET that is current, and no oil fired plant in Brazil), choose the closest dataset, and say so in `note`. A stand-in is a modelling decision: it belongs in your report.

## 3. Check before you trust a number

Do these checks in this order. Each kind of check has found a real error in this project (paper, "Errors found and corrected").

| Check | Command | What it found here |
|---|---|---|
| Every factor is per the unit BRANCH expects | `BRANCH_FACTORS=data/factors/mydb_<method>.json python experiments/openlca/audit_factors.py` | Written after the next check found a factor computed per MJ and used per kWh |
| BRANCH and openLCA give the same result for whole products | `BRANCH_FACTORS=... python experiments/openlca/validate_openlca.py --regions DE --out results/validation_mydb.csv` ([`RUNBOOK.md`](RUNBOOK.md), section 6) | A gap of 2.3% for the refillable glass bottle: the factor per MJ used per kWh |
| Each material uses the dataset of its own kind | Read the list from `list_datasets.py` beside your map | PET and polyethylene were using the disposal datasets of a plastics mixture (up to 5.1% of the impact of a product) |
| No dataset is counted twice | Open in openLCA each dataset of the map and read what it already contains | A production mix of aluminium that already held recycled metal, used beside a recycled content |
| The uncertainty the database states can be used | `python experiments/openlca/read_database.py --db <database folder> signs` | 14,167 waste outputs of BAFU:2026 whose lognormal mean has the opposite sign of the amount |

Always pass `--out` to the validation: without it the script writes the table of the paper, `paper/data/validation_openlca.csv`.

The third and fourth checks have no command, on purpose. The fourth took reading 70 datasets, and it found the one error of this project that changed a conclusion.

To use the factor file afterwards, set `BRANCH_FACTORS` to its path, or keep it as the newest file in `data/factors/`:

```bash
BRANCH_FACTORS=data/factors/mydb_<method>.json python app.py
```

## 4. What does not move with the map

- **The priors are not from the database.** Recycling rates, distances, masses and trips come from statistics and studies named in [`data/regions/`](../data/regions/) and in `branch/catalogue.py`. They stay valid. A few source notes there name BAFU:2026 datasets (for example the mixture of glass colours); with another database, read them as "the datasets of the map".
- **The results of the paper are results with BAFU:2026 and EF 3.1.** With another database the verdicts can change: with 21 factors from ELCD 3.2, one of twelve did ([`CLAIMS.md`](CLAIMS.md), row 10). Run the validation, and do not quote the numbers of the paper for your database.
- **The desktop application names BAFU:2026 in its messages** (`branch/connector.py`). The route of this page is the terminal and `python app.py`.
- **The licence of your database decides what you may publish.** This repository ignores `data/factors/` because the terms of BAFU:2026 do not allow publishing its values. Keep that rule unless your licence says otherwise in writing.
- **The impact method must exist in your database under a name `--method` can find**, with the categories your comparison uses.

# The product file, regions, other products, strategies

What the [README](../README.md) and the [operating guide](RUNBOOK.md) do not cover: how to describe a product, how a region works, how to compare products that are not containers, and which question strategies exist.

## A product file

A product is a bill of materials in a JSON file. Anything you state is fixed; anything you leave out is completed from the codified rules in [`branch/catalogue.py`](../branch/catalogue.py) and becomes an explicit choice the agent may ask about.

```json
{
  "id": "can",
  "name": "Aluminium can 330 ml",
  "volume_l": 0.33,
  "refillable": false,
  "components": [{"id": "body_and_lid", "material": "aluminium", "mass_g": 13}],
  "materials": {"aluminium": {"recycled_content": 0.5}}
}
```

```python
from branch.real_cases import compare

model = compare("aluminium_can_330ml", "beverage_carton_1l", region="DE")   # benchmark names
model = compare("my_product.json", "pet_bottle_1l", region="PT")           # or your own file
```

Materials in the catalogue: PET, HDPE, LDPE, glass, aluminium and liquid packaging board (the six of the benchmark), and nine added as data files that no benchmark case uses: corrugated board, cartonboard, kraft paper, polypropylene, polystyrene, expanded polystyrene, PVC, PLA and steel sheet (a proxy for tinplate, without the tin coating). These materials come with codified rules for containers (forming, distribution, refill, end of life). Any other product is described by processes chosen from the database: see [Any product](#any-product). The benchmark products are in [`data/benchmark/`](../data/benchmark). Before comparing new products, extract only the factors they need:

```bash
python experiments/openlca/extract_factors.py --update --specs aluminium_can_330ml beverage_carton_1l --region DE
```

## Regions

A region is a JSON file in [`data/regions/`](../data/regions) that states only what differs from its parent: electricity mix (or a question, such as national grid versus isolated system), delivery and supply legs by transport mode (lorry, barge, rail), and regional priors such as recycling rates.

```
GLO ── PT, DE
    ├─ EU ── 25 other countries of the European Union, Iceland and Norway
    └─ BR ── BR-N (Northern Brazil) ── BR-AM (Amazonas, Manaus: river supply, isolated grids)
```

```python
compare("aluminium_can_330ml", "beverage_carton_1l", region="BR-AM")
```

For Portugal, Germany and Brazil the recycling rates, the split between incineration and landfill, the recycled content and (for Germany) the trips of refillable bottles come from national statistics: Eurostat and the APA packaging reports for Portugal, BMUV, GVM and ZSVR for Germany, ABIPET, ABRALATAS, Tetra Pak and ABREMA for Brazil. Each value names its document and year in the `SOURCE:` tag. Component masses, trips (outside Germany), washing, distribution distance, the recycled content of aluminium, the recycled content of PET in Brazil and the burden of recycled PET are still `ASSUMPTION:` priors, and the subregions BR-N and BR-AM still rest on assumptions.

For the 25 other countries of the European Union, Iceland and Norway, the recycling rates of plastic, aluminium, steel, paper and glass packaging and the split between incineration and landfill come from two Eurostat tables (`env_waspacr` and `env_wasmun`, years 2022 to 2024) kept in [`data/eurostat/`](../data/eurostat). `python experiments/data/make_eu_regions.py` writes those 28 files from the tables and states its rules; nobody edits them by hand. Eurostat gives one rate for all plastic packaging and none for beverage cartons, and each file says so.

To add a place, copy the closest file, set `parent`, and change only what is different. Every prior keeps its `SOURCE:` or `ASSUMPTION:` tag, and `sources_needed` lists the data still to collect; both appear in the reports.

## Any product

The agent, its questions and its certificate do not depend on packaging. Packaging is the first domain with codified rules and sourced national values; any other product is described by processes of the database (11,951 in BAFU:2026), chosen by their exact name:

```json
{
  "name": "Cotton bag",
  "functional_unit": "carrying the shopping of one household for one year",
  "units_per_functional_unit": 1,
  "exchanges": [
    {"id": "fabric", "stage": "material", "process": "Textile, woven cotton, at plant", "amount": [0.10, 0.20]},
    {"id": "sea freight", "stage": "transport", "process": "Transport, transoceanic freight ship", "amount": [0.5, 3.0]},
    {"id": "disposal", "stage": "end_of_life", "process": "Disposal, textiles, soiled, 25% water, to municipal incineration", "amount": 0.15}
  ]
}
```

- `amount` is for one product, in the unit of the process (the app's search shows it: kg, kWh, t*km, items, hours). A number is a known amount. A pair is the smallest and the largest it could be: BRANCH keeps it as an open choice, labelled as an assumption given by the user, and asks for the exact value only if it can change which product is better.
- `stage` is one of `material`, `manufacturing`, `transport`, `use`, `end_of_life`, `other`.
- When several locations share a process name, add the location code: `"location": "CH"` in a file, or `Tap water, at user @CH` in the app.
- `functional_unit` says what both products do, and `units_per_functional_unit` how many of each are needed for it.
- In the app: open **Other inputs from the openLCA database** under each product, use **Search the openLCA database** to copy the process names, and press **Compare**. With openLCA connected, the app reads the factors of the processes you chose.

What this way does not give: sourced starting values (the ranges are yours) and links between amounts (a mass and its disposal are two separate inputs). Examples: [`data/examples/cotton_bag.json`](../data/examples/cotton_bag.json) and [`pp_bag.json`](../data/examples/pp_bag.json).

## More materials

openLCA has no fixed list of materials: it can assess anything whose processes are in the database you load. To see what BAFU:2026 (or any database) offers:

```bash
python experiments/openlca/list_datasets.py                       # every process, grouped, to outputs/datasets_*.csv
python experiments/openlca/list_datasets.py --grep tinplate --full  # with reference flow, unit and waste flag
```

Then add a material as a data file, without code: [`data/materials/README.md`](../data/materials/README.md).

## Question strategies

| Strategy | What it ranks |
|---|---|
| `decision_flip` | expected reduction of p(1 − p), p = P(I_A < I_B); the first order Sobol index of the verdict (proposed) |
| `decision_flip_min` | ablation with the literal loss min(p, 1 − p); scores near zero when no single answer can flip the verdict, so it asks more questions |
| `decision_entropy` | ablation with the binary entropy of p |
| `decision_flip_tp`, `decision_flip_min_tp` | ablations that estimate the two losses by total probability instead of the plug-in estimate |
| `sobol` | first order variance index of the result, not of the decision |
| `least_confident`, `margin`, `entropy` | uncertainty sampling on each choice's prior (Settles 2009) |
| `random` | random order |

```python
run_agent(model, oracle, strategy="margin", batch_size=3, n_samples=20_000, tau=0.05)
```

## On the GPU

The same code runs on NumPy or CuPy. Install `pip install cupy-cuda12x` and set `BRANCH_BACKEND=cupy`.

```bash
BRANCH_BACKEND=cupy python experiments/benchmark/bench_latency.py
```

## Reference

Settles, Burr. 2009. *Active Learning Literature Survey*. Computer Sciences Technical Report 1648. Madison: University of Wisconsin–Madison.

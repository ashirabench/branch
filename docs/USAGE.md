# Using BRANCH in detail

The [README](../README.md) has the short version. This page has every way of using BRANCH.

## Web App for Companies

No Python and no openLCA needed on the company's side: a browser page where you pick the region, type two bills of materials (part, material, grams), answer the few questions BRANCH asks, and download a one page manager report (PDF, plain English) plus the technical report.

```bash
pip install -e ".[app]"
BRANCH_DEMO=1 python app.py                                          # interface with illustrative numbers
python app.py                                                       # real factors: newest file in data/factors/
```

Open http://127.0.0.1:7860. To host it for companies (Docker, factors mounted on the server and never served), see [`docs/DEPLOY.md`](DEPLOY.md).

## Quick Start

```bash
git clone https://github.com/ashirabench/branch.git
cd branch
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
pytest
```

Run the agent on the toy case with a simulated human:

```python
from branch import run_agent
from branch.cases import toy_packaging, draw_truth

model = toy_packaging()                      # PET vs refillable glass, PLACEHOLDER numbers
truth = draw_truth(model, seed=0)            # a simulated expert answers from this world

result = run_agent(model, oracle=lambda name: truth[name], strategy="decision_flip", truth=truth)
print(result["verdict"], result["p_flip"], result["certified"], result["questions"])
# Glass < PET 0.00135 True 3
```

`oracle(name)` returns the human's answer, or `None` for "I don't know". The result also holds `decided_by` (human, prior or unknown for every choice), the impact intervals of both alternatives, and the full trace.

## Detailed Usage

<details>
<summary>Talk to the agent in the terminal</summary>

```bash
python examples/demo_cli.py --toy                  # placeholder toy case, no openLCA needed
python examples/demo_cli.py --region PT           # real BAFU:2026 factors (any code in data/regions)
```

The agent asks whether the comparison will be disclosed to the public (if so, it states that ISO 14044 requires a critical review panel, which BRANCH prepares for but does not replace) and writes `outputs/report.md`.
</details>

<details>
<summary>Compare any two products</summary>

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

```bash
python examples/demo_cli.py --a aluminium_can_330ml --b beverage_carton_1l --region DE
```

Materials in the catalogue: PET, HDPE, LDPE, glass, aluminium and liquid packaging board (the six of the benchmark), and nine added as data files that no benchmark case uses: corrugated board, cartonboard, kraft paper, polypropylene, polystyrene, expanded polystyrene, PVC, PLA and steel sheet (a proxy for tinplate, without the tin coating). These materials come with codified rules for containers (forming, distribution, refill, end of life). Any other product is described by processes chosen from the database: see [Any product](#any-product). The benchmark products are in [`data/benchmark/`](../data/benchmark). Before comparing new products, extract only the factors they need:

```bash
python experiments/openlca/extract_factors.py --update --specs aluminium_can_330ml beverage_carton_1l --region DE
```
</details>

<details>
<summary>Regions, from Portugal to the Amazon</summary>

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
</details>

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

<details>
<summary>More materials, and how to see everything openLCA can assess</summary>

openLCA has no fixed list of materials: it can assess anything whose processes are in the database you load. To see what BAFU:2026 (or any database) offers:

```bash
python experiments/openlca/list_datasets.py                       # every process, grouped, to outputs/datasets_*.csv
python experiments/openlca/list_datasets.py --grep tinplate --full  # with reference flow, unit and waste flag
```

Then add a material as a data file, without code: [`data/materials/README.md`](../data/materials/README.md).
</details>

<details>
<summary>Manager report (PDF)</summary>

```python
from branch.manager_report import manager_pdf
manager_pdf(result, model, "outputs/report.pdf", public=False)
```

The answer in one sentence and how sure BRANCH is, where the impact comes from (disposal on its own), the smallest change that would flip the answer, what the person said and what BRANCH assumed, and the ISO 14044 notice on public comparisons, always printed.
</details>

<details>
<summary>Send the result to openLCA (connector)</summary>

With openLCA open on the database the factors came from and the IPC server running, BRANCH writes the resolved comparison back into it: one process per alternative, every exchange linked to the BAFU process it came from, one parameter per modelling choice with its value, question, source and who decided it, and a product system ready to calculate. It then calculates both systems in openLCA and compares them with its own numbers.

```bash
python examples/demo_cli.py --a aluminium_can_330ml --b beverage_carton_1l --region DE --push --jsonld outputs/branch.zip
```

```python
from branch import olca_bridge
out = olca_bridge.push_comparison(olca_bridge.client(8080), model, result, verify=True)
out["check"]   # openLCA vs BRANCH, per alternative
```

The amounts are those of one world: the human's answers and the most probable value of every remaining choice. The distributions, the verdict and its probability of being wrong stay in the BRANCH report.
</details>

<details>
<summary>Use real impact factors from openLCA</summary>

The real case needs unit impact factors extracted once from openLCA 2.x with the IPC server running on port 8080. See [`data/README.md`](../data/README.md).

```bash
python experiments/openlca/extract_factors.py --method "EF 3.1"
```

```python
from branch.real_cases import pet_vs_refillable_glass, assumptions

model = pet_vs_refillable_glass(region="PT", category="Climate change")
print(assumptions(model))   # priors that are still placeholders
```
</details>

<details>
<summary>Choose a query strategy</summary>

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
</details>

<details>
<summary>Run on the GPU</summary>

The same code runs on NumPy or CuPy. Install `pip install cupy-cuda12x` and set `BRANCH_BACKEND=cupy`.

```bash
BRANCH_BACKEND=cupy python experiments/benchmark/bench_latency.py
```
</details>

## Experiments

The grid mirrors Faria et al. (2022): every configuration of strategy, batch size and sample size runs over many seeds, and each seed draws a different simulated expert world.

```bash
python experiments/benchmark/run_grid.py --case lca --J 40 --case_seeds 4 --batch 1 3 --seeds 30 --n 10000 --tag lca_J40
python experiments/benchmark/analyze.py results/lca_J40      # boxplots, P(flip) curves, Wilcoxon table
python experiments/benchmark/bench_latency.py                # time to choose one question
```

`--case` is `toy` (placeholder packaging case), `lca` (synthetic linear LCA with J choices), `sym` (synthetic symmetric case) or `real` (any two product files with extracted factors):

```bash
python experiments/benchmark/run_grid.py --case real --a pet_bottle_1l --b glass_refillable_1l --region PT --seeds 30
```


<div align="center">
<h1>BRANCH: Belief Revising Agent for Non-expert Certified Human-in-the-loop LCA</h1>

<a href="docs/BRANCH_Project_Proposal_v2.pdf"><img src="https://img.shields.io/badge/Proposal-v2%20PDF-b31b1b" alt="Proposal"></a>
<a href="paper/main.pdf"><img src="https://img.shields.io/badge/Paper-PDF-b31b1b" alt="Paper"></a>
<a href="https://github.com/ashirabench/branch/releases/latest"><img src="https://img.shields.io/badge/Download-BRANCH%20for%20openLCA-1f6feb" alt="Download"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MPL%202.0-brightgreen" alt="License: MPL 2.0"></a>
<img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
<img src="https://img.shields.io/badge/openLCA-2.6-2e7d32" alt="openLCA 2.6">
<a href="https://github.com/ashirabench/branch/actions/workflows/tests.yml"><img src="https://github.com/ashirabench/branch/actions/workflows/tests.yml/badge.svg" alt="tests"></a>

**Department of Informatics Engineering, University of Coimbra**
Human-Centered Artificial Intelligence, 2026/2027

[Ashira Benchimol](https://github.com/ashirabench)

</div>

<p align="center"><img src="docs/assets/branch_overview.svg" width="100%" alt="BRANCH overview"></p>

## What it is

openLCA calculates what the user models. The modelling choices that ISO 14044 leaves to expert judgement (recycled content, trips of a refillable bottle, recycling rate, electricity mix, distances, which dataset) stay with the user, and that is where a person who is not an LCA expert gets stuck.

BRANCH is a companion agent for openLCA for that person. From a bill of materials and a location it completes a comparison of two products, keeps every choice it had to make as a probability distribution with its source, and asks the person **only the questions whose answer can still change which product is better**. It stops when the verdict is unlikely to be wrong, and it sends the model back to openLCA.

Three things set it apart from other tools around openLCA:

1. **It decides what to ask.** Choices are ranked by their power to reverse the verdict, and a stated rule says when to stop.
2. **What it returns is a native openLCA model.** Every choice is an input parameter, the amounts are formulas of those parameters, and an open choice carries its prior as uncertainty. openLCA recalculates the model and its own Monte Carlo simulation runs on it. Nothing is locked inside BRANCH.
3. **It contains no language model.** Every number comes from a dataset or from a written rule, and every default is labelled with its source or with the word assumption.

## Try it in two minutes

No openLCA needed for a first look; the numbers of this mode are illustrative.

```bash
git clone https://github.com/ashirabench/branch.git && cd branch
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
BRANCH_DEMO=1 python app.py          # open http://127.0.0.1:7860
```

Or in Python, with a simulated person who answers the questions:

```python
from branch import run_agent
from branch.cases import toy_packaging, draw_truth

model = toy_packaging()                      # PET against refillable glass, placeholder numbers
truth = draw_truth(model, seed=0)            # the answers of the simulated person
result = run_agent(model, oracle=lambda name: truth[name], strategy="decision_flip", truth=truth)
print(result["verdict"], result["p_flip"], result["certified"], result["questions"])
# Glass < PET 0.00135 True 3
```

## With your own openLCA

BRANCH never ships inventory data. It reads the unit impact factors once from the database open in your openLCA 2.x (IPC server on port 8080), computes with them, and writes the comparison back.

```bash
python experiments/openlca/extract_factors.py --method "EF 3.1"     # once
python app.py                                                       # the same page, now with real factors
```

[`docs/EXAMPLE.md`](docs/EXAMPLE.md) walks through one comparison from the bill of materials to the parametrised model in openLCA. [`docs/USAGE.md`](docs/USAGE.md) has every other way of using BRANCH: the terminal, product files, regions, products that are not containers, the PDF report, hosting. Installers of the desktop connector for macOS and Windows are on the [releases page](https://github.com/ashirabench/branch/releases/latest).

## Results

Simulated experts, comparisons that I built on real inventory data (BAFU:2026 with EF 3.1), three questions per round and a certificate of 2.5%. [`docs/CLAIMS.md`](docs/CLAIMS.md) lists each statement with the file that supports it and the command that repeats it; the [paper](paper/main.pdf) has the details.

| Statement | Result |
|---|---|
| Fewer questions than uncertainty sampling (the one confirmatory test) | 2.91 against 5.01 questions on 30 cases of ten pairs of packages; difference 2.11, 95% interval over pairs 0.83 to 3.57, p = 0.016 |
| As few questions as the Sobol index of the impact, the ranking an LCA practitioner would use | Difference of 0.03 question on 30 cases and 0.01 on 18, inside a margin of half a question fixed beforehand |
| Fewer questions than the Sobol index of the impact | Shown only on 100 synthetic models with one question per round (0.43 fewer, 0.07 to 0.82); not shown with three per round or on real comparisons |
| The certificate, when the expert's answers contradict the agent's beliefs | 2.4% to 5.2% of the certified verdicts of the 18 beverage cases are wrong against a target of 2.5%; 1.6% in the 30 other cases |
| Agreement with openLCA | Largest relative difference of 2.0 × 10⁻⁸ over 166 products in 83 regions |

## What it does not claim

- No person outside the project has used BRANCH yet. Every expert in the experiments is simulated.
- The certificate is a statement under the agent's beliefs. Cases that it certifies without asking anything carry most of its errors.
- Versions 0.1.1 and 0.1.2 counted secondary aluminium twice. Version 0.2.0 corrects it; the [changelog](CHANGELOG.md) and the paper say what changed.
- The uncertainty that the database states for its datasets is not in the results: the copy of BAFU:2026 used here has waste outputs whose lognormal geometric mean has the opposite sign of the amount, a known kind of database error, and a Monte Carlo simulation in openLCA then subtracts the treatment of waste ([`experiments/openlca/openlca_lognormal/`](experiments/openlca/openlca_lognormal/)).
- BRANCH covers attributional studies (ILCD Situation A). It does not replace the critical review that ISO 14044 requires for comparative assertions disclosed to the public.

## Where things are

| Folder | What is in it |
|---|---|
| [`branch/`](branch/) | The agent: beliefs, Monte Carlo, question strategies, the BDI loop, the builder of models, the reports, the openLCA connector, the web application |
| [`data/`](data/) | Product files, materials, regions and their sources. Inventory factors are never committed |
| [`experiments/`](experiments/) | The experiments of the paper, the checks against openLCA, the scripts that build data files, and the plans written before each run ([guide](experiments/README.md)) |
| [`examples/`](examples/) | A terminal demonstration |
| [`tests/`](tests/) | 225 tests, run on every push |
| [`paper/`](paper/) | The paper and the summaries its numbers come from |
| [`docs/`](docs/) | The claims and their evidence, the example, the usage guide, the proof of the identity behind the score, the deployment guide |
| [`packaging/`](packaging/) | The desktop connector for macOS and Windows |

## Reproducing the paper

```bash
bash reproduce.sh            # install, extract factors from openLCA, tests, experiments, figures, paper/main.pdf
bash reproduce.sh paper      # figures, tables and the PDF from the committed summaries (no openLCA)
QUICK=1 bash reproduce.sh    # 3 seeds and one question per round, to check the pipeline in minutes
```

The numbers of the benchmark are generated into `paper/tables/numbers.tex`, and a test compares the table of the later experiments with the committed summaries, so prose and data cannot drift apart.

## Citation

```bibtex
@misc{benchimol2026branch,
  title  = {Asking Only What Can Flip the Verdict: A Human-in-the-Loop {BDI} Agent
            for Comparative Life Cycle Assessment},
  author = {Benchimol, Ashira},
  year   = {2026},
  note   = {Lab project paper, Human-Centered Artificial Intelligence,
            Department of Informatics Engineering, University of Coimbra},
  url    = {https://github.com/ashirabench/branch}
}
```

## Independence

BRANCH is an independent project. It is not affiliated with, sponsored by or endorsed by GreenDelta GmbH, the developer of openLCA; "for openLCA" says only which software BRANCH works with. openLCA and the other product names mentioned here belong to their owners.

## Acknowledgements

BRANCH builds on [openLCA](https://www.openlca.org), [olca-ipc](https://github.com/GreenDelta/olca-ipc.py) and [olca-schema](https://github.com/GreenDelta/olca-schema) by GreenDelta, and on the Life Cycle Inventory database of the Swiss Federal Administration (BAFU:2026). I thank the Human-Centered AI course at the University of Coimbra.

## References

BAFU (Federal Office for the Environment). 2026. *Life Cycle Inventory Database of the Swiss Federal Administration, BAFU:2026*, version 1.1. Bern: Federal Office for the Environment.

European Commission, Joint Research Centre. 2010. *International Reference Life Cycle Data System (ILCD) Handbook: General Guide for Life Cycle Assessment, Detailed Guidance*. EUR 24708 EN. Luxembourg: Publications Office of the European Union.

Faria, Bruno, Dylan Perdigão, Joana Brás, and Luis Macedo. 2022. "The Joint Role of Batch Size and Query Strategy in Active Learning-based Prediction: A Case Study in the Heart Attack Domain." In *Progress in Artificial Intelligence: EPIA 2022*. Cham: Springer.

ISO. 2006. *ISO 14040:2006 Environmental Management: Life Cycle Assessment: Principles and Framework*. Geneva: International Organization for Standardization.

Settles, Burr. 2009. *Active Learning Literature Survey*. Computer Sciences Technical Report 1648. Madison: University of Wisconsin–Madison.

Wooldridge, Michael. 2009. *An Introduction to MultiAgent Systems*. 2nd ed. Chichester: Wiley.

The full reference list is in the [proposal](docs/BRANCH_Project_Proposal_v2.pdf).

## License

Code released under the [Mozilla Public License 2.0](LICENSE), the licence of openLCA. LCA data are not included and remain under their own terms of use.

## Use of AI tools

AI (Claude, by Anthropic) was used as a support tool at every stage of this project: research, writing, code, tests, experiments, documentation and repository maintenance, including commits and pull requests. I defined the problem, took every design decision, ran the factor extraction and every validation in openLCA, reviewed every change before it entered the repository and checked every reference against its source. The Human-Centered AI course allows the use of AI tools, and the professor was informed.

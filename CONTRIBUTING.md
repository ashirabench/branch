# Contributing to BRANCH

Thank you for your interest. BRANCH is a research prototype developed for the Human-Centered AI course at the University of Coimbra, so issues and suggestions are very welcome.

## Issues

Please open a GitHub issue with a short description, the command you ran, and the full error message. For questions about LCA modelling choices, cite the ISO 14044 clause or ILCD Handbook section you have in mind.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Install in editable mode: `pip install -e ".[dev,experiments,app]"`.
3. Add or update tests in `tests/` and run the three checks GitHub runs: `ruff check .`, `mypy` and `pytest`.
4. Keep the agent free of language models: every decision must be traceable to data, a codified rule or the human.
5. Never commit LCA data (BAFU, ELCD or extracted factors). Their terms of use do not allow redistribution; see [`data/README.md`](data/README.md).

## Rules of the code

They are tests ([`tests/test_architecture.py`](tests/test_architecture.py)), so a change that breaks one fails before it is merged.

- **No function longer than 50 lines.** One function, one job. The model builder once had a function of 320 lines, and that is where the errors of the model were found.
- **No module of the package longer than 600 lines**; divide by subject.
- **The core of the agent** (`beliefs`, `lca_model`, `montecarlo`, `query`, `agent`, `backend`) imports nothing but itself: no openLCA, no page, no report.
- **No module imports another in a circle**, and an import goes inside a function only for what is optional (openLCA, the page, the GPU).
- **A caught error is said.** `except Exception` must name the error and show it, log it or raise it again.
- **One module knows where the data is** (`branch/paths.py`), and nothing keeps state between calls.
- **A change to the model builder must leave the models identical**, or say why not: `tests/test_builder_golden.py`.

## Priors and data

Every prior is tagged `SOURCE` (with a citation) or `ASSUMPTION` (a placeholder). The defaults are in `branch/catalogue.py`, the national and regional values in `data/regions/*.json` and the product masses in `data/benchmark/*.json`. A pull request that replaces an `ASSUMPTION` with a sourced prior is the most useful contribution. Add each published value you read to `data/prior_checks.csv`, so that `tests/test_prior_checks.py` keeps it inside the range.

## License

By contributing, you agree that your contributions will be licensed under the [Mozilla Public License 2.0](LICENSE), the licence of openLCA.

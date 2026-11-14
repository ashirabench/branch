# Contributing to BRANCH

Thank you for your interest. BRANCH is a research prototype developed for the Human-Centered AI course at the University of Coimbra, so issues and suggestions are very welcome.

## Issues

Please open a GitHub issue with a short description, the command you ran, and the full error message. For questions about LCA modelling choices, cite the ISO 14044 clause or ILCD Handbook section you have in mind.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Install in editable mode: `pip install -e ".[dev]"`.
3. Add or update tests in `tests/` and run `pytest`.
4. Keep the agent free of language models: every decision must be traceable to data, a codified rule or the human.
5. Never commit LCA data (BAFU, ELCD or extracted factors). Their terms of use do not allow redistribution; see [`data/README.md`](data/README.md).

## Priors and data

Every prior is tagged `SOURCE` (with a citation) or `ASSUMPTION` (a placeholder). The defaults are in `branch/catalogue.py`, the national and regional values in `data/regions/*.json` and the product masses in `data/benchmark/*.json`. A pull request that replaces an `ASSUMPTION` with a sourced prior is the most useful contribution. Add each published value you read to `data/prior_checks.csv`, so that `tests/test_prior_checks.py` keeps it inside the range.

## License

By contributing, you agree that your contributions will be licensed under the [Mozilla Public License 2.0](LICENSE), the licence of openLCA.

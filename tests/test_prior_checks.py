"""Every published value in data/prior_checks.csv must lie inside the prior it checks.

The table lists values read in the original documents. A prior that excluded one of
them would be wrong, so this test fails when a prior is narrowed past a published value.
"""
import csv
import os

import numpy as np
import pytest

from branch.builder import required_factor_keys
from branch.real_cases import compare
from tests.test_builder import BENCH, CAT

ROOT = os.path.join(os.path.dirname(__file__), "..")


def factors():
    keys = sorted({k for r in ("PT", "DE", "BR") for k in required_factor_keys(BENCH, r)})
    rng = np.random.default_rng(0)
    return {"method": "synthetic", "path": "synthetic.json", "citation": "synthetic",
            "factors": {k: {"impacts": {CAT: float(rng.uniform(0.01, 5))}} for k in keys}}


ROWS = [r for r in csv.DictReader(open(os.path.join(ROOT, "data", "prior_checks.csv")))
        if r["read_in_original"] == "yes" and r["comparable"] == "yes"]


@pytest.mark.parametrize("row", ROWS, ids=lambda r: f"{r['choice']}@{r['region']}")
def test_published_value_is_inside_the_prior(row):
    a, b = row["pair"].split("|")
    model = compare(a, b, region=row["region"], factors=factors())
    choice = model.by_name[row["choice"]]
    dist = choice._frozen()
    low, high = dist.ppf(0.0), dist.ppf(1.0)
    assert low <= float(row["value"]) <= high, (
        f"{row['choice']} in {row['region']}: {row['value']} {row['unit']} from {row['source']} "
        f"is outside the prior [{low:g}, {high:g}]")

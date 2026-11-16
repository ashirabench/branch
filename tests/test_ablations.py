"""Knowledge ablations of experiments/record/PLAN_2026-11-13.md: the code path, not the results."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "experiments", "benchmark"))

from branch.agent import run_agent  # noqa: E402
from branch.builder import required_factor_keys  # noqa: E402
from branch.cases import draw_truth  # noqa: E402
from branch.real_cases import compare  # noqa: E402
from run_grid import make_uniform, no_location_region  # noqa: E402
from tests.test_builder import BENCH, CAT  # noqa: E402

PAIR = ("pet_bottle_1l", "glass_refillable_1l")


def factors():
    keys = sorted({k for r in ("PT", "DE", "BR") for k in required_factor_keys(BENCH, r)} | {"electricity_mv_GLO"})
    rng = np.random.default_rng(0)
    return {"method": "synthetic", "path": "synthetic.json", "citation": "synthetic",
            "factors": {k: {"impacts": {CAT: float(rng.uniform(0.01, 5))}} for k in keys}}


def test_no_location_model_has_the_choices_of_every_national_model():
    f = factors()
    agent = compare(*PAIR, region=no_location_region(), factors=f)
    for region in ("PT", "DE", "BR"):
        national = compare(*PAIR, region=region, factors=f)
        assert [c.name for c in agent.choices] == [c.name for c in national.choices]
        for c in national.choices:
            if c.kind == "categorical":
                assert c.labels == agent.by_name[c.name].labels
    assert not any(c.source.startswith("SOURCE") and "Eurostat" in c.source for c in agent.choices)


def test_uniform_keeps_ranges_and_options():
    f = factors()
    national = compare(*PAIR, region="DE", factors=f)
    agent = make_uniform(compare(*PAIR, region="DE", factors=f))
    for c in national.choices:
        u = agent.by_name[c.name]
        if c.kind == "categorical":
            assert u.labels == c.labels and np.allclose(u.probs, 1 / len(c.labels))
        else:
            assert u.prior[0] == "uniform"
            assert np.isclose(u.ppf(0.0), c.ppf(0.0)) and np.isclose(u.ppf(1.0), c.ppf(1.0))


def test_reference_verdict_decides_whether_a_certificate_is_wrong():
    f = factors()
    model = compare(*PAIR, region="PT", factors=f)
    truth = draw_truth(model, 0)
    own = bool(model.delta_at(truth) < 0)
    kw = dict(strategy="decision_flip", batch_size=3, n_samples=2000, tau=0.025, seed=0, truth=truth)
    same = run_agent(compare(*PAIR, region="PT", factors=f), lambda n: truth[n], reference_a_lower=own, **kw)
    plain = run_agent(compare(*PAIR, region="PT", factors=f), lambda n: truth[n], **kw)
    flipped = run_agent(compare(*PAIR, region="PT", factors=f), lambda n: truth[n], reference_a_lower=not own, **kw)
    assert same["correct"] == plain["correct"] and same["questions"] == plain["questions"]
    assert flipped["correct"] == (not plain["correct"])

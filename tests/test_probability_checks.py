"""Checks behind the validation of the probability and behind the reading of interactions."""
import importlib.util
import os

import numpy as np
from scipy import stats

from branch.cases import toy_packaging
from branch.montecarlo import State

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(*parts):
    path = os.path.join(os.path.dirname(HERE), *parts)
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_draws_follow_the_priors():
    """Every continuous choice: the draws of the model against the distribution written in its prior
    (Kolmogorov and Smirnov distance), and against the mean that the definition gives by hand."""
    model = toy_packaging()
    S = np.asarray(model.sample(20000, 0), dtype=float)
    checked = 0
    for j, c in enumerate(model.choices):
        if c.kind != "continuous":
            continue
        dist, p = c.prior
        d = stats.kstest(S[:, j], c._frozen().cdf).statistic
        assert d < 0.015, (c.name, d)
        by_hand = {"uniform": lambda: (p["low"] + p["high"]) / 2, "normal": lambda: p["mean"],
                   "triangular": lambda: (p["low"] + p["mode"] + p["high"]) / 3,
                   "beta": lambda: p["a"] / (p["a"] + p["b"]),
                   "lognormal": lambda: p["median"] * np.exp(p["sigma"] ** 2 / 2)}[dist]()
        assert abs(S[:, j].mean() - by_hand) <= 0.02 * abs(by_hand) + 1e-9, (c.name, S[:, j].mean(), by_hand)
        checked += 1
    assert checked >= 3


def test_exact_interval_and_summary():
    vp = _load("experiments", "openlca", "validate_probability.py")
    lo, hi = vp.exact_interval(80, 200)
    assert 0.33 < lo < 0.34 and 0.47 < hi < 0.48          # Clopper and Pearson, 80 of 200
    assert vp.exact_interval(0, 10)[0] == 0.0 and vp.exact_interval(10, 10)[1] == 1.0
    worlds = [{"olca_a": 1.0, "olca_b": 2.0, "branch_a": 1.0, "branch_b": 2.0}] * 3 + \
             [{"olca_a": 3.0, "olca_b": 2.0, "branch_a": 3.0 * (1 + 1e-9), "branch_b": 2.0}]
    s = vp.summarise(worlds, 0.7)
    assert s["same_winner"] == 4 and s["p_openlca_worlds"] == 0.75 and s["branch_inside_interval"]
    assert s["largest_relative_difference"] < 2e-9
    assert not vp.summarise(worlds, 0.01)["branch_inside_interval"]


class _PureInteraction:
    """Two choices with answers -1 and +1; A wins when their product is negative. Neither answer alone
    says anything about the verdict, both together decide it."""

    def __init__(self, n=4000, seed=0):
        rng = np.random.default_rng(seed)
        self.x = {"u": rng.choice([-1.0, 1.0], n), "v": rng.choice([-1.0, 1.0], n)}
        self.delta = self.x["u"] * self.x["v"]
        self.open = ["u", "v"]

    def conditional_deltas(self, name):
        other = self.x["v" if name == "u" else "u"]
        return np.stack([-other, other]), np.array([0.5, 0.5])


def test_first_order_misses_a_pure_interaction_and_the_total_index_sees_it():
    ic = _load("experiments", "benchmark", "interaction_check.py")
    ind, p = ic.indices(_PureInteraction())
    assert 0.45 < p < 0.55
    for name in ("u", "v"):
        first, total = ind[name]
        assert first < 0.01 and total > 0.95


def test_indices_agree_when_choices_do_not_interact_through_the_verdict():
    """One choice decides the verdict alone: first order and total index are both 1 for it, 0 for the other."""
    class OneDecides(_PureInteraction):
        def __init__(self):
            super().__init__()
            self.delta = self.x["u"].copy()

        def conditional_deltas(self, name):
            if name == "u":
                n = len(self.delta)
                return np.stack([-np.ones(n), np.ones(n)]), np.array([0.5, 0.5])
            return np.stack([self.delta, self.delta]), np.array([0.5, 0.5])
    ic = _load("experiments", "benchmark", "interaction_check.py")
    ind, _ = ic.indices(OneDecides())
    assert ind["u"][0] > 0.95 and ind["u"][1] > 0.95 and ind["v"][0] < 0.01 and ind["v"][1] < 0.01

"""Numerical checks of docs/lemma.md on the engine's own estimates."""
import numpy as np

from branch.beliefs import Choice
from branch.cases import toy_packaging
from branch.lca_model import Model, Term
from branch.montecarlo import State, p_a_lower
from branch.query import STRATEGIES


def _indicator_sobol(state, name):
    """S_j of D = 1{delta < 0}, computed directly from conditional verdict probabilities."""
    d, w = state.conditional_deltas(name)
    pk = (d < 0).mean(axis=1)
    pbar = float((w * pk).sum())
    return float((w * (pk - pbar) ** 2).sum()) / (pbar * (1 - pbar)), pbar


def test_proposition_1_decision_flip_is_the_sobol_index_of_the_verdict():
    m = toy_packaging()
    st = State(m, m.sample(200_000, seed=11))
    scores = STRATEGIES["decision_flip"](st, np.random.default_rng(0))
    p = float(p_a_lower(st.delta))
    for name in st.open:
        s_j, pbar = _indicator_sobol(st, name)
        # R_g(j) = p(1-p) S_j, up to the Monte Carlo gap between p and sum_k w_k p_k
        gap = abs((p - p * p) - (pbar - pbar * pbar))
        assert abs(scores[name] - pbar * (1 - pbar) * s_j) <= gap + 1e-12
    ranked = sorted(st.open, key=lambda n: scores[n], reverse=True)
    by_sobol = sorted(st.open, key=lambda n: _indicator_sobol(st, n)[0], reverse=True)
    assert ranked[0] == by_sobol[0]


def _leaning_model():
    """delta = 1 + x0 + 0.1 x1: the verdict leans to B, and no single answer flips it."""
    choices = [Choice("x0", "continuous", ("uniform", {"low": -0.9, "high": 0.9}), "TEST"),
               Choice("x1", "continuous", ("normal", {"mean": 0.0, "sd": 1.0}), "TEST")]
    terms = [Term("base", [], lambda xp, v: 1.0),
             Term("t0", ["x0"], lambda xp, v: v["x0"]),
             Term("t1", ["x1"], lambda xp, v: 0.1 * v["x1"])]
    return Model(choices, terms)


def test_proposition_2_the_literal_loss_stalls_and_the_smooth_one_does_not():
    m = _leaning_model()
    st = State(m, m.sample(100_000, seed=3))
    rng = np.random.default_rng(0)
    p = float(p_a_lower(st.delta))
    assert 0 < p < 0.05
    for name in st.open:
        d, _ = st.conditional_deltas(name)
        assert ((d < 0).mean(axis=1) < 0.5).all()          # no answer carries p across 1/2
    flat = STRATEGIES["decision_flip_min"](st, rng)
    smooth = STRATEGIES["decision_flip"](st, rng)
    for name in st.open:
        d, w = st.conditional_deltas(name)
        pbar = float((w * (d < 0).mean(axis=1)).sum())
        # R_m(j) = p - sum_k w_k p_k: only the Monte Carlo gap, no information about j
        assert abs(flat[name] - (p - pbar)) < 1e-12
        # R_g(j) = gap + Var_k(p_k): the variance term carries the information
        pk = (d < 0).mean(axis=1)
        var = float((w * (pk - pbar) ** 2).sum())
        gap = (p - p * p) - (pbar - pbar * pbar)
        assert abs(smooth[name] - (gap + var)) < 1e-12
        if name == "x0":
            assert var > 0
    # with the total probability estimator the literal loss is exactly zero, the smooth one is not
    tp_min = STRATEGIES["decision_flip_min_tp"](st, rng)
    tp = STRATEGIES["decision_flip_tp"](st, rng)
    assert all(abs(v) < 1e-15 for v in tp_min.values())
    assert tp["x0"] > 0 and tp["x1"] > 0


def test_proposition_3_bounds():
    p = np.linspace(0, 1, 10_001)
    m, g = np.minimum(p, 1 - p), p * (1 - p)
    assert (m <= 2 * g + 1e-15).all() and (2 * g <= 2 * m + 1e-15).all()


def test_total_probability_estimator_is_exactly_the_sobol_index():
    m = toy_packaging()
    st = State(m, m.sample(20_000, seed=5))
    tp = STRATEGIES["decision_flip_tp"](st, np.random.default_rng(0))
    for name in st.open:
        s_j, pbar = _indicator_sobol(st, name)
        assert np.isclose(tp[name], pbar * (1 - pbar) * s_j, rtol=1e-9, atol=1e-15)

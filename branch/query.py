"""Query strategies (Step 5): which open modelling choice to ask the human next.

Every strategy returns {choice_name: score}; the agent asks the highest.

Baselines from the course (Settles 2009; Macedo, HCAI ch. 4) applied to the
prior of each choice:
    random, least_confident, margin, entropy
Baseline from the LCA literature:
    sobol      first order variance based sensitivity index S_j
Proposed (expected error reduction on the VERDICT, preposterior analysis,
Howard 1966; "Expected Error Reduction" in the course slides):
    decision_flip      reduction of the smooth loss p(1-p), p = P(I_A < I_B).
                       Equivalent to the first order Sobol index of the
                       decision indicator 1{I_A < I_B} instead of the result.
    decision_flip_min  ablation: the literal loss min(p, 1-p) from the
                       proposal. Its kink makes the myopic agent stall when
                       no single answer can flip the verdict.
    decision_entropy   ablation: binary entropy of p as the loss.

Note for the paper: the uncertainty baselines look only at the prior of a
choice, not at its effect on the result; sobol looks at the effect on the
variance of the result, not on the decision. decision_flip looks at the
decision. That contrast is the central claim.
"""
import numpy as np

from .montecarlo import p_a_lower


def _prior_stat(state, fn):
    return {n: float(fn(state.model.by_name[n].answer_probs())) for n in state.open}


def random_strategy(state, rng):
    return {n: float(rng.random()) for n in state.open}


def least_confident(state, rng):
    return _prior_stat(state, lambda p: 1.0 - p.max())


def margin(state, rng):
    def f(p):
        top = np.sort(p)[::-1]
        return -(top[0] - (top[1] if len(top) > 1 else 0.0))
    return _prior_stat(state, f)


def entropy(state, rng):
    return _prior_stat(state, lambda p: float(-(p * np.log(p + 1e-12)).sum()))


def sobol(state, rng):
    var_total = float(state.delta.var())
    out = {}
    for n in state.open:
        d, w = state.conditional_deltas(n)
        means = d.mean(axis=1)
        mu = (w * means).sum()
        out[n] = float((w * (means - mu) ** 2).sum()) / (var_total + 1e-300)
    return out


def _expected_loss_reduction(loss):
    def strategy(state, rng):
        xp = state.model.xp
        now = float(loss(p_a_lower(state.delta, xp), xp))
        out = {}
        for n in state.open:
            d, w = state.conditional_deltas(n)
            out[n] = now - float((w * loss(p_a_lower(d, xp), xp)).sum())
        return out
    return strategy


def _total_probability_reduction(loss):
    """Same expected loss reduction, but the loss before the answer is taken at
    sum_k w_k p_k (law of total probability over the K represented answers)
    instead of the sample estimate of p. Then R(j) for p(1-p) is exactly the
    Sobol index of the verdict times p(1-p), and min(p, 1-p) scores exactly 0
    when no answer crosses 1/2 (docs/lemma.md). Ablation for the paper."""
    def strategy(state, rng):
        xp = state.model.xp
        out = {}
        for n in state.open:
            d, w = state.conditional_deltas(n)
            pk = p_a_lower(d, xp)
            out[n] = float(loss((w * pk).sum(), xp)) - float((w * loss(pk, xp)).sum())
        return out
    return strategy


decision_flip = _expected_loss_reduction(lambda p, xp: p * (1.0 - p))
decision_flip_tp = _total_probability_reduction(lambda p, xp: p * (1.0 - p))
decision_flip_min_tp = _total_probability_reduction(lambda p, xp: xp.minimum(p, 1.0 - p))
decision_flip_min = _expected_loss_reduction(lambda p, xp: xp.minimum(p, 1.0 - p))
decision_entropy = _expected_loss_reduction(
    lambda p, xp: -(p * xp.log(p + 1e-12) + (1.0 - p) * xp.log(1.0 - p + 1e-12)))


STRATEGIES = {
    "random": random_strategy,
    "least_confident": least_confident,
    "margin": margin,
    "entropy": entropy,
    "sobol": sobol,
    "decision_flip": decision_flip,
    "decision_flip_min": decision_flip_min,
    "decision_entropy": decision_entropy,
    "decision_flip_tp": decision_flip_tp,
    "decision_flip_min_tp": decision_flip_min_tp,
}

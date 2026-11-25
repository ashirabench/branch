"""Monte Carlo conditioned on human answers (Step 4).

State holds one shared sample matrix S (N x J), the cached value of every
term, and delta = I_A - I_B per sample. Fixing a choice recomputes only the
terms that depend on it (incremental update). conditional_deltas evaluates
every possible answer of one choice at once, reusing all other terms.
"""
from typing import Any

from .beliefs import Choice  # noqa: F401  (re-exported for convenience)
from .lca_model import Model

RELATIVE_TIE = 1e-9


class State:
    def __init__(self, model: Model, S: Any) -> None:
        xp = model.xp
        self.model = model
        self.S = S.copy()
        self.contrib = xp.stack([model.term_value(m, self.S) for m in range(len(model.terms))])
        self.delta = self._snap(self.contrib.sum(axis=0))
        self.open = [c.name for c in model.choices if c.is_open() and c.askable]   # what can still be asked
        self.fixed = {c.name: c.encode(c.fixed) for c in model.choices if not c.is_open()}
        self.unknown: list = []  # asked, human said "I don't know": prior kept

    def fix(self, name: str, value: float) -> None:
        m_ = self.model
        self.S[:, m_.idx[name]] = float(value)
        for m in m_.terms_of[name]:
            new = m_.term_value(m, self.S)
            self.delta += new - self.contrib[m]
            self.contrib[m] = new
        self.delta = self._snap(self.delta)
        self.open.remove(name)
        self.fixed[name] = float(value)

    def mark_unknown(self, name: str) -> None:
        """The human does not know: keep the distribution, never ask again."""
        self.open.remove(name)
        self.unknown.append(name)

    def conditional_deltas(self, name: str) -> Any:
        """delta for every possible answer of `name`: (K, N) and weights (K,)."""
        xp, m_ = self.model.xp, self.model
        vals, w = m_.by_name[name].answers()
        V = xp.asarray(vals, dtype=xp.float64).reshape(-1, 1)
        d = xp.broadcast_to(self.delta, (V.shape[0], self.delta.shape[0])).copy()
        for m in m_.terms_of[name]:
            d += m_.term_value(m, self.S, override=(name, V)) - self.contrib[m]
        return self._snap(d), xp.asarray(w)

    def _snap(self, d: Any) -> Any:
        """A difference below a billionth of the impacts that make it is rounding, not a difference:
        it is set to exactly zero, so that p_a_lower counts it as a tie. Two identical products
        would otherwise differ by rounding in every draw, always with the same sign, and the
        agent would certify that one is lower."""
        xp = self.model.xp
        tol = RELATIVE_TIE * xp.abs(self.contrib).sum(axis=0)
        return xp.where(xp.abs(d) <= tol, 0.0, d)


def p_a_lower(delta: Any, xp: Any = None) -> float:
    """P(I_A < I_B) along the last axis, a draw where the two impacts are equal counting one half.

    Without the half, two products with the same impact in every draw would give p = 0, and the
    agent would certify that B is lower with no risk at all. With it they give p = 1/2, which is
    the truth: nothing tells them apart. A continuous model has ties with probability zero, so
    nothing else changes."""
    return (delta < 0).mean(axis=-1) + 0.5 * (delta == 0).mean(axis=-1)


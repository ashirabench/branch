"""Bill of materials + location -> linear LCA surrogate (Step 3).

The comparative result is additive:

    delta = I_A - I_B = sum_m h_m(theta_{deps_m})

LCA is linear in the amount of each exchange, so each Term is one exchange
(amount x unit impact factor) and depends on only a few choices. Unit impact
factors come from openLCA ONCE (olca_bridge); the agent never calls openLCA
inside the Monte Carlo loop.
"""
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

import numpy as np


@dataclass
class Term:
    """One additive contribution to delta = I_A - I_B.

    fn(xp, v) receives {choice_name: array} and returns an array that
    broadcasts against its inputs. sign=-1 for terms of alternative B.
    Categorical values arrive as option indices (floats): index a factor
    table with xp.asarray(v[name]).astype(int).

    inventory(v), optional: for one world of scalars, the exchanges behind
    this term as {factor key: amount}, so that fn = sum(amount x factor).
    This is what is written back to openLCA (olca_bridge.push_comparison).
    """
    name: str
    deps: Sequence[str]
    fn: Callable
    sign: float = 1.0
    inventory: Optional[Callable] = None


class Model:
    """Choices (beliefs.Choice) + Terms, on a NumPy or CuPy backend."""

    meta: dict                     # set by builder.build_model; absent in a model written by hand
    factor_data: dict
    build_args: dict

    def __init__(self, choices: Any, terms: Sequence[Term], xp: Any = np, label_a: str = "A",
                 label_b: str = "B") -> None:
        self.choices = list(choices.list() if hasattr(choices, "list") else choices)
        self.terms = list(terms)
        self.xp = xp
        self.label_a, self.label_b = label_a, label_b
        self.idx = {c.name: j for j, c in enumerate(self.choices)}
        self.by_name = {c.name: c for c in self.choices}
        self.terms_of = {c.name: [m for m, t in enumerate(self.terms) if c.name in t.deps]
                         for c in self.choices}
        for t in self.terms:
            for d in t.deps:
                if d not in self.idx:
                    raise KeyError(f"Term {t.name} depends on unknown choice {d}")

    def sample(self, n: int, seed: int) -> Any:
        """Common random numbers: CPU draw from a SeedSequence, one transfer to
        the device, so CPU and GPU runs see identical samples. Choices already
        fixed (Choice.fixed) enter as constants."""
        rng = np.random.default_rng(np.random.SeedSequence(seed))
        u = rng.random((n, len(self.choices)))
        cols = []
        for j, c in enumerate(self.choices):
            cols.append(np.full(n, c.encode(c.fixed)) if not c.is_open() else c.ppf(u[:, j]))
        return self.xp.asarray(np.column_stack(cols), dtype=self.xp.float64)

    def term_value(self, m: int, S: Any, override: Optional[tuple] = None) -> Any:
        """Term m for every sample row of S. override=(name, V) with V of shape
        (K, 1) evaluates every candidate answer at once, giving (K, N)."""
        t = self.terms[m]
        v = {d: S[:, self.idx[d]] for d in t.deps}
        if override is not None:
            v[override[0]] = override[1]
        out = self.xp.asarray(t.sign * t.fn(self.xp, v), dtype=self.xp.float64)
        if out.ndim == 0:
            out = out + self.xp.zeros(S.shape[0])
        return out

    def inventory(self, point: dict) -> dict:
        """Exchanges per functional unit for one world {name: engine number}:
        {label_a: {factor key: amount}, label_b: {...}}. Needs Terms built
        with an inventory function (builder.py)."""
        out: dict = {self.label_a: {}, self.label_b: {}}
        for t in self.terms:
            if t.inventory is None:
                raise ValueError(f"Term {t.name} has no inventory; build the model with builder.py")
            side = out[self.label_a if t.sign > 0 else self.label_b]
            for key, amount in t.inventory({d: float(point[d]) for d in t.deps}).items():
                side[key] = side.get(key, 0.0) + float(amount)
        return out

    def delta_at(self, point: dict) -> float:
        """Exact delta for one fully specified world {name: engine number}."""
        S = self.xp.asarray([[float(point[c.name]) for c in self.choices]], dtype=self.xp.float64)
        return float(sum(self.term_value(m, S)[0] for m in range(len(self.terms))))

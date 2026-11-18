"""Modelling choices as explicit random variables (Step 3).

Every ISO 14044 / ILCD choice that the bill of materials and the location
do not fix is a Choice. A Choice holds a prior, the provision it comes from,
and whether it is value laden (then it is always asked, never delegated).

The engine (lca_model, montecarlo, query) works on numbers: a categorical
value is the index of its option, a continuous value is the value itself.
`encode` and `decode` translate between labels and numbers. Sampling for the
engine goes through `ppf` (inverse CDF of shared uniforms), so every
candidate question sees the same Monte Carlo draws (common random numbers).
"""
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats


@dataclass
class Choice:
    name: str
    kind: str                      # "categorical" or "continuous"
    prior: Any                     # categorical: {option: prob}; continuous: (dist, params), see _frozen
    source: str                    # e.g. "ILCD 2010, sec. 6.9", "Eurostat env_waspac 2024"
    value_laden: bool = False      # value laden choices stay with the human
    question: str = ""             # the question shown to the human
    fixed: Any = None              # set when the human answers
    n_answers: int = 5             # continuous: answers represented by this many quantile points
    askable: bool = True           # False: uncertainty nobody can answer (the database's own), never asked

    def __post_init__(self):
        if self.kind not in ("categorical", "continuous"):
            raise ValueError(f"{self.name}: kind must be 'categorical' or 'continuous'")

    # ------------------------------------------------------------------ state
    def is_open(self) -> bool:
        return self.fixed is None

    def fix(self, value) -> None:
        self.fixed = value

    # ------------------------------------------------------------- the prior
    @property
    def labels(self):
        return list(self.prior.keys())

    @property
    def probs(self):
        p = np.array(list(self.prior.values()), dtype=float)
        return p / p.sum()

    def _frozen(self):
        """scipy distribution for a continuous prior.

        normal {mean, sd} | beta {a, b} | uniform {low, high}
        triangular {low, mode, high} | lognormal {median, sigma}
        """
        dist, params = self.prior
        if dist == "normal":
            return stats.norm(params["mean"], params["sd"])
        if dist == "beta":
            return stats.beta(params["a"], params["b"])
        if dist == "uniform":
            return stats.uniform(params["low"], params["high"] - params["low"])
        if dist == "triangular":
            lo, hi = params["low"], params["high"]
            return stats.triang((params["mode"] - lo) / (hi - lo), loc=lo, scale=hi - lo)
        if dist == "lognormal":
            return stats.lognorm(params["sigma"], scale=params["median"])
        raise ValueError(f"unknown distribution {dist}")

    # ------------------------------------------------- labels <-> engine numbers
    def encode(self, value) -> float:
        """Answer as the engine sees it: option index or real value."""
        if self.kind == "categorical":
            return float(self.labels.index(value)) if not isinstance(value, (int, float, np.number)) else float(value)
        return float(value)

    def decode(self, x):
        if self.kind == "categorical":
            return self.labels[int(round(float(x)))]
        return float(x)

    # ------------------------------------------------------- engine sampling
    def ppf(self, u):
        """Inverse CDF of uniforms u, in engine numbers."""
        if self.kind == "categorical":
            idx = np.searchsorted(np.cumsum(self.probs), u, side="right")
            return np.clip(idx, 0, len(self.probs) - 1).astype(float)
        return self._frozen().ppf(u)

    def answers(self):
        """Possible human answers (engine numbers) and their prior weights."""
        if self.kind == "categorical":
            return np.arange(len(self.probs), dtype=float), self.probs
        q = (np.arange(self.n_answers) + 0.5) / self.n_answers
        return self._frozen().ppf(q), np.full(self.n_answers, 1.0 / self.n_answers)

    def answer_probs(self):
        """Prior probability vector used by the uncertainty sampling baselines."""
        return self.answers()[1]

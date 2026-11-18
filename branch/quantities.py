"""The small pieces every term of the model is made of.

A term is a product of quantities. A quantity is a constant or the value of a choice in a world
(Param). The helpers below read a quantity in a world, pick the option of a categorical choice, and
apply the uncertainty that the database states for a factor.
"""
from typing import Any, Optional

import numpy as np


class Param:
    """A quantity in a term: a Choice (by name) or a constant engine number."""

    def __init__(self, name: Optional[str] = None, const: Optional[float] = None) -> None:
        self.name, self.const = name, const

    def __call__(self, v: dict) -> Any:
        return v[self.name] if self.name is not None else self.const


def as_scalar(x: Any) -> Any:
    """A plain number, or the symbol itself when the inventory is being traced into formulas (formulas.py)."""
    return x if hasattr(x, "text") else float(x)


def option_index(p: Param, v: dict) -> int:
    """Option index of a categorical Param in a world of scalars."""
    return int(round(float(p(v))))


class Scaled(Param):
    """exp(sigma z): the multiplier of one factor when a single draw z moves every factor together."""

    def __init__(self, name: str, sigma: float, xp: Any) -> None:
        super().__init__(name)
        self.sigma, self.xp = sigma, xp

    def __call__(self, v):
        z = v[self.name]
        return float(np.exp(self.sigma * z)) if isinstance(z, (int, float)) else self.xp.exp(self.sigma * z)


COMMON_FACTOR_DRAW = "factor.all"
MEDIAN_TOLERANCE = 0.10


def consistent_uncertainty(unc: dict) -> bool:
    """True when the median of the Monte Carlo runs of a dataset lies within 10% of the value the
    database calculates for it. The others are the ones that the wrong signs of the database reach."""
    ratio = unc.get("median_ratio")
    return ratio is not None and abs(float(ratio) - 1.0) <= MEDIAN_TOLERANCE


def deps(*params: Optional[Param]) -> list:
    return list(dict.fromkeys(p.name for p in params if p is not None and p.name is not None))


def multiplier(p: Optional[Param], v: dict) -> Any:
    """Multiplier of a factor in a world: its uncertainty draw, or exactly 1."""
    return 1.0 if p is None else p(v)


def option_table(xp: Any, values: Any, us: list, i: Any, v: dict) -> Any:
    """values[i], each option multiplied by the uncertainty of its own factor."""
    out = values[i]
    if any(u is not None for u in us):
        mult = xp.ones_like(out)
        for j, u in enumerate(us):
            if u is not None:
                mult = xp.where(i == j, u(v), mult)
        out = out * mult
    return out

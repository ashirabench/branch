"""Benchmark cases built from unit impact factors extracted from openLCA.

The factors come from experiments/openlca/extract_factors.py (data/factors/*.json,
kept out of git: the BAFU terms of use do not allow redistributing the
data). Every result must cite: "Life Cycle Inventory database of the Swiss
Federal Administration, BAFU:2026".

Two kinds of numbers live here, and they must never be confused:
  * unit impact factors: REAL, read from the JSON file (per kg, kWh, tkm, MJ);
  * priors on the modelling choices: marked SOURCE when they come from a
    cited source and ASSUMPTION when they are placeholders I chose. Every
    ASSUMPTION is listed by assumptions(model), and every report lists it.
"""

import numpy as np

from .builder import build_model
from .factors import factor, load_factors  # noqa: F401  (re-exported)

DEFAULT_CATEGORY = "Climate change"
CITATION = "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026"


def assumptions(model):
    """Choices whose prior is still a placeholder chosen by me."""
    return [c.name for c in model.choices if c.source.startswith("ASSUMPTION")]


def compare(spec_a, spec_b, region="PT", category=DEFAULT_CATEGORY, factors=None, xp=np, country=None, **kw):
    """Any two products described by a bill of materials (see builder.py), in a
    region from data/regions/ (country= is accepted as an alias)."""
    model = build_model(spec_a, spec_b, country or region, category, factors or load_factors(), xp=xp, **kw)
    model.meta["citation"] = model.meta.get("citation") or CITATION
    return model


def pet_vs_refillable_glass(region="PT", category=DEFAULT_CATEGORY, factors=None, xp=np):
    """1 L of beverage delivered: single use PET bottle (A) vs refillable glass bottle (B).

    Built from data/benchmark/pet_bottle_1l.json and glass_refillable_1l.json.
    Cut-off approach for recycling (ILCD Situation A, attributional).
    """
    return compare("pet_bottle_1l", "glass_refillable_1l", region, category, factors, xp)

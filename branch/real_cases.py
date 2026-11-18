"""Benchmark cases built from unit impact factors extracted from openLCA.

The factors come from experiments/openlca/extract_factors.py (data/factors/*.json,
kept out of git: the BAFU terms of use do not allow redistributing the
data). Every result must cite: "Life Cycle Inventory database of the Swiss
Federal Administration, BAFU:2026".

Two kinds of numbers live here, and they must never be confused:
  * unit impact factors: REAL, read from the JSON file (per kg, kWh, tkm, MJ);
  * priors on the modelling choices: marked SOURCE when they come from a
    cited source and ASSUMPTION when they are placeholders I chose. Every
    ASSUMPTION is listed by assumptions(model) and must be replaced by a
    sourced prior (Eurostat, sector reports, published LCAs) before results
    are reported.
"""
import glob
import json
import os
import re

import numpy as np

from .builder import build_model, factor  # noqa: F401  (factor re-exported)
from .paths import data_path

DEFAULT_CATEGORY = "Climate change"
CITATION = "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026"


def load_factors(path=None, root=None):
    """The file in BRANCH_FACTORS if that is set, else the newest data/factors/*.json, unless a
    path is given. BRANCH_FACTORS lets every command run on another factor file, such as the
    hybrid of the second database test (experiments/data/make_hybrid_factors.py)."""
    if path is None and root is None:
        path = os.environ.get("BRANCH_FACTORS") or None
    if path is None:
        if root:
            roots = [root]
        else:                       # the repository's data/factors, then the connector's user folder
            from .connector import factors_dir
            roots = [data_path("factors"), factors_dir()]
        files = sorted((f for r in roots for f in glob.glob(os.path.join(r, "*.json"))), key=os.path.getmtime)
        if not files:
            raise FileNotFoundError(
                "No extracted factors found. Run experiments/openlca/extract_factors.py with openLCA open first.")
        path = files[-1]
    with open(path) as fh:
        data = json.load(fh)
    data["path"] = path
    year = re.search(r"(20\d\d)", str(data.get("database", ""))) or re.search(r"(20\d\d)", os.path.basename(path))
    if "20XY" in str(data.get("citation", "")):              # files made before the year was filled in
        data["citation"] = data["citation"].replace("20XY", year.group(1) if year else "2026")
    return data


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

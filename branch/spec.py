"""The product file: what a description of a product may say, read and checked (Step 3).

Proposal v2, Goal 1: the agent "accepts as input only a bill of materials
(material type and mass per component), the location of production and use,
and optionally a second alternative to compare". This module turns two such
descriptions into the Choices and Terms the engine already understands, so a
new comparison needs a product file, not new code.

A product description (dict, or a JSON file):

    {
      "id": "pet",                        short slug, prefixes its choice names
      "name": "PET single use",           shown in questions and the report
      "volume_l": 1.0,                    content of one container
      "refillable": false,                adds trips, washing and the return leg
      "components": [
        {"id": "bottle", "material": "pet",
         "mass_g": 32}                    or "mass_prior": [dist, params, source]
      ]
    }

Anything the description states is fixed (the deterministic part of the
belief base). Anything it leaves out is completed from the codified rules in
catalogue.py and becomes an explicit Choice. Optional per component:
"conversion" (factor key or null) overrides the material's default process;
"recycled_content_prior" [dist, params, source] replaces the material's prior
of recycled content for that component. A region may override a mass prior
with the key "<product>.<component>.mass_g".
Optional per material, written under "materials": {"pet": {...}}:
"dataset" (option label), "recycled_content", "recycling_rate",
"incineration_share", "end_of_life" (option label); each fixes that choice.
With the Circular Footprint Formula also "recycling_ratio".

Choice names: "<product>.<component>.mass_g" for masses,
"<product>.<material>.<field>" for material choices (dataset,
recycled_content, recycled_ratio, recycling_rate, incineration_share,
end_of_life), "<product>.<field>" for refillable choices, and the bare name
for choices shared by both alternatives (distribution_km).

Comparison: delta = I_A - I_B per functional unit, cut-off system model.

builder.py turns two such descriptions into a model; product_terms.py writes the terms.
"""
import json
import os
import re

from . import catalogue as cat
from .beliefs import Choice
from .paths import data_path
from .regions import load_region

BENCHMARK_DIR = data_path("benchmark")

STAGES = ("material", "manufacturing", "transport", "use", "end_of_life", "other")


# What a value can be in the world, whatever the prior says: a share lies between 0 and 1, a
# container is used at least once, and every other quantity (mass, distance, energy, water) is not
# negative. A stated value outside these is an error of typing; a value outside the prior only is not.
SHARES = ("recycled_content", "recycling_rate", "incineration_share", "recycled_ratio", "recycling_ratio")


def physical_range(name):
    """(lowest, highest) a choice can take in the world, from the last part of its name."""
    field = str(name).rsplit(".", 1)[-1]
    if field in SHARES:
        return 0.0, 1.0
    if field == "trips":
        return 1.0, float("inf")
    return 0.0, float("inf")


def _check_value(where, name, value):
    lo, hi = physical_range(name)
    if not lo <= float(value) <= hi:
        bound = f"at least {lo:g}" if hi == float("inf") else f"between {lo:g} and {hi:g}"
        raise ValueError(f"{where}: {name.rsplit('.', 1)[-1]} = {value} is impossible; it must be {bound}")


def _check_mass_prior(where, prior):
    """A mass prior must be a distribution BRANCH knows, with sensible parameters, and never negative."""
    dist, params = prior[0], prior[1]
    if dist == "triangular" and not params["low"] <= params["mode"] <= params["high"]:
        raise ValueError(f"{where}: a triangular prior needs low <= mode <= high")
    frozen = Choice(where, "continuous", (dist, params), "check")._frozen()
    if not frozen.ppf(1e-9) >= 0:
        raise ValueError(f"{where}: this mass prior gives negative masses; use triangular, uniform or lognormal")


def _check_component(spec, c):
    where = f"{spec['id']}.{c['id']}"
    if "mass_g" in c and not float(c["mass_g"]) > 0:
        raise ValueError(f"{where}: mass_g must be more than 0")
    if "mass_g" not in c:
        _check_mass_prior(where, c["mass_prior"])


def _check_stated(spec):
    """Every value the product file states for a material or for reuse is possible in the world."""
    for mid, known in spec["materials"].items():
        for field, value in known.items():
            if field in SHARES:
                _check_value(f"{spec['id']}.{mid}", field, value)
    for field, value in (spec.get("reuse") or {}).items():
        _check_value(f"{spec['id']}.reuse", field, value)


def process_key(name, location=None):
    """Factor key of any process of the database, chosen by its exact name:
    "proc:<name>" or "proc:<name> @<location code>" when several locations share the name."""
    name = re.sub(r"\s+", " ", str(name).strip())
    if not name:
        raise ValueError("the openLCA process needs a name")
    return f"proc:{name}" + (f" @{str(location).strip()}" if location and str(location).strip() else "")


def parse_process_key(key):
    """(name, location or None) of a "proc:" key, else None."""
    if not str(key).startswith("proc:"):
        return None
    name, _, loc = key[5:].partition(" @")
    return name, (loc or None)


def _check_exchanges(spec):
    """Inputs chosen from the database by process name (any product, not only containers).

    {"id", "process" (exact openLCA name), "location" (optional code), "stage" (one of STAGES),
     "amount": number, or [low, high] when the person only knows a range, "source": optional}
    The amount is per product, in the unit of the reference flow of the process."""
    seen = {c["id"] for c in spec.get("components") or []}
    for i, e in enumerate(spec.get("exchanges") or []):
        e.setdefault("label", str(e.get("id") or f"input {i + 1}"))
        e["id"] = re.sub(r"[^a-z0-9]+", "_", str(e.get("id") or f"input_{i + 1}").lower()).strip("_") or f"input_{i + 1}"
        where = f"{spec['id']}.{e['id']}"
        if e["id"] in seen:
            raise ValueError(f"{spec['id']}: duplicate id {e['id']!r}")
        seen.add(e["id"])
        if not e.get("key"):
            if not e.get("process"):
                raise ValueError(f"{where}: give the openLCA process name")
            e["key"] = process_key(e["process"], e.get("location"))
        e.setdefault("stage", "other")
        if e["stage"] not in STAGES:
            raise ValueError(f"{where}: stage must be one of {', '.join(STAGES)}")
        amount = e.get("amount")
        if isinstance(amount, (list, tuple)):
            if len(amount) != 2 or not float(amount[0]) < float(amount[1]):
                raise ValueError(f"{where}: a range needs a smallest and a larger largest amount")
            if float(amount[0]) < 0:
                raise ValueError(f"{where}: amounts cannot be negative")
            e["amount"] = [float(amount[0]), float(amount[1])]
        else:
            try:
                e["amount"] = float(amount)
            except (TypeError, ValueError):
                raise ValueError(f"{where}: give an amount, or a smallest and a largest amount") from None
            if e["amount"] < 0:
                raise ValueError(f"{where}: amounts cannot be negative")


def load_spec(spec):
    """Product description from a dict, a JSON path, or a benchmark name
    ("pet_bottle_1l" -> data/benchmark/pet_bottle_1l.json). Validated."""
    if isinstance(spec, str):
        path = spec if os.path.exists(spec) else os.path.join(BENCHMARK_DIR, f"{spec}.json")
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
    spec = dict(spec)
    spec.setdefault("id", re.sub(r"[^a-z0-9]+", "_", spec.get("name", "product").lower()).strip("_"))
    spec.setdefault("name", spec["id"])
    spec.setdefault("volume_l", 1.0)
    spec.setdefault("refillable", False)
    spec.setdefault("materials", {})
    comps = spec.get("components") or []
    spec["components"] = comps
    if not comps and not spec.get("exchanges"):
        raise ValueError(f"{spec['id']}: the bill of materials has no components")
    units = spec.setdefault("units_per_functional_unit", 1.0)
    if not float(units) > 0:
        raise ValueError(f"{spec['id']}: units_per_functional_unit must be positive")
    seen = set()
    for i, c in enumerate(comps):
        c.setdefault("id", f"c{i}")
        if c["id"] in seen:
            raise ValueError(f"{spec['id']}: duplicate component id {c['id']!r}")
        seen.add(c["id"])
        materials = cat.load_materials()
        if c.get("material") not in materials:
            raise ValueError(f"{spec['id']}.{c['id']}: unknown material {c.get('material')!r}; "
                             f"known: {sorted(materials)}")
        if "mass_g" not in c and "mass_prior" not in c:
            raise ValueError(f"{spec['id']}.{c['id']}: give mass_g or mass_prior")
        _check_component(spec, c)
    if spec["volume_l"] <= 0:
        raise ValueError(f"{spec['id']}: volume_l must be positive")
    _check_stated(spec)
    _check_exchanges(spec)
    return spec


def required_factor_keys(specs, region):
    """Every factor key the comparison of these products in this region needs."""
    region = load_region(region)
    materials = cat.load_materials()
    specs = [load_spec(s) for s in specs]
    keys = set()
    if any(spec["components"] for spec in specs):   # the rules for containers: washing, legs by mass
        keys |= set(cat.UTILITIES.values())
        elec = region.electricity
        keys |= {elec} if isinstance(elec, str) else {k for k, _ in elec["options"].values()}
        keys |= {cat.TRANSPORT[leg["mode"]] for leg in region.distribution + region.supply}
    for spec in specs:
        keys |= {e["key"] for e in spec.get("exchanges") or []}
        for c in spec["components"]:
            m = materials[c["material"]]
            keys |= {k for k, _ in m["datasets"].values()}
            conv = c.get("conversion", m["conversion"])
            if conv:
                keys.add(conv)
            rec = m["recycled"]
            if rec and rec["model"] == "dataset":
                keys.add(rec["key"])
            eol = m["end_of_life"]
            if eol["model"] == "split":
                keys |= {eol["incineration"], eol["landfill"]}
            else:
                keys |= {k for k, _ in eol["options"].values() if k}
    return sorted(keys)


# ------------------------------------------------------------- parameters

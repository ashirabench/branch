"""Regions: what the location fixes, and what it changes in the priors (Step 4).

Proposal v2, section 4.1: continuous choices "receive priors centered on the
location's statistics". A region is a JSON file in data/regions/ with a
parent, so a new place only states what differs from the place above it:

    GLO  (defaults: one lorry leg filler to shops)
     ├── PT, DE
     ├── EU   (European Union, a group)
     │    └── AT, BE, ... SK, IS, NO   (written by experiments/data/make_eu_regions.py from Eurostat)
     └── BR
          └── BR-N   (Northern Brazil)
               └── BR-AM   (Amazonas: Manaus, river supply, isolated grids)

Fields (all optional except code and name; a child overrides its parent):

    "electricity"   factor key of the electricity mix, or
                    {"options": {label: [key, weight]}, "source": ..., "question": ...}
                    which becomes a categorical Choice (grid vs isolated system)
    "distribution"  legs filler -> shops, [{"mode": "lorry", "km": [dist, params, source]}];
                    refillables travel each leg twice (empty return)
    "supply"        legs packaging producer -> filler, per container produced
    "priors"        overrides of catalogue priors by key, e.g.
                    "pet.recycling_rate": ["beta", {"a": 2, "b": 8}, "SOURCE: ..."]
                    "refillable.trips": [...]
                    and for a categorical choice (the fate of a glass bottle)
                    "glass.end_of_life": {"weights": {label: w, ...}, "source": "SOURCE: ..."}
                    Keys: <material>.recycling_rate, .incineration_share, .recycled_content,
                    .recycled_ratio, .end_of_life; refillable.trips.
    "sources_needed" what still has to be sourced for this region (shown in reports)
    "group"         true for a set of countries (EU): its members inherit from it, but it does not
                    appear in their name ("France", not "European Union > France")

Transport modes map to factor keys in catalogue.TRANSPORT.
"""
import json
import os
import re

from .paths import data_path

# BRANCH_REGIONS points at another folder of region files (same file names as data/regions).
REGION_DIR = os.environ.get("BRANCH_REGIONS") or data_path("regions")


class Region:
    def __init__(self, chain):
        self.chain = chain                     # [self, parent, ..., root] raw dicts
        self.code = chain[0]["code"]
        self.name = chain[0]["name"]

    def get(self, field, default=None):
        for r in self.chain:
            if field in r:
                return r[field]
        return default

    def prior(self, key, default):
        """Regional prior for a catalogue key, else the catalogue default."""
        for r in self.chain:
            if key in r.get("priors", {}):
                return r["priors"][key]
        return default

    @property
    def electricity(self):
        return self.get("electricity")

    @property
    def distribution(self):
        return self.get("distribution", [])

    @property
    def supply(self):
        return self.get("supply", [])

    @property
    def path(self):
        return " > ".join(r["name"] for r in reversed(self.chain) if r["code"] != "GLO"
                          and not (r.get("group") and r is not self.chain[0]))

    def sources_needed(self):
        out = []
        for r in self.chain:
            out += r.get("sources_needed", [])
        return out


def _raw(code, root):
    path = os.path.join(root, f"{code}.json")
    if not os.path.exists(path):
        if code != "GLO" and re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(-[A-Za-z0-9]+)*", code or ""):
            # Any country (or grid) in the database without a region file of its own: its own
            # electricity mix from openLCA, everything else from the global defaults.
            return {"code": code, "name": code, "parent": "GLO", "electricity": f"electricity_mv_{code}",
                    "sources_needed": [f"national packaging waste statistics for {code}"]}
        raise ValueError(f"unknown region {code!r}; known: {list_regions(root)}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("code") != code:
        raise ValueError(f"{path}: code must be {code!r}")
    return data


def load_region(code, root=None):
    """Region by code, with its chain of parents resolved."""
    if isinstance(code, Region):
        return code
    root = root or REGION_DIR
    chain, seen = [], set()
    while code:
        if code in seen:
            raise ValueError(f"region cycle at {code!r}")
        seen.add(code)
        r = _raw(code, root)
        chain.append(r)
        code = r.get("parent")
    region = Region(chain)
    if region.electricity is None:
        raise ValueError(f"region {region.code!r} has no electricity mix in its chain")
    return region


def list_regions(root=None):
    root = root or REGION_DIR
    return sorted(f[:-5] for f in os.listdir(root) if f.endswith(".json"))

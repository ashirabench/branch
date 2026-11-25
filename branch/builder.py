"""Two product files + a location -> the comparative model (Step 3).

Proposal v2, Goal 1: the agent "accepts as input only a bill of materials (material type and mass per
component), the location of production and use, and optionally a second alternative to compare".
build_model() is that step. It reads the two product files (spec.py), completes what they leave out
from the rules of catalogue.py and the region file, each completion an explicit Choice with its
source, and asks product_terms.py for the terms of each product.

Choice names: "<product>.<component>.mass_g" for masses, "<product>.<material>.<field>" for material
choices (dataset, recycled_content, recycled_ratio, recycling_rate, incineration_share, end_of_life),
"<product>.<field>" for refillable choices, and the bare name for choices shared by both
alternatives (distribution_km).

Comparison: delta = I_A - I_B per functional unit.
"""
import os

import numpy as np

from . import catalogue as cat
from .beliefs import Choice
from .factors import factor, load_factors  # noqa: F401  (factor re-exported)
from .lca_model import Model
from .product_terms import product_terms
from .quantities import COMMON_FACTOR_DRAW, MEDIAN_TOLERANCE, Param, Scaled, consistent_uncertainty  # noqa: F401  (re-exported)
from .regions import load_region
from .spec import (  # noqa: F401  (re-exported)
    BENCHMARK_DIR,
    STAGES,
    load_spec,
    parse_process_key,
    process_key,
    required_factor_keys,
)


class _Builder:
    """The choices and factors of one comparison, shared by its two products. Asking twice for the
    same choice returns the same one, so a choice both products share is asked once."""

    def __init__(self, region, category, data, xp, shared=None, system_model="cut-off",
                 inventory_uncertainty=False, cff_heat="gas", cff_overrides=None):
        self.region, self.category, self.data, self.xp = region, category, data, xp
        self.system_model = system_model
        self.inventory_uncertainty = inventory_uncertainty
        self.cff_heat = cff_heat
        self.materials = cat.load_materials()
        self.cff = cat.load_cff() if system_model == "cff" else {}
        for mid, changes in (cff_overrides or {}).items():
            if mid in self.cff:
                self.cff[mid] = {**self.cff[mid], **changes}
        self.energy = cat.load_energy_recovery() if system_model == "cff" else {}
        self.shared = shared or {}
        self.choices = {}
        self._legs, self._elec = {}, None

    def f(self, key):
        return factor(self.data, key, self.category)

    def u(self, key):
        """Uncertainty of a unit factor as stated by the database: a multiplier with median 1, or
        None when the factor file carries none for this factor and category (or it is switched off).

        It is a Choice that nobody can answer (askable=False): it stays in every Monte Carlo draw,
        the same draw for both products when they share the dataset, and the agent never asks it."""
        if not self.inventory_uncertainty or key is None:
            return None
        unc = ((self.data.get("factors", {}).get(key) or {}).get("uncertainty") or {}).get(self.category)
        if not unc or not unc.get("gsd") or float(unc["gsd"]) <= 1.0:
            return None
        if self.inventory_uncertainty == "consistent" and not consistent_uncertainty(unc):
            return None
        if self.inventory_uncertainty == "correlated":
            # the bound opposite to independence: one standard normal draw moves every factor at once,
            # each by its own geometric standard deviation
            if COMMON_FACTOR_DRAW not in self.choices:
                self.choices[COMMON_FACTOR_DRAW] = Choice(
                    COMMON_FACTOR_DRAW, "continuous", ("normal", {"mean": 0.0, "sd": 1.0}),
                    "SOURCE: uncertainty that the database states for the exchanges of its datasets, propagated by "
                    "Monte Carlo runs in openLCA; ASSUMPTION of this sensitivity run: all factors move together",
                    question="", askable=False)
            return Scaled(COMMON_FACTOR_DRAW, float(np.log(float(unc["gsd"]))), self.xp)
        name = f"factor.{key}"
        if name not in self.choices:
            gsd = float(unc["gsd"])
            self.choices[name] = Choice(
                name, "continuous", ("lognormal", {"median": 1.0, "sigma": float(np.log(gsd))}),
                f"SOURCE: uncertainty that the database states for the exchanges of this dataset, propagated by "
                f"{int(unc.get('n', 0))} Monte Carlo runs in openLCA: geometric standard deviation {gsd:.3g} "
                f"for {self.category}", question="", askable=False)
        return Param(name)

    def continuous(self, name, entry, question, fixed=None, prior_key=None):
        """prior_key: catalogue key a region may override, e.g. "pet.recycling_rate"."""
        if fixed is not None:
            return Param(const=float(fixed))
        if name not in self.choices:
            if prior_key:
                entry = self.region.prior(prior_key, entry)
            dist, params, source = entry[:3]
            self.choices[name] = Choice(name, "continuous", (dist, params), source, question=question)
        return Param(name)

    def electricity(self):
        """(Param of the option index, factor table, keys) for the region's mix."""
        if self._elec is None:
            e = self.region.electricity
            if isinstance(e, str):
                p, keys = Param(const=0.0), [e]
            else:
                p, keys = self.categorical("electricity", e["options"], e["source"], e["question"],
                                           self.shared.get("electricity"))
            self._elec = (p, self.xp.asarray([self.f(k) for k in keys], dtype=self.xp.float64), keys,
                          [self.u(k) for k in keys])
        return self._elec

    def legs(self, kind):
        """[(km Param, factor, key)] for "distribution" or "supply", shared by both products."""
        if kind not in self._legs:
            legs = self.region.distribution if kind == "distribution" else self.region.supply
            out = []
            for leg in legs:
                mode = leg["mode"]
                name = "distribution_km" if kind == "distribution" and len(legs) == 1 else f"{kind}.{mode}_km"
                q = cat.TRANSPORT_QUESTIONS[kind].format(mode=cat.MODE_WORDS.get(mode, mode))
                km = self.continuous(name, leg["km"], q, self.shared.get(name))
                out.append((km, self.f(cat.TRANSPORT[mode]), cat.TRANSPORT[mode], self.u(cat.TRANSPORT[mode])))
            self._legs[kind] = out
        return self._legs[kind]

    def categorical(self, name, options, source, question, fixed=None, prior_key=None):
        """options {label: (value, weight)} -> (Param of the option index, value table).

        prior_key: catalogue key a region may override with {"weights": {label: w}, "source": ...},
        e.g. "glass.end_of_life" from the national recycling statistics.
        """
        labels = list(options)
        values = [v for v, _ in options.values()]
        if fixed is not None:
            if fixed not in labels:
                raise ValueError(f"{name}: {fixed!r} is not one of {labels}")
            return Param(const=float(labels.index(fixed))), values
        if len(labels) == 1:
            return Param(const=0.0), values
        if name not in self.choices:
            weights = {k: w for k, (_, w) in options.items()}
            override = self.region.prior(prior_key, None) if prior_key else None
            if override:
                unknown = set(override["weights"]) - set(labels)
                if unknown:
                    raise ValueError(f"{self.region.code} {prior_key}: unknown options {sorted(unknown)}; "
                                     f"the catalogue has {labels}")
                weights = {k: float(override["weights"].get(k, 0.0)) for k in labels}
                source = override["source"]
            self.choices[name] = Choice(name, "categorical", weights, source, question=question)
        return Param(name), values


# ----------------------------------------------------------------- model

def build_model(spec_a, spec_b, region="PT", category="Climate change", factors=None,
                functional_unit_l=1.0, xp=np, shared=None, country=None, system_model="cut-off",
                inventory_uncertainty=False, cff_heat="gas", cff_overrides=None):
    """Comparative Model: delta = I_A - I_B per functional unit (litres delivered).

    region   region code from data/regions/ ("PT", "DE", "BR", "BR-N", "BR-AM", ...);
             country= is accepted as an alias.
    factors  dict from extract_factors.py (real_cases.load_factors()); loaded
             from data/factors/ when None.
    shared   values the user already knows for shared choices, e.g.
             {"distribution_km": 120} or {"electricity": "national grid (SIN)"}.
    inventory_uncertainty  True: when the factor file carries the uncertainty of its datasets
             (written by experiments/openlca/extract_uncertainty.py), every factor varies in the Monte Carlo
             draws as a choice that nobody is asked. Off by default: the app and the main results of
             the paper do not use it; its third ablation does (experiments/record/PLAN_2026-11-15.md, A3).
             "correlated": a sensitivity run in which one draw moves every factor together, the bound
             opposite to treating the factors as independent.
    cff_heat  heat that the steam of a waste-to-energy plant replaces in the Circular Footprint Formula:
             "gas" (default, heat from natural gas), "district" (Swiss district heat average) or "none".
    cff_overrides  {material: {parameter: value}} over data/cff/, for sensitivity runs only.
    system_model  "cut-off" (ISO default, ILCD Situation A) or "cff", the EU PEF
             Circular Footprint Formula with the parameters of Part C of Annex II in data/cff/
             and the credit for recovered energy (B = 0).
    """
    _check_options(system_model, cff_heat, inventory_uncertainty)
    region = load_region(country or region)
    if factors is None:
        factors = load_factors()
    _name_region_after_its_grid(region, factors)
    a, b_ = load_spec(spec_a), load_spec(spec_b)
    if a["id"] == b_["id"]:
        raise ValueError("the two alternatives need different ids")
    b = _Builder(region, category, factors, xp, shared, system_model, inventory_uncertainty, cff_heat, cff_overrides)
    _check_cff_parameters(b, a, b_)
    packaged = bool(a["components"] or b_["components"])
    if packaged:
        b.legs("distribution")        # shared choices first, as in the hand written model
    terms = (product_terms(b, a, +1.0, functional_unit_l / a["volume_l"])
             + product_terms(b, b_, -1.0, functional_unit_l / b_["volume_l"]))
    model = Model(list(b.choices.values()), terms, xp, label_a=a["name"], label_b=b_["name"])
    model.factor_data = factors
    model.build_args = {"spec_a": a, "spec_b": b_, "region": region.code,
                        "functional_unit_l": functional_unit_l, "shared": shared,
                        "system_model": system_model, "inventory_uncertainty": inventory_uncertainty,
                        "cff_heat": cff_heat, "cff_overrides": cff_overrides}
    model.meta = _meta(region, category, system_model, factors, a, b_, functional_unit_l, packaged)
    return model


SYSTEM_MODELS = ("cut-off", "cff")
UNCERTAINTY_OPTIONS = (False, True, "correlated", "consistent")


def _check_options(system_model, cff_heat, inventory_uncertainty):
    if system_model not in SYSTEM_MODELS:
        raise ValueError("system_model must be 'cut-off' or 'cff'")
    if cff_heat not in cat.CFF_HEAT_OPTIONS:
        raise ValueError(f"cff_heat must be one of {sorted(cat.CFF_HEAT_OPTIONS)}")
    if inventory_uncertainty not in UNCERTAINTY_OPTIONS:
        raise ValueError("inventory_uncertainty must be False, True, 'correlated' or 'consistent'")


def _name_region_after_its_grid(region, factors):
    """A country without a region file takes the name the database gives to its electricity grid."""
    grid = (factors.get("factors") or {}).get(f"electricity_mv_{region.code}") or {}
    if region.name == region.code and grid.get("location"):
        region.name = region.chain[0]["name"] = grid["location"]


def _check_cff_parameters(b, a, b_):
    if b.system_model != "cff":
        return
    missing = sorted({c["material"] for spec in (a, b_) for c in spec["components"]} - set(b.cff))
    if missing:
        raise ValueError("The Circular Footprint Formula needs the parameters of Part C of Annex II "
                         "(former PEF Annex C) in data/cff/ for: "
                         + ", ".join(missing))


def _meta(region, category, system_model, factors, a, b_, functional_unit_l, packaged):
    """What the reports say about the comparison besides its numbers."""
    return {"country": region.code, "region": region.name, "region_path": region.path,
            "sources_needed": region.sources_needed() if packaged else [],
            "category": category,
            "system_model": system_model, "method": factors.get("method"),
            "factors_file": os.path.basename(factors.get("path", "")),
            "citation": factors.get("citation"),
            "functional_unit": _functional_unit(a, b_, functional_unit_l),
            "products": [a, b_]}


def _functional_unit(a, b_, functional_unit_l):
    """The service both alternatives deliver. Containers: litres delivered. Other products:
    the text given in the product files ("functional_unit"), which must be the same for both."""
    given = {s["functional_unit"].strip() for s in (a, b_) if s.get("functional_unit")}
    if len(given) > 1:
        raise ValueError("the two products must deliver the same service: give them the same functional_unit")
    if given:
        return given.pop()
    if a["components"] or b_["components"]:
        return f"{functional_unit_l:g} L of beverage delivered to the retailer"
    return "the same use of one product"


def rebuild(model, category):
    """The same comparison (same products, region and choices) for another impact category."""
    args = model.build_args
    return build_model(args["spec_a"], args["spec_b"], args["region"], category, model.factor_data,
                       args["functional_unit_l"], model.xp, args["shared"],
                       system_model=args.get("system_model", "cut-off"),
                       inventory_uncertainty=args.get("inventory_uncertainty", False),
                       cff_heat=args.get("cff_heat", "gas"), cff_overrides=args.get("cff_overrides"))

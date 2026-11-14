"""Bill of materials + location -> comparative Model, for any two products (Step 3).

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

Choice names: "<product>.<component>.mass_g" for masses,
"<product>.<material>.<field>" for material choices (dataset,
recycled_content, recycled_ratio, recycling_rate, incineration_share,
end_of_life), "<product>.<field>" for refillable choices, and the bare name
for choices shared by both alternatives (distribution_km).

Comparison: delta = I_A - I_B per functional unit, cut-off system model.
"""
import json
import os
import re

import numpy as np

from . import catalogue as cat
from .beliefs import Choice
from .lca_model import Model, Term
from .regions import load_region

BENCHMARK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "benchmark")


# ---------------------------------------------------------------- inputs

STAGES = ("material", "manufacturing", "transport", "use", "end_of_life", "other")


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
                raise ValueError(f"{where}: give an amount, or a smallest and a largest amount")
            if e["amount"] < 0:
                raise ValueError(f"{where}: amounts cannot be negative")


def load_spec(spec):
    """Product description from a dict, a JSON path, or a benchmark name
    ("pet_bottle_1l" -> data/benchmark/pet_bottle_1l.json). Validated."""
    if isinstance(spec, str):
        path = spec if os.path.exists(spec) else os.path.join(BENCHMARK_DIR, f"{spec}.json")
        with open(path) as fh:
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
    if spec["volume_l"] <= 0:
        raise ValueError(f"{spec['id']}: volume_l must be positive")
    _check_exchanges(spec)
    return spec


def factor(data, key, category):
    """Unit impact factor from an extract_factors.py file."""
    try:
        return float(data["factors"][key]["impacts"][category])
    except KeyError as exc:
        raise KeyError(f"Factor {key!r} / category {category!r} missing in "
                       f"{data.get('path', 'factors')}. Run experiments/extract_factors.py "
                       f'--update --only "{key}"') from exc


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

class Param:
    """A quantity in a term: a Choice (by name) or a constant engine number."""

    def __init__(self, name=None, const=None):
        self.name, self.const = name, const

    def __call__(self, v):
        return v[self.name] if self.name is not None else self.const


class _Builder:
    def __init__(self, region, category, data, xp, shared=None, system_model="cut-off"):
        self.region, self.category, self.data, self.xp = region, category, data, xp
        self.system_model = system_model
        self.materials = cat.load_materials()
        self.cff = cat.load_cff() if system_model == "cff" else {}
        self.shared = shared or {}
        self.choices = {}
        self._legs, self._elec = {}, None

    def f(self, key):
        return factor(self.data, key, self.category)

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
            self._elec = (p, self.xp.asarray([self.f(k) for k in keys], dtype=self.xp.float64), keys)
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
                out.append((km, self.f(cat.TRANSPORT[mode]), cat.TRANSPORT[mode]))
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


def _i(p, v):
    """Option index of a categorical Param in a world of scalars."""
    return int(round(float(p(v))))


def _deps(*params):
    return [p.name for p in params if p is not None and p.name is not None]


def _product_terms(b, spec, sign, n_units):
    """Terms of one alternative, already multiplied by containers per functional unit."""
    xp = b.xp
    pid, pname = spec["id"], spec["name"]
    idx = lambda p, v: xp.asarray(p(v)).astype(int)  # noqa: E731
    terms = []

    if spec["refillable"]:
        r = cat.REFILLABLE
        given = spec.get("reuse", {})
        trips = b.continuous(f"{pid}.trips", r["trips"], r["trips"][3].format(p=f'"{pname}" container'), given.get("trips"),
                             "refillable.trips")
        legs = cat.REFILLABLE_TRANSPORT_LEGS
    else:
        trips, legs = Param(const=1.0), 1

    n_units = n_units * float(spec.get("units_per_functional_unit", 1.0))

    # inputs chosen from the database by process name: amount x unit factor, any life cycle stage
    for e in spec.get("exchanges") or []:
        key, what = e["key"], e.get("label") or e["id"].replace("_", " ")
        unit = (b.data.get("factors", {}).get(key) or {}).get("unit") or "unit of the process"
        proc_name = (parse_process_key(key) or (key, None))[0]
        if isinstance(e["amount"], list):
            lo, hi = e["amount"]
            source = e.get("source") or (f"ASSUMPTION: range given by the user for {what}, "
                                         f"{lo:g} to {hi:g} {unit}; every value in it equally likely")
            if not source.startswith(("SOURCE:", "ASSUMPTION:")):
                source = "ASSUMPTION: " + source
            amount = b.continuous(f"{pid}.{e['id']}.amount", ("uniform", {"low": lo, "high": hi}, source),
                                  f'How much "{proc_name}" does one "{pname}" need for {what} ({unit})?')
        else:
            amount = Param(const=float(e["amount"]))
        fac = b.f(key)

        def exchange(xp_, v, amount=amount, fac=fac):
            return n_units * amount(v) * fac

        def exchange_inv(v, amount=amount, key=key):
            return {key: n_units * amount(v)}

        terms.append(Term(f"{pid}.{e['id']}.{e['stage']}", _deps(amount), exchange, sign, exchange_inv))

    total_mass = []
    for c in spec["components"]:
        mid = c["material"]
        m = b.materials[mid]
        label = m["label"]
        where = f'{label} in "{pname}"'
        known = spec["materials"].get(mid, {})

        if "mass_g" in c:
            mass = Param(const=float(c["mass_g"]))
        else:
            dist, params, source = c["mass_prior"][:3]
            mass = b.continuous(f"{pid}.{c['id']}.mass_g", (dist, params, source),
                                f'How many grams does the {c["id"].replace("_", " ")} of "{pname}" weigh?',
                                None, f"{pid}.{c['id']}.mass_g")
        total_mass.append(mass)

        # virgin dataset
        ds, ds_keys = b.categorical(f"{pid}.{mid}.dataset", m["datasets"],
                                    m.get("datasets_source", "SOURCE: catalogue datasets"),
                                    m.get("dataset_question", "Which {c} dataset applies?").format(c=where),
                                    known.get("dataset"))
        virgin = xp.asarray([b.f(k) for k in ds_keys], dtype=xp.float64)
        conv_key = c.get("conversion", m["conversion"])
        conv = b.f(conv_key) if conv_key else 0.0

        # recycled content
        rec = m["recycled"]
        if rec is None:
            r_share, ratio, rec_f = Param(const=0.0), None, 0.0
        else:
            # a component may carry its own prior (aluminium foil is not can sheet)
            own = c.get("recycled_content_prior")
            r_share = b.continuous(f"{pid}.{mid}.recycled_content", tuple(own) if own else rec["content"],
                                   f"What share of the {where} is recycled material (0 to 1)?",
                                   known.get("recycled_content"), None if own else f"{mid}.recycled_content")
            if rec["model"] == "burden_ratio":
                ratio = b.continuous(f"{pid}.{mid}.recycled_ratio", rec["ratio"],
                                     f"Impact of recycled {label} relative to virgin {label} (0 to 1)?",
                                     known.get("recycled_ratio"), f"{mid}.recycled_ratio")
                rec_f = None
            else:
                ratio, rec_f = None, b.f(rec["key"])

        def material(xp_, v, mass=mass, ds=ds, virgin=virgin, conv=conv, r=r_share,
                     ratio=ratio, rec_f=rec_f, trips=trips):
            kg = mass(v) / 1000
            vf = virgin[idx(ds, v)]
            recycled = ratio(v) * vf if ratio is not None else rec_f
            return n_units * kg * ((1 - r(v)) * vf + r(v) * recycled + conv) / trips(v)

        def material_inv(v, mass=mass, ds=ds, ds_keys=ds_keys, conv_key=conv_key, r=r_share,
                         ratio=ratio, rec=rec, trips=trips):
            kg = n_units * mass(v) / 1000 / trips(v)
            share = r(v)
            virgin_kg = kg * (1 - share) + (kg * share * ratio(v) if ratio is not None else 0.0)
            out = {ds_keys[_i(ds, v)]: virgin_kg}
            if rec is not None and rec["model"] == "dataset":
                out[rec["key"]] = out.get(rec["key"], 0.0) + kg * share
            if conv_key:
                out[conv_key] = out.get(conv_key, 0.0) + kg
            return out

        terms.append(Term(f"{pid}.{c['id']}.material", _deps(mass, ds, r_share, ratio, trips),
                          material, sign, material_inv))

        # Circular Footprint Formula: what cut-off leaves out (PEF, Annex C parameters)
        if b.system_model == "cff":
            p = b.cff[mid]
            A, q_in, q_out = float(p["A"]), float(p["Qsin_Qp"]), float(p["Qsout_Qp"])
            eol_key = p.get("recycling_eol_key")
            if eol_key:
                erec_eol = ("key", eol_key, b.f(eol_key))
            elif rec is not None and rec["model"] == "dataset":
                erec_eol = ("key", rec["key"], rec_f)
            elif ratio is not None:
                erec_eol = ("ratio", ratio, None)
            else:
                raise ValueError(f"data/cff/{mid}.json needs recycling_eol_key: {label} has no recycled dataset")

            # recycled content: R1 (A Erec + (1-A) Ev Qsin/Qp) instead of R1 Erec
            if rec is not None:
                def cff_content(xp_, v, mass=mass, ds=ds, virgin=virgin, r=r_share, ratio=ratio,
                                rec_f=rec_f, trips=trips, A=A, q_in=q_in):
                    vf = virgin[idx(ds, v)]
                    erec = ratio(v) * vf if ratio is not None else rec_f
                    return n_units * mass(v) / 1000 * r(v) * (1 - A) * (vf * q_in - erec) / trips(v)

                def cff_content_inv(v, mass=mass, ds=ds, ds_keys=ds_keys, r=r_share, ratio=ratio, rec=rec,
                                    trips=trips, A=A, q_in=q_in):
                    w = n_units * mass(v) / 1000 * r(v) * (1 - A) / trips(v)
                    vk = ds_keys[_i(ds, v)]
                    if ratio is not None:
                        return {vk: w * (q_in - ratio(v))}
                    return {vk: w * q_in, rec["key"]: -w}

                terms.append(Term(f"{pid}.{c['id']}.cff.material", _deps(mass, ds, r_share, ratio, trips),
                                  cff_content, sign, cff_content_inv))

        # end of life
        eol = m["end_of_life"]
        if eol["model"] == "split":
            rate = b.continuous(f"{pid}.{mid}.recycling_rate", eol["recycling_rate"],
                                f'What share of used {label} from "{pname}" is collected for recycling (0 to 1)?',
                                known.get("recycling_rate"), f"{mid}.recycling_rate")
            share = b.continuous(f"{pid}.{mid}.incineration_share", eol["incineration_share"],
                                 f'Of the {label} from "{pname}" not recycled, what share is incinerated (0 to 1)?',
                                 known.get("incineration_share"), f"{mid}.incineration_share")
            inc, land = b.f(eol["incineration"]), b.f(eol["landfill"])

            def end_of_life(xp_, v, mass=mass, rate=rate, share=share, inc=inc, land=land, trips=trips):
                s = share(v)
                return (n_units * mass(v) / 1000 * (1 - rate(v)) * (s * inc + (1 - s) * land)
                        / trips(v))

            def eol_inv(v, mass=mass, rate=rate, share=share, keys=(eol["incineration"], eol["landfill"]),
                        trips=trips):
                kg = n_units * mass(v) / 1000 * (1 - rate(v)) / trips(v)
                return {keys[0]: kg * share(v), keys[1]: kg * (1 - share(v))}

            deps = _deps(mass, rate, share, trips)
        else:
            fate, keys = b.categorical(f"{pid}.{mid}.end_of_life", eol["options"], eol["source"],
                                       eol["question"].format(c=where), known.get("end_of_life"),
                                       f"{mid}.end_of_life")
            table = xp.asarray([b.f(k) if k else 0.0 for k in keys], dtype=xp.float64)

            def end_of_life(xp_, v, mass=mass, fate=fate, table=table, trips=trips):
                return n_units * mass(v) / 1000 * table[idx(fate, v)] / trips(v)

            def eol_inv(v, mass=mass, fate=fate, keys=keys, trips=trips):
                key = keys[_i(fate, v)]
                return {key: n_units * mass(v) / 1000 / trips(v)} if key else {}

            deps = _deps(mass, fate, trips)
        terms.append(Term(f"{pid}.{c['id']}.end_of_life", deps, end_of_life, sign, eol_inv))

        if b.system_model == "cff":
            # recycling at end of life: (1-A) R2 (E_recycling,EoL - E*v Qsout/Qp)
            if eol["model"] == "split":
                r2_param, r2 = rate, (lambda v, rate=rate: rate(v))
            else:
                rec_opts = xp.asarray([1.0 if k is None else 0.0 for k in keys], dtype=xp.float64)
                r2_param = fate
                r2 = (lambda v, fate=fate, rec_opts=rec_opts: rec_opts[idx(fate, v)])

            def cff_eol(xp_, v, mass=mass, ds=ds, virgin=virgin, r2=r2, trips=trips, A=A, q_out=q_out,
                        erec_eol=erec_eol):
                vf = virgin[idx(ds, v)]
                e_eol = erec_eol[2] if erec_eol[0] == "key" else erec_eol[1](v) * vf
                return n_units * mass(v) / 1000 * (1 - A) * r2(v) * (e_eol - vf * q_out) / trips(v)

            def cff_eol_inv(v, mass=mass, ds=ds, ds_keys=ds_keys, r2=r2, trips=trips, A=A, q_out=q_out,
                            erec_eol=erec_eol):
                w = n_units * mass(v) / 1000 * (1 - A) * float(r2(v)) / trips(v)
                vk = ds_keys[_i(ds, v)]
                if erec_eol[0] == "key":
                    out = {vk: -w * q_out}
                    out[erec_eol[1]] = out.get(erec_eol[1], 0.0) + w
                    return out
                return {vk: w * (erec_eol[1](v) - q_out)}

            deps_cff = _deps(mass, ds, r2_param, trips, erec_eol[1] if erec_eol[0] == "ratio" else None)
            terms.append(Term(f"{pid}.{c['id']}.cff.end_of_life", deps_cff, cff_eol, sign, cff_eol_inv))

    if not spec["components"]:       # nothing whose mass the legs of the region would carry
        return terms

    # distribution, per fill (a refillable makes the empty return leg too)
    dist = b.legs("distribution")
    masses = tuple(total_mass)

    def transport(xp_, v, masses=masses, dist=dist, legs=legs):
        tonnes = sum(mp(v) for mp in masses) / 1e6
        return n_units * tonnes * legs * sum(km(v) * f for km, f, _ in dist)

    def transport_inv(v, masses=masses, dist=dist, legs=legs):
        tonnes = n_units * sum(mp(v) for mp in masses) / 1e6 * legs
        out = {}
        for km, _, key in dist:
            out[key] = out.get(key, 0.0) + tonnes * km(v)
        return out

    terms.append(Term(f"{pid}.transport", _deps(*total_mass, *[k for k, _, _ in dist]),
                      transport, sign, transport_inv))

    # supply of the packaging to the filler, once per container produced
    supply = b.legs("supply")
    if supply:
        def supply_t(xp_, v, masses=masses, supply=supply, trips=trips):
            tonnes = sum(mp(v) for mp in masses) / 1e6
            return n_units * tonnes * sum(km(v) * f for km, f, _ in supply) / trips(v)

        def supply_inv(v, masses=masses, supply=supply, trips=trips):
            tonnes = n_units * sum(mp(v) for mp in masses) / 1e6 / trips(v)
            out = {}
            for km, _, key in supply:
                out[key] = out.get(key, 0.0) + tonnes * km(v)
            return out

        terms.append(Term(f"{pid}.supply_transport", _deps(*total_mass, trips, *[k for k, _, _ in supply]),
                          supply_t, sign, supply_inv))

    if spec["refillable"]:
        r, given = cat.REFILLABLE, spec.get("reuse", {})
        kwh = b.continuous(f"{pid}.wash_kwh", r["wash_kwh"], r["wash_kwh"][3].format(p=f'"{pname}" container'),
                           given.get("wash_kwh"), "refillable.wash_kwh")
        heat = b.continuous(f"{pid}.wash_heat_mj", r["wash_heat_mj"], r["wash_heat_mj"][3].format(p=f'"{pname}" container'),
                            given.get("wash_heat_mj"), "refillable.wash_heat_mj")
        water = b.continuous(f"{pid}.wash_water_kg", r["wash_water_kg"], r["wash_water_kg"][3].format(p=f'"{pname}" container'),
                             given.get("wash_water_kg"), "refillable.wash_water_kg")
        grid, elec, elec_keys = b.electricity()
        heat_f, water_f = b.f(cat.UTILITIES["heat"]), b.f(cat.UTILITIES["water"])

        def washing(xp_, v, kwh=kwh, heat=heat, water=water, grid=grid):
            return n_units * (kwh(v) * elec[idx(grid, v)] + heat(v) * heat_f + water(v) * water_f)

        def washing_inv(v, kwh=kwh, heat=heat, water=water, grid=grid):
            return {elec_keys[_i(grid, v)]: n_units * kwh(v), cat.UTILITIES["heat"]: n_units * heat(v),
                    cat.UTILITIES["water"]: n_units * water(v)}

        terms.append(Term(f"{pid}.washing", _deps(kwh, heat, water, grid), washing, sign, washing_inv))
    return terms


# ----------------------------------------------------------------- model

def build_model(spec_a, spec_b, region="PT", category="Climate change", factors=None,
                functional_unit_l=1.0, xp=np, shared=None, country=None, system_model="cut-off"):
    """Comparative Model: delta = I_A - I_B per functional unit (litres delivered).

    region   region code from data/regions/ ("PT", "DE", "BR", "BR-N", "BR-AM", ...);
             country= is accepted as an alias.
    factors  dict from extract_factors.py (real_cases.load_factors()); loaded
             from data/factors/ when None.
    shared   values the user already knows for shared choices, e.g.
             {"distribution_km": 120} or {"electricity": "national grid (SIN)"}.
    system_model  "cut-off" (ISO default, ILCD Situation A) or "cff", the EU PEF
             Circular Footprint Formula with Annex C parameters from data/cff/.
    """
    if system_model not in ("cut-off", "cff"):
        raise ValueError("system_model must be 'cut-off' or 'cff'")
    region = load_region(country or region)
    if factors is None:
        from .real_cases import load_factors
        factors = load_factors()
    grid = (factors.get("factors") or {}).get(f"electricity_mv_{region.code}") or {}
    if region.name == region.code and grid.get("location"):       # country without a region file
        region.name = region.chain[0]["name"] = grid["location"]
    a, b_ = load_spec(spec_a), load_spec(spec_b)
    if a["id"] == b_["id"]:
        raise ValueError("the two alternatives need different ids")
    b = _Builder(region, category, factors, xp, shared, system_model)
    if system_model == "cff":
        missing = sorted({c["material"] for spec in (a, b_) for c in spec["components"]} - set(b.cff))
        if missing:
            raise ValueError("The Circular Footprint Formula needs PEF Annex C parameters in data/cff/ for: "
                             + ", ".join(missing))
    if a["components"] or b_["components"]:
        b.legs("distribution")        # shared choices first, as in the hand written model
    terms = (_product_terms(b, a, +1.0, functional_unit_l / a["volume_l"])
             + _product_terms(b, b_, -1.0, functional_unit_l / b_["volume_l"]))
    model = Model(list(b.choices.values()), terms, xp, label_a=a["name"], label_b=b_["name"])
    model.factor_data = factors
    model.build_args = {"spec_a": a, "spec_b": b_, "region": region.code,
                        "functional_unit_l": functional_unit_l, "shared": shared,
                        "system_model": system_model}
    model.meta = {"country": region.code, "region": region.name, "region_path": region.path,
                  "sources_needed": region.sources_needed() if (a["components"] or b_["components"]) else [],
                  "category": category,
                  "system_model": system_model, "method": factors.get("method"),
                  "factors_file": os.path.basename(factors.get("path", "")),
                  "citation": factors.get("citation"),
                  "functional_unit": _functional_unit(a, b_, functional_unit_l),
                  "products": [a, b_]}
    return model


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
                       system_model=args.get("system_model", "cut-off"))

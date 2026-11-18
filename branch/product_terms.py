"""The terms of one product: one small function per stage of its life cycle.

product_terms() is the only entry. It walks the product file in a fixed order and asks one function
per stage for its term: an input chosen by name, the material of a component, its end of life, the
additions of the Circular Footprint Formula, the distribution, the supply of the packaging, the
washing of a refillable container.

Each function that writes a term returns a Term with two views of the same exchange: fn, vectorised
over the Monte Carlo draws, and inventory, the amounts per factor key in one world, which is what is
written to openLCA. The order in which the functions create choices is the order of the columns of
the draws, so it is part of the result: tests/test_builder_golden.py fails when it changes.
"""
from dataclasses import dataclass
from typing import Any, Optional

from . import catalogue as cat
from .lca_model import Term
from .quantities import Param, as_scalar, deps, multiplier, option_index, option_table
from .spec import parse_process_key


@dataclass
class _Product:
    """What every term of one product shares."""
    b: Any                 # the builder: choices, factors, region
    spec: dict
    sign: float            # +1 for alternative A, -1 for B
    n_units: float         # containers per functional unit
    trips: Param           # uses of one container (1 when it is not refillable)
    legs: float            # distribution legs per fill (a refillable also returns empty)

    @property
    def pid(self):
        return self.spec["id"]

    @property
    def pname(self):
        return self.spec["name"]

    @property
    def xp(self):
        return self.b.xp

    def idx(self, p, v):
        """Option index of a categorical quantity, over the draws."""
        return self.xp.asarray(p(v)).astype(int)


@dataclass
class _Part:
    """One component of a product, with the quantities its terms share."""
    c: dict                # the component as the product file gives it
    mid: str               # material id
    m: dict                # the material of the catalogue
    known: dict            # what the product file fixes for this material
    mass: Param = None
    ds: Param = None               # which virgin dataset
    ds_keys: list = None
    virgin: Any = None             # factor of each virgin dataset
    virgin_u: list = None
    conv_key: Optional[str] = None
    conv: float = 0.0
    conv_u: Any = None
    rec: Optional[dict] = None     # how the catalogue models recycled content
    r_share: Param = None
    ratio: Optional[Param] = None  # impact of recycled relative to virgin, when there is no dataset
    rec_f: Optional[float] = None
    rec_u: Any = None

    @property
    def label(self):
        return self.m["label"]

    @property
    def cid(self):
        return self.c["id"]


@dataclass
class _Fate:
    """What happens to a component after use: a split by rates, or one option among several."""
    eol: dict
    rate: Param = None             # split: share collected for recycling
    share: Param = None            # split: share of the rest that is incinerated
    fate: Param = None             # options: which one
    keys: list = None              # options: factor key of each (None = recycled, no burden)

    @property
    def split(self):
        return self.eol["model"] == "split"


@dataclass
class _Cff:
    """Parameters of the Circular Footprint Formula for one component."""
    A: float
    q_in: float
    q_out: float
    burden: tuple                  # ("key", factor key, factor, uncertainty) or ("ratio", Param, None)


# ---------------------------------------------------------------- entry

def product_terms(b, spec, sign, n_units):
    """Terms of one alternative, already multiplied by containers per functional unit."""
    trips, legs = _reuse(b, spec)
    p = _Product(b, spec, sign, n_units * float(spec.get("units_per_functional_unit", 1.0)), trips, legs)
    terms = [_exchange_term(p, e) for e in spec.get("exchanges") or []]
    masses = []
    for c in spec["components"]:
        part = _part(p, c)
        masses.append(part.mass)
        terms += _component_terms(p, part)
    if not spec["components"]:       # nothing whose mass the legs of the region would carry
        return terms
    terms.append(_distribution_term(p, tuple(masses)))
    terms += _supply_terms(p, tuple(masses))
    if spec["refillable"]:
        terms.append(_washing_term(p))
    return terms


def _reuse(b, spec):
    """(trips, distribution legs per fill) of a container."""
    if not spec["refillable"]:
        return Param(const=1.0), 1
    r = cat.REFILLABLE
    trips = b.continuous(f"{spec['id']}.trips", r["trips"], r["trips"][3].format(p=f'"{spec["name"]}" container'),
                         spec.get("reuse", {}).get("trips"), "refillable.trips")
    return trips, cat.REFILLABLE_TRANSPORT_LEGS


def _component_terms(p, part):
    """Material and end of life of one component; with the Circular Footprint Formula, its additions."""
    terms = [_material_term(p, part)]
    cff = _cff(p, part) if p.b.system_model == "cff" else None
    if cff and part.rec is not None:
        terms.append(_cff_content_term(p, part, cff))
    fate, term = _end_of_life(p, part)
    terms.append(term)
    if cff:
        terms.append(_cff_end_of_life_term(p, part, fate, cff))
        energy = _cff_energy_term(p, part, fate)
        if energy:
            terms.append(energy)
    return terms


# ---------------------------------------------------------------- inputs chosen by name

def _exchange_term(p, e):
    """An input chosen from the database by process name: amount x unit factor, any life cycle stage."""
    b, key = p.b, e["key"]
    amount = _exchange_amount(p, e)
    fac, fac_u = b.f(key), b.u(key)
    n_units = p.n_units

    def exchange(xp_, v):
        return n_units * amount(v) * fac * multiplier(fac_u, v)

    def exchange_inv(v):
        return {key: n_units * amount(v)}

    return Term(f"{p.pid}.{e['id']}.{e['stage']}", deps(amount, fac_u), exchange, p.sign, exchange_inv)


def _exchange_amount(p, e):
    """The amount of an input: the number given, or a choice over the range given."""
    if not isinstance(e["amount"], list):
        return Param(const=float(e["amount"]))
    key, what = e["key"], e.get("label") or e["id"].replace("_", " ")
    unit = (p.b.data.get("factors", {}).get(key) or {}).get("unit") or "unit of the process"
    proc_name = (parse_process_key(key) or (key, None))[0]
    lo, hi = e["amount"]
    source = e.get("source") or (f"ASSUMPTION: range given by the user for {what}, "
                                 f"{lo:g} to {hi:g} {unit}; every value in it equally likely")
    if not source.startswith(("SOURCE:", "ASSUMPTION:")):
        source = "ASSUMPTION: " + source
    return p.b.continuous(f"{p.pid}.{e['id']}.amount", ("uniform", {"low": lo, "high": hi}, source),
                          f'How much "{proc_name}" does one "{p.pname}" need for {what} ({unit})?')


# ---------------------------------------------------------------- one component

def _part(p, c):
    """The quantities of one component, created in the order mass, virgin dataset, recycled content."""
    mid = c["material"]
    part = _Part(c, mid, p.b.materials[mid], p.spec["materials"].get(mid, {}))
    part.mass = _mass(p, c)
    _virgin(p, part)
    _recycled_content(p, part)
    return part


def _where(p, part):
    return f'{part.label} in "{p.pname}"'


def _mass(p, c):
    if "mass_g" in c:
        return Param(const=float(c["mass_g"]))
    dist, params, source = c["mass_prior"][:3]
    return p.b.continuous(f"{p.pid}.{c['id']}.mass_g", (dist, params, source),
                          f'How many grams does the {c["id"].replace("_", " ")} of "{p.pname}" weigh?',
                          None, f"{p.pid}.{c['id']}.mass_g")


def _virgin(p, part):
    """Which dataset stands for the virgin material, and the conversion process."""
    b, m, xp = p.b, part.m, p.xp
    part.ds, part.ds_keys = b.categorical(
        f"{p.pid}.{part.mid}.dataset", m["datasets"], m.get("datasets_source", "SOURCE: catalogue datasets"),
        m.get("dataset_question", "Which {c} dataset applies?").format(c=_where(p, part)),
        part.known.get("dataset"))
    part.virgin = xp.asarray([b.f(k) for k in part.ds_keys], dtype=xp.float64)
    part.virgin_u = [b.u(k) for k in part.ds_keys]
    part.conv_key = part.c.get("conversion", m["conversion"])
    part.conv = b.f(part.conv_key) if part.conv_key else 0.0
    part.conv_u = b.u(part.conv_key) if part.conv_key else None


def _recycled_content(p, part):
    """Share of recycled material, and its burden: a ratio to the virgin material or a dataset."""
    b, rec, known = p.b, part.m["recycled"], part.known
    part.rec = rec
    if rec is None:
        part.r_share, part.ratio, part.rec_f = Param(const=0.0), None, 0.0
        return
    own = part.c.get("recycled_content_prior")     # a component may carry its own prior (aluminium foil is not can sheet)
    part.r_share = b.continuous(f"{p.pid}.{part.mid}.recycled_content", tuple(own) if own else rec["content"],
                                f"What share of the {_where(p, part)} is recycled material (0 to 1)?",
                                known.get("recycled_content"), None if own else f"{part.mid}.recycled_content")
    if rec["model"] == "burden_ratio":
        part.ratio = b.continuous(f"{p.pid}.{part.mid}.recycled_ratio", rec["ratio"],
                                  f"Impact of recycled {part.label} relative to virgin {part.label} (0 to 1)?",
                                  known.get("recycled_ratio"), f"{part.mid}.recycled_ratio")
        part.rec_f = None
    else:
        part.ratio, part.rec_f, part.rec_u = None, b.f(rec["key"]), b.u(rec["key"])


def _material_term(p, k):
    """Virgin material, recycled content and conversion of one component."""
    n_units, trips, xp = p.n_units, p.trips, p.xp

    def material(xp_, v):
        kg = k.mass(v) / 1000
        vf = option_table(xp, k.virgin, k.virgin_u, p.idx(k.ds, v), v)
        recycled = k.ratio(v) * vf if k.ratio is not None else k.rec_f * multiplier(k.rec_u, v)
        r = k.r_share
        return n_units * kg * ((1 - r(v)) * vf + r(v) * recycled + k.conv * multiplier(k.conv_u, v)) / trips(v)

    def material_inv(v):
        kg = n_units * k.mass(v) / 1000 / trips(v)
        share = k.r_share(v)
        virgin_kg = kg * (1 - share) + (kg * share * k.ratio(v) if k.ratio is not None else 0.0)
        out = {k.ds_keys[option_index(k.ds, v)]: virgin_kg}
        if k.rec is not None and k.rec["model"] == "dataset":
            out[k.rec["key"]] = out.get(k.rec["key"], 0.0) + kg * share
        if k.conv_key:
            out[k.conv_key] = out.get(k.conv_key, 0.0) + kg
        return out

    return Term(f"{p.pid}.{k.cid}.material",
                deps(k.mass, k.ds, k.r_share, k.ratio, trips, *k.virgin_u, k.conv_u, k.rec_u),
                material, p.sign, material_inv)


# ---------------------------------------------------------------- end of life

def _end_of_life(p, part):
    """(what happens to the component, its term)."""
    eol = part.m["end_of_life"]
    return _eol_split(p, part, eol) if eol["model"] == "split" else _eol_options(p, part, eol)


def _eol_split(p, k, eol):
    """A recycling rate, and the rest shared between incineration and landfill."""
    b, known, n_units, trips = p.b, k.known, p.n_units, p.trips
    rate = b.continuous(f"{p.pid}.{k.mid}.recycling_rate", eol["recycling_rate"],
                        f'What share of used {k.label} from "{p.pname}" is collected for recycling (0 to 1)?',
                        known.get("recycling_rate"), f"{k.mid}.recycling_rate")
    share = b.continuous(f"{p.pid}.{k.mid}.incineration_share", eol["incineration_share"],
                         f'Of the {k.label} from "{p.pname}" not recycled, what share is incinerated (0 to 1)?',
                         known.get("incineration_share"), f"{k.mid}.incineration_share")
    inc, land = b.f(eol["incineration"]), b.f(eol["landfill"])
    inc_u, land_u = b.u(eol["incineration"]), b.u(eol["landfill"])
    keys = (eol["incineration"], eol["landfill"])

    def end_of_life(xp_, v):
        s = share(v)
        return (n_units * k.mass(v) / 1000 * (1 - rate(v))
                * (s * inc * multiplier(inc_u, v) + (1 - s) * land * multiplier(land_u, v)) / trips(v))

    def eol_inv(v):
        kg = n_units * k.mass(v) / 1000 * (1 - rate(v)) / trips(v)
        return {keys[0]: kg * share(v), keys[1]: kg * (1 - share(v))}

    term = Term(f"{p.pid}.{k.cid}.end_of_life", deps(k.mass, rate, share, trips, inc_u, land_u),
                end_of_life, p.sign, eol_inv)
    return _Fate(eol, rate=rate, share=share), term


def _eol_options(p, k, eol):
    """One fate among several (recycled, incinerated, landfilled), each with its dataset."""
    b, n_units, trips, xp = p.b, p.n_units, p.trips, p.xp
    fate, keys = b.categorical(f"{p.pid}.{k.mid}.end_of_life", eol["options"], eol["source"],
                               eol["question"].format(c=_where(p, k)), k.known.get("end_of_life"),
                               f"{k.mid}.end_of_life")
    table = xp.asarray([b.f(key) if key else 0.0 for key in keys], dtype=xp.float64)
    table_u = [b.u(key) for key in keys]

    def end_of_life(xp_, v):
        return n_units * k.mass(v) / 1000 * option_table(xp, table, table_u, p.idx(fate, v), v) / trips(v)

    def eol_inv(v):
        key = keys[option_index(fate, v)]
        return {key: n_units * k.mass(v) / 1000 / trips(v)} if key else {}

    term = Term(f"{p.pid}.{k.cid}.end_of_life", deps(k.mass, fate, trips, *table_u), end_of_life, p.sign, eol_inv)
    return _Fate(eol, fate=fate, keys=keys), term


# ---------------------------------------------------------------- Circular Footprint Formula

def _cff(p, k):
    """The parameters of Part C of Annex II for this material, and the burden of recycling at end of life."""
    params = p.b.cff[k.mid]
    return _Cff(float(params["A"]), float(params["Qsin_Qp"]), float(params["Qsout_Qp"]),
                _cff_recycling_burden(p, k, params))


def _cff_recycling_burden(p, k, params):
    """Impact of recycling the material at end of life: a dataset, or a share of the virgin material."""
    b, rec = p.b, k.rec
    eol_key = params.get("recycling_eol_key")
    if eol_key:
        return ("key", eol_key, b.f(eol_key), b.u(eol_key))
    if rec is not None and rec["model"] == "dataset":
        return ("key", rec["key"], k.rec_f, k.rec_u)
    if k.ratio is not None:
        return ("ratio", k.ratio, None)
    # no recycling dataset in the database: its impact as a share of the virgin material,
    # an explicit choice that the agent can ask about
    rr = cat.CFF_RECYCLING_RATIO
    return ("ratio", b.continuous(f"{p.pid}.{k.mid}.recycling_ratio", rr[:3], rr[3].format(label=k.label),
                                  k.known.get("recycling_ratio"), f"{k.mid}.recycling_ratio"), None)


def _cff_content_term(p, k, cff):
    """Recycled content: R1 (A Erec + (1-A) Ev Qsin/Qp) instead of R1 Erec. What cut-off leaves out."""
    n_units, trips, xp, A, q_in = p.n_units, p.trips, p.xp, cff.A, cff.q_in

    def cff_content(xp_, v):
        vf = option_table(xp, k.virgin, k.virgin_u, p.idx(k.ds, v), v)
        erec = k.ratio(v) * vf if k.ratio is not None else k.rec_f * multiplier(k.rec_u, v)
        return n_units * k.mass(v) / 1000 * k.r_share(v) * (1 - A) * (vf * q_in - erec) / trips(v)

    def cff_content_inv(v):
        w = n_units * k.mass(v) / 1000 * k.r_share(v) * (1 - A) / trips(v)
        vk = k.ds_keys[option_index(k.ds, v)]
        if k.ratio is not None:
            return {vk: w * (q_in - k.ratio(v))}
        return {vk: w * q_in, k.rec["key"]: -w}

    return Term(f"{p.pid}.{k.cid}.cff.material",
                deps(k.mass, k.ds, k.r_share, k.ratio, trips, *k.virgin_u, k.rec_u),
                cff_content, p.sign, cff_content_inv)


def _recycled_share(p, f):
    """R2: (the choice it depends on, the share recycled at end of life in each draw)."""
    if f.split:
        return f.rate, (lambda v: f.rate(v))
    rec_opts = p.xp.asarray([1.0 if key is None else 0.0 for key in f.keys], dtype=p.xp.float64)
    return f.fate, (lambda v: rec_opts[p.idx(f.fate, v)])


def _cff_end_of_life_term(p, k, f, cff):
    """Recycling at end of life: (1-A) R2 (E_recycling,EoL - E*v Qsout/Qp)."""
    n_units, trips, xp, A, q_out, burden = p.n_units, p.trips, p.xp, cff.A, cff.q_out, cff.burden
    r2_param, r2 = _recycled_share(p, f)

    def cff_eol(xp_, v):
        vf = option_table(xp, k.virgin, k.virgin_u, p.idx(k.ds, v), v)
        e_eol = burden[2] * multiplier(burden[3], v) if burden[0] == "key" else burden[1](v) * vf
        return n_units * k.mass(v) / 1000 * (1 - A) * r2(v) * (e_eol - vf * q_out) / trips(v)

    def cff_eol_inv(v):
        w = n_units * k.mass(v) / 1000 * (1 - A) * as_scalar(r2(v)) / trips(v)
        vk = k.ds_keys[option_index(k.ds, v)]
        if burden[0] == "key":
            out = {vk: -w * q_out}
            out[burden[1]] = out.get(burden[1], 0.0) + w
            return out
        return {vk: w * (burden[1](v) - q_out)}

    needs = deps(k.mass, k.ds, r2_param, trips, burden[1] if burden[0] == "ratio" else burden[3], *k.virgin_u)
    return Term(f"{p.pid}.{k.cid}.cff.end_of_life", needs, cff_eol, p.sign, cff_eol_inv)


def _burnt_share(p, f):
    """R3: (the share incinerated in each draw, the choices it depends on)."""
    if f.split:
        return (lambda v: (1 - f.rate(v)) * f.share(v)), (f.rate, f.share)
    burnt = p.xp.asarray([1.0 if "incinerat" in lab else 0.0 for lab in f.eol["options"]], dtype=p.xp.float64)
    return (lambda v: burnt[p.idx(f.fate, v)]), (f.fate,)


def _cff_energy_term(p, k, f):
    """Energy recovery, with B = 0 (the PEF default): R3 x (E_ER - LHV X_elec E_SE,elec - LHV X_heat E_SE,heat).

    R3 x E_ER is already the incineration part of the end of life term; what the formula adds is the
    credit for the electricity and the heat that the plant delivers. None when the material has no
    entry in data/cff/energy_recovery.json."""
    b = p.b
    rec_energy = b.energy.get(k.mid)
    if not rec_energy:
        return None
    kwh, steam = float(rec_energy["electricity_mj_per_kg"]) / 3.6, float(rec_energy["steam_mj_per_kg"])
    grid, elec, elec_keys, elec_u = b.electricity()
    heat_key = cat.CFF_HEAT_OPTIONS[b.cff_heat]
    if heat_key is None:                      # sensitivity: no credit for the heat
        heat_f, heat_u, steam = 0.0, None, 0.0
    else:
        heat_f, heat_u = b.f(heat_key), b.u(heat_key)
    r3, r3_params = _burnt_share(p, f)
    n_units, trips, xp = p.n_units, p.trips, p.xp

    def cff_energy(xp_, v):
        return (-n_units * k.mass(v) / 1000 * r3(v)
                * (kwh * option_table(xp, elec, elec_u, p.idx(grid, v), v) + steam * heat_f * multiplier(heat_u, v))
                / trips(v))

    def cff_energy_inv(v):
        w = n_units * k.mass(v) / 1000 * as_scalar(r3(v)) / trips(v)
        out = {elec_keys[option_index(grid, v)]: -w * kwh}
        if heat_key:
            out[heat_key] = -w * steam
        return out

    return Term(f"{p.pid}.{k.cid}.cff_energy.end_of_life",
                deps(k.mass, trips, grid, *r3_params, *elec_u, heat_u), cff_energy, p.sign, cff_energy_inv)


# ---------------------------------------------------------------- transport and washing

def _leg_deps(masses, legs, *more):
    return deps(*masses, *more, *[km for km, _, _, _ in legs], *[u for _, _, _, u in legs])


def _distribution_term(p, masses):
    """Distribution, per fill (a refillable makes the empty return leg too)."""
    dist, legs, n_units = p.b.legs("distribution"), p.legs, p.n_units

    def transport(xp_, v):
        tonnes = sum(mp(v) for mp in masses) / 1e6
        return n_units * tonnes * legs * sum(km(v) * f * multiplier(u, v) for km, f, _, u in dist)

    def transport_inv(v):
        tonnes = n_units * sum(mp(v) for mp in masses) / 1e6 * legs
        out = {}
        for km, _, key, _unc in dist:
            out[key] = out.get(key, 0.0) + tonnes * km(v)
        return out

    return Term(f"{p.pid}.transport", _leg_deps(masses, dist), transport, p.sign, transport_inv)


def _supply_terms(p, masses):
    """Supply of the packaging to the filler, once per container produced. [] when the region has no such leg."""
    supply, n_units, trips = p.b.legs("supply"), p.n_units, p.trips
    if not supply:
        return []

    def supply_t(xp_, v):
        tonnes = sum(mp(v) for mp in masses) / 1e6
        return n_units * tonnes * sum(km(v) * f * multiplier(u, v) for km, f, _, u in supply) / trips(v)

    def supply_inv(v):
        tonnes = n_units * sum(mp(v) for mp in masses) / 1e6 / trips(v)
        out = {}
        for km, _, key, _unc in supply:
            out[key] = out.get(key, 0.0) + tonnes * km(v)
        return out

    return [Term(f"{p.pid}.supply_transport", _leg_deps(masses, supply, trips), supply_t, p.sign, supply_inv)]


def _washing_choice(p, field):
    r = cat.REFILLABLE
    return p.b.continuous(f"{p.pid}.{field}", r[field], r[field][3].format(p=f'"{p.pname}" container'),
                          p.spec.get("reuse", {}).get(field), f"refillable.{field}")


def _washing_term(p):
    """Electricity, heat and water to wash a refillable container before each fill."""
    b, n_units, xp = p.b, p.n_units, p.xp
    kwh, heat, water = (_washing_choice(p, f) for f in ("wash_kwh", "wash_heat_mj", "wash_water_kg"))
    grid, elec, elec_keys, elec_u = b.electricity()
    heat_key, water_key = cat.UTILITIES["heat"], cat.UTILITIES["water"]
    heat_f, water_f = b.f(heat_key), b.f(water_key)
    heat_u, water_u = b.u(heat_key), b.u(water_key)

    def washing(xp_, v):
        return n_units * (kwh(v) * option_table(xp, elec, elec_u, p.idx(grid, v), v)
                          + heat(v) * heat_f * multiplier(heat_u, v) + water(v) * water_f * multiplier(water_u, v))

    def washing_inv(v):
        return {elec_keys[option_index(grid, v)]: n_units * kwh(v), heat_key: n_units * heat(v),
                water_key: n_units * water(v)}

    return Term(f"{p.pid}.washing", deps(kwh, heat, water, grid, *elec_u, heat_u, water_u),
                washing, p.sign, washing_inv)

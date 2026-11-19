"""The openLCA connector (Steps 2 and 7).

Reading:  experiments/openlca/extract_factors.py takes unit impact factors from the
          open openLCA database, once.
Writing:  push_comparison sends the resolved comparison back to the same
          database, so the user opens, inspects and edits it in openLCA
          (proposal section 4.4). For every alternative it creates
            * a product flow "BRANCH | <alternative> | <functional unit>",
            * a unit process with one exchange per dataset of the inventory,
              each linked to the BAFU process it came from (default provider);
              every continuous choice is an input parameter with its value,
              question, source, who decided it and, while it is open, its prior
              as uncertainty, and the amounts are formulas of those parameters,
            * a product system linked like the factor extraction.
          With verify=True it calculates both systems in openLCA and compares
          them with BRANCH's own numbers, so the connector checks itself.
          write_jsonld saves the same objects as an openLCA JSON-LD zip.

The values are those of one world (whatif.point_world): the human's answers,
the most probable option of open categorical choices and the median of open
continuous ones. Sending the same comparison again updates it in place.

BRANCH writes into the database that is open in openLCA. Work on a copy, or
make a backup first (in openLCA: right click the database, Backup database).

Requires openLCA 2.6 (the version checked) with the IPC server running (Tools > Developer tools >
IPC Server, port 8080) and the database the factors were extracted from.
"""
import logging
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any

import olca_schema as o

from .factors import factor
from .formulas import trace
from .olca_extract import linking_for, ready
from .whatif import point_world

CATEGORY = "BRANCH"
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/ashirabench/branch")
ITEMS_PROPERTY, ITEMS_UNIT = "Number of items", "Item(s)"
MAX_FORMULA = 900     # characters; the longest formula of the catalogue has 457
log = logging.getLogger(__name__)


def client(port: int = 8080):
    import olca_ipc as ipc
    return ipc.Client(port)


def _param_name(name):
    """openLCA parameter names must be identifiers."""
    return re.sub(r"\W", "_", name)


def _uid(*parts):
    """The same comparison always gets the same identifiers, so sending it again updates the objects
    in openLCA and does not pile up copies."""
    return str(uuid.uuid5(NAMESPACE, "|".join(str(p) for p in parts)))


def _items_property(c):
    """A 'number of items' flow property, its reference unit, and what had to be added for it.

    The property is looked up by its name, because its identifier differs between databases; it is
    accepted only if the reference unit of its unit group is 'Item(s)'. Databases imported without the
    openLCA reference data (BAFU:2026 is one) have none: BRANCH then adds 'Units of items' /
    'Number of items' with the unit 'Item(s)', with fixed identifiers, and says so (push_comparison
    returns them under "created")."""
    def unit_of(fp_ref):
        fp = c.get(o.FlowProperty, fp_ref.id)
        group = c.get(o.UnitGroup, fp.unit_group.id)
        return next((u for u in group.units if u.is_ref_unit), None)

    fp_ref = c.find(o.FlowProperty, ITEMS_PROPERTY)
    if fp_ref is None:
        fp_ref = next((d for d in c.get_descriptors(o.FlowProperty) if "item" in (d.name or "").lower()), None)
    unit = unit_of(fp_ref) if fp_ref is not None else None
    if unit is not None and (unit.name or "").lower().startswith("item"):
        return fp_ref, o.Ref(ref_type=o.RefType.Unit, id=unit.id, name=unit.name), []
    unit = o.Unit(id=_uid("unit", ITEMS_UNIT), name=ITEMS_UNIT, conversion_factor=1.0, is_ref_unit=True)
    group = o.UnitGroup(id=_uid("unit group", "Units of items"), name="Units of items", category=CATEGORY, units=[unit])
    prop = o.FlowProperty(id=_uid("flow property", ITEMS_PROPERTY), name=ITEMS_PROPERTY, category=CATEGORY,
                          flow_property_type=o.FlowPropertyType.PHYSICAL_QUANTITY,
                          unit_group=o.Ref(ref_type=o.RefType.UnitGroup, id=group.id, name=group.name))
    c.put(group)
    fp_ref = c.put(prop) or o.Ref(ref_type=o.RefType.FlowProperty, id=prop.id, name=prop.name)
    return fp_ref, o.Ref(ref_type=o.RefType.Unit, id=unit.id, name=unit.name), [group, prop]


def _provider_exchange(c, factors, key):
    """Reference exchange of the BAFU process behind a factor key."""
    entry = factors["factors"][key]
    proc = c.get(o.Process, entry["id"])
    if proc is None:
        raise LookupError(f"Process {entry.get('process')!r} ({entry['id']}) for {key!r} is not in the open "
                          "database. Open the database the factors were extracted from.")
    ref = next(e for e in proc.exchanges if e.is_quantitative_reference)
    return proc, ref


def uncertainty_of(choice):
    """The prior of an open continuous choice as an openLCA uncertainty, or (None, why not).

    openLCA has uniform, triangular, normal and lognormal distributions. A beta prior (the recycling
    rates) has no counterpart there, so it gets none and the parameter says so: openLCA's simulation
    then keeps that parameter at its value. For a lognormal, openLCA takes the value entered as
    geometric mean as the mean of its draws (checked in openLCA 2.6.2, experiments/openlca/openlca_lognormal),
    so the field receives median x exp(sigma^2 / 2), which gives draws with the median of the prior. Check
    again with every new version of openLCA: if openLCA corrects this, the factor must go."""
    dist, p = choice.prior
    T = o.UncertaintyType
    if dist == "uniform":
        return o.Uncertainty(distribution_type=T.UNIFORM_DISTRIBUTION, minimum=float(p["low"]), maximum=float(p["high"])), None
    if dist == "triangular":
        return o.Uncertainty(distribution_type=T.TRIANGLE_DISTRIBUTION, minimum=float(p["low"]), mode=float(p["mode"]),
                             maximum=float(p["high"])), None
    if dist == "normal":
        return o.Uncertainty(distribution_type=T.NORMAL_DISTRIBUTION, mean=float(p["mean"]), sd=float(p["sd"])), None
    if dist == "lognormal":
        sigma = float(p["sigma"])
        return o.Uncertainty(distribution_type=T.LOG_NORMAL_DISTRIBUTION,
                             geom_mean=float(p["median"]) * math.exp(sigma ** 2 / 2), geom_sd=math.exp(sigma)), None
    return None, (f"its prior is a {dist} distribution {p}, which openLCA does not have, so openLCA's simulation "
                  "keeps this parameter at its value")


@dataclass
class Built:
    """What one comparison becomes in openLCA."""
    objects: list          # [(flow, process)], one pair per alternative
    linking: Any           # how openLCA must link them to the processes of the database
    created: list          # unit group and flow property BRANCH had to add, [] when the database had them


@dataclass
class _Sending:
    """What every object of one comparison shares while it is being built."""
    c: Any
    model: Any
    result: dict
    world: dict            # the value of every choice in the world that is sent
    names: dict            # choice name -> parameter name in openLCA
    untraced: Any          # choices whose formula could not be written
    items_fp: Any
    items_unit: Any
    fu: str
    base: tuple            # what the identifiers are derived from
    side_of: dict          # choice name -> the alternatives whose terms use it
    provider_types: list


def build_objects(c, model, result):
    """olca-schema objects for both alternatives (Built).

    Every continuous choice a person can answer is an input parameter of the process, the amounts of
    the exchanges are formulas of those parameters, and a choice that is still open carries its prior
    as the uncertainty of the parameter. Editing a parameter in openLCA, or running openLCA's own Monte
    Carlo simulation on the product system, therefore moves the model. Categorical choices pick a
    dataset or a route and are not numbers: they stay at the option of this world and are listed in
    the description of the process."""
    world = point_world(model, result)
    names = {ch.name: _param_name(ch.name) for ch in model.choices if ch.kind == "continuous" and ch.askable}
    if len(set(names.values())) != len(names):
        raise ValueError("two choices would get the same parameter name in openLCA")
    inventory, untraced = trace(model, world, names)
    items_fp, items_unit, created = _items_property(c)
    fu = model.meta.get("functional_unit", "functional unit")
    s = _Sending(c, model, result, world, names, untraced, items_fp, items_unit, fu,
                 (model.label_a, model.label_b, fu, model.meta.get("country")), _sides(model), [])
    objects = [_alternative(s, label, exchanges) for label, exchanges in inventory.items()]
    return Built(objects, linking_for(s.provider_types), created)


def _sides(model):
    """Which alternative each choice belongs to: a parameter goes into the process that uses it."""
    side_of = {}
    for t in model.terms:
        for d in t.deps:
            side_of.setdefault(d, set()).add(model.label_a if t.sign > 0 else model.label_b)
    return side_of


def _alternative(s, label, exchanges):
    """(flow, process) of one alternative."""
    flow = o.Flow(id=_uid(*s.base, "flow", label), name=f"BRANCH | {label} | {s.fu}", category=CATEGORY,
                  flow_type=o.FlowType.PRODUCT_FLOW,
                  flow_properties=[o.FlowPropertyFactor(flow_property=s.items_fp, conversion_factor=1.0,
                                                        is_ref_flow_property=True)])
    ex = _exchanges(s, flow, exchanges)
    params, fixed_options = _parameters(s, label)
    process = o.Process(id=_uid(*s.base, "process", label), name=f"BRANCH | {label}", category=CATEGORY,
                        process_type=o.ProcessType.UNIT_PROCESS, description=_description(s, fixed_options),
                        exchanges=ex, parameters=params, last_internal_id=len(ex))
    return flow, process


def _exchanges(s, flow, exchanges):
    """The reference output, then one input per factor key, linked to the process of the database."""
    ex = [o.Exchange(internal_id=1, flow=o.Ref(ref_type=o.RefType.Flow, id=flow.id, name=flow.name),
                     flow_property=s.items_fp, unit=s.items_unit, amount=1.0, is_input=False,
                     is_quantitative_reference=True)]
    for key, (amount, formula) in sorted(exchanges.items()):
        if amount == 0:
            continue
        proc, ref = _provider_exchange(s.c, s.model.factor_data, key)
        s.provider_types.append(getattr(proc, "process_type", None))
        if formula is not None and len(formula) > MAX_FORMULA:
            formula = None            # too long for the field of the database: the amount stays a number
        waste = getattr(ref.flow, "flow_type", None) == o.FlowType.WASTE_FLOW
        ex.append(o.Exchange(internal_id=len(ex) + 1, flow=ref.flow, flow_property=ref.flow_property,
                             unit=ref.unit, amount=float(amount), amount_formula=formula, is_input=not waste,
                             default_provider=o.Ref(ref_type=o.RefType.Process, id=proc.id, name=proc.name),
                             description=f"BRANCH factor key: {key}"))
    return ex


def _parameters(s, label):
    """(input parameters of the continuous choices of this alternative, the options that were fixed)."""
    params, fixed_options = [], []
    for ch in s.model.choices:
        if not ch.askable or label not in s.side_of.get(ch.name, ()):
            continue
        value = s.world[ch.name]
        who = s.result["decided_by"][ch.name]
        if ch.kind != "continuous":
            fixed_options.append(f"{ch.question} {ch.decode(value)} (decided by: {who})")
            continue
        params.append(_parameter(s, label, ch, value, who))
    return params, fixed_options


def _parameter(s, label, ch, value, who):
    unc, why = (uncertainty_of(ch) if ch.is_open() else (None, None))
    note = ("" if ch.name not in s.untraced else
            " The amounts do not follow this parameter: its formula could not be written.")
    return o.Parameter(
        id=_uid(*s.base, "parameter", label, ch.name), name=s.names[ch.name], value=float(value),
        is_input_parameter=True, parameter_scope=o.ParameterScope.PROCESS_SCOPE, uncertainty=unc,
        description=(f"{ch.question} Value: {ch.decode(value)}. Decided by: {who}. "
                     f"Source of the default: {ch.source}"
                     + (f" No uncertainty in openLCA: {why}." if why else "") + note))


def _description(s, fixed_options):
    model, result = s.model, s.result
    return (f"Built by BRANCH. Comparison: {model.label_a} vs {model.label_b}, {s.fu}, "
            f"{model.meta.get('country')}. Verdict: {result['verdict']} "
            f"(probability wrong {result['p_flip']:.1%}, "
            f"{'certified' if result['certified'] else 'not certified'}). "
            f"The amounts are formulas of the input parameters of this process; a parameter that a person "
            f"answered has no uncertainty, and an open one carries the prior BRANCH used. "
            + ("Options fixed in this model, which are not numbers and cannot be parameters: "
               + "; ".join(fixed_options) + ". " if fixed_options else "")
            + f"Data: {model.meta.get('citation')}.")


def _drop_old_systems(c, process):
    """Delete the product systems that an earlier send built on this same process."""
    try:
        old = [d for d in c.get_descriptors(o.ProductSystem) if d.name == process.name]
    except Exception as exc:
        log.warning("the product systems of an earlier send could not be listed, so none was removed: %s", exc)
        return 0
    n = 0
    for d in old:
        try:
            system = c.get(o.ProductSystem, d.id)
            if system is not None and system.ref_process is not None and system.ref_process.id == process.id:
                c.delete(d)
                n += 1
        except Exception as exc:
            log.warning("the product system %s of an earlier send was not removed: %s", d.name, exc)
    return n


def push_comparison(c, model, result, verify=True, jsonld_path=None):
    """Write both alternatives to the open openLCA database (see module doc).

    Sending the same comparison again updates its flow, process and product system; it does not add
    copies. Returns {"processes": [Ref], "systems": [Ref], "flows": [Ref], "check": {...} or None,
    "created": [names of the unit group and flow property BRANCH had to add], "replaced": int}.
    """
    built = build_objects(c, model, result)
    linking = built.linking
    procs, systems, flows, replaced = [], [], [], 0
    for flow, process in built.objects:
        replaced += _drop_old_systems(c, process)
        c.put(flow)
        flows.append(o.Ref(ref_type=o.RefType.Flow, id=flow.id, name=flow.name))
        procs.append(c.put(process))
        systems.append(c.create_product_system(procs[-1], linking))
    if jsonld_path:
        write_jsonld(jsonld_path, built.objects, built.created)
    check = verify_in_openlca(c, model, result, systems) if verify else None
    return {"processes": procs, "systems": systems, "flows": flows, "check": check,
            "created": [x.name for x in built.created], "replaced": replaced}


def _method(c, model):
    """The impact method of the factors: by its identifier when the factor file has it, else by name."""
    mid, name = model.factor_data.get("method_id"), model.meta.get("method")
    method = None
    if mid:
        try:
            got = c.get(o.ImpactMethod, mid)
            method = o.Ref(ref_type=o.RefType.ImpactMethod, id=got.id, name=got.name) if got is not None else None
        except Exception as exc:         # looked for by name below
            log.debug("the impact method %s was not found by its identifier: %s", mid, exc)
            method = None
    if method is None and name:
        method = c.find(o.ImpactMethod, name)
    return method, name


def _impact(c, system, method, category):
    """What openLCA calculates for one product system and one impact category."""
    res = c.calculate(o.CalculationSetup(target=system, impact_method=method, amount=1.0))
    try:
        ready(res)
        return next(float(i.amount) for i in res.get_total_impacts() if i.impact_category.name == category)
    finally:
        res.dispose()


def _relative(olca, branch):
    return abs(olca - branch) / abs(branch) if branch else None


def verify_in_openlca(c, model, result, systems):
    """Calculate the pushed systems in openLCA and compare with BRANCH."""
    category = model.meta.get("category")
    method, method_name = _method(c, model)
    if method is None:
        return {"error": f"impact method {method_name!r} not found in the open database"}
    inv = model.inventory(point_world(model, result))
    out = {}
    for (label, exchanges), system in zip(inv.items(), systems):
        olca = _impact(c, system, method, category)
        branch = sum(a * factor(model.factor_data, k, category) for k, a in exchanges.items())
        out[label] = {"openLCA": olca, "BRANCH": branch, "relative_difference": _relative(olca, branch)}
    return out


def write_jsonld(path, objs, created=()):
    """openLCA JSON-LD zip of the new flows and processes. Import it into the
    database that holds the BAFU processes so the providers resolve."""
    from olca_schema.zipio import ZipWriter
    w = ZipWriter(path)
    try:
        for extra in created:
            w.write(extra)
        for flow, process in objs:
            w.write(flow)
            w.write(process)
    finally:
        w.close()
    return path


def diagnose_in_openlca(c, model, result, labels=None):
    """Per exchange check: each linked BAFU exchange alone in a temporary process,
    calculated in openLCA and compared with amount x unit factor. Finds which
    exchange explains a difference reported by verify_in_openlca. Temporary
    objects are deleted afterwards.

    Returns {label: [(factor key, openLCA, BRANCH, relative difference), ...]}."""
    method, _ = _method(c, model)
    category = model.meta.get("category")
    built = build_objects(c, model, result)
    out = {}
    for flow, process in built.objects:
        label = process.name.replace("BRANCH | ", "")
        if labels and label not in labels:
            continue
        out[label] = [_check_exchange_alone(c, model, flow, process, e, built.linking, method, category)
                      for e in process.exchanges if not e.is_quantitative_reference]
    return out


def _check_exchange_alone(c, model, flow, process, e, linking, method, category):
    """(factor key, openLCA, BRANCH, relative difference) of one exchange in a process of its own."""
    key = e.description.split(": ", 1)[1]
    ref_ex = next(x for x in process.exchanges if x.is_quantitative_reference)
    f = o.Flow(id=str(uuid.uuid4()), name=f"BRANCH check | {key}", category=CATEGORY,
               flow_type=o.FlowType.PRODUCT_FLOW, flow_properties=flow.flow_properties)
    r = o.Exchange(internal_id=1, flow=o.Ref(ref_type=o.RefType.Flow, id=f.id, name=f.name),
                   flow_property=ref_ex.flow_property, unit=ref_ex.unit, amount=1.0, is_input=False,
                   is_quantitative_reference=True)
    one = o.Exchange(internal_id=2, flow=e.flow, flow_property=e.flow_property, unit=e.unit,
                     amount=e.amount, amount_formula=e.amount_formula, is_input=e.is_input,
                     default_provider=e.default_provider)
    pr = o.Process(id=str(uuid.uuid4()), name=f"BRANCH check | {key}", category=CATEGORY,
                   process_type=o.ProcessType.UNIT_PROCESS, exchanges=[r, one], last_internal_id=2,
                   parameters=process.parameters if e.amount_formula else None)
    c.put(f)
    pref = c.put(pr)
    sys_ref = c.create_product_system(pref, linking)
    try:
        olca = _impact(c, sys_ref, method, category)
    finally:
        _delete_quietly(c, sys_ref, pref, o.Ref(ref_type=o.RefType.Flow, id=f.id))
    branch = e.amount * factor(model.factor_data, key, category)
    return key, olca, branch, _relative(olca, branch)


def _delete_quietly(c, *objects):
    """Remove temporary objects; one that openLCA refuses to delete must not hide the result."""
    for obj in objects:
        try:
            c.delete(obj)
        except Exception as exc:                 # reported, never raised: the check itself has finished
            log.warning("could not delete the temporary object %s from openLCA: %s", getattr(obj, "id", obj), exc)

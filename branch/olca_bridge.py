"""The openLCA connector (Steps 2 and 7).

Reading:  experiments/extract_factors.py takes unit impact factors from the
          open openLCA database, once.
Writing:  push_comparison sends the resolved comparison back to the same
          database, so the user opens, inspects and edits it in openLCA
          (proposal section 4.4). For every alternative it creates
            * a product flow "BRANCH | <alternative> | <functional unit>",
            * a unit process with one exchange per dataset of the inventory,
              each linked to the BAFU process it came from (default provider),
              and one parameter per modelling choice recording its value,
              question, source and who decided it,
            * a product system linked like the factor extraction.
          With verify=True it calculates both systems in openLCA and compares
          them with BRANCH's own numbers, so the connector checks itself.
          write_jsonld saves the same objects as an openLCA JSON-LD zip.

The amounts are those of one world (whatif.point_world): the human's answers,
the most probable option of open categorical choices and the median of open
continuous ones. The distributions stay in the BRANCH report.

Requires openLCA 2.x with the IPC server running (Tools > Developer tools >
IPC Server, port 8080) and the database the factors were extracted from.
"""
import re
import uuid

import olca_schema as o

from .whatif import point_world

LINKING = o.LinkingConfig(prefer_unit_processes=False, provider_linking=o.ProviderLinking.PREFER_DEFAULTS)
CATEGORY = "BRANCH"


def client(port: int = 8080):
    import olca_ipc as ipc
    return ipc.Client(port)


def _param_name(name):
    """openLCA parameter names must be identifiers."""
    return re.sub(r"\W", "_", name)


_CREATED = []      # unit group and flow property BRANCH had to add (also written to the JSON-LD zip)


def _items_property(c):
    """A 'number of items' flow property and its reference unit.

    Databases imported without the openLCA reference data (BAFU:2026 is one) have none:
    BRANCH then adds 'Units of items' / 'Number of items' with the unit 'Item(s)'."""
    fp_ref = c.find(o.FlowProperty, "Number of items")
    if fp_ref is None:
        fp_ref = next((d for d in c.get_descriptors(o.FlowProperty)
                       if "item" in (d.name or "").lower()), None)
    if fp_ref is None:
        unit = o.Unit(id=str(uuid.uuid4()), name="Item(s)", conversion_factor=1.0, is_ref_unit=True)
        group = o.UnitGroup(id=str(uuid.uuid4()), name="Units of items", category=CATEGORY, units=[unit])
        prop = o.FlowProperty(id=str(uuid.uuid4()), name="Number of items", category=CATEGORY,
                              flow_property_type=o.FlowPropertyType.PHYSICAL_QUANTITY,
                              unit_group=o.Ref(ref_type=o.RefType.UnitGroup, id=group.id, name=group.name))
        c.put(group)
        fp_ref = c.put(prop) or o.Ref(ref_type=o.RefType.FlowProperty, id=prop.id, name=prop.name)
        _CREATED[:] = [group, prop]
        return fp_ref, o.Ref(ref_type=o.RefType.Unit, id=unit.id, name=unit.name)
    fp = c.get(o.FlowProperty, fp_ref.id)
    group = c.get(o.UnitGroup, fp.unit_group.id)
    unit = next(u for u in group.units if u.is_ref_unit)
    return fp_ref, o.Ref(ref_type=o.RefType.Unit, id=unit.id, name=unit.name)


def _provider_exchange(c, factors, key):
    """Reference exchange of the BAFU process behind a factor key."""
    entry = factors["factors"][key]
    proc = c.get(o.Process, entry["id"])
    if proc is None:
        raise LookupError(f"Process {entry.get('process')!r} ({entry['id']}) for {key!r} is not in the open "
                          "database. Open the database the factors were extracted from.")
    ref = next(e for e in proc.exchanges if e.is_quantitative_reference)
    return proc, ref


def build_objects(c, model, result):
    """olca-schema objects for both alternatives: [(flow, process), ...]."""
    factors = model.factor_data
    world = point_world(model, result)
    inventory = model.inventory(world)
    items_fp, items_unit = _items_property(c)
    fu = model.meta.get("functional_unit", "functional unit")
    side_of = {}
    for t in model.terms:
        for d in t.deps:
            side_of.setdefault(d, set()).add(model.label_a if t.sign > 0 else model.label_b)

    out = []
    for label, exchanges in inventory.items():
        flow = o.Flow(id=str(uuid.uuid4()), name=f"BRANCH | {label} | {fu}", category=CATEGORY,
                      flow_type=o.FlowType.PRODUCT_FLOW,
                      flow_properties=[o.FlowPropertyFactor(flow_property=items_fp, conversion_factor=1.0,
                                                            is_ref_flow_property=True)])
        ex = [o.Exchange(internal_id=1, flow=o.Ref(ref_type=o.RefType.Flow, id=flow.id, name=flow.name),
                         flow_property=items_fp, unit=items_unit, amount=1.0, is_input=False,
                         is_quantitative_reference=True)]
        for key, amount in sorted(exchanges.items()):
            if amount == 0:
                continue
            proc, ref = _provider_exchange(c, factors, key)
            waste = getattr(ref.flow, "flow_type", None) == o.FlowType.WASTE_FLOW
            ex.append(o.Exchange(internal_id=len(ex) + 1, flow=ref.flow, flow_property=ref.flow_property,
                                 unit=ref.unit, amount=float(amount), is_input=not waste,
                                 default_provider=o.Ref(ref_type=o.RefType.Process, id=proc.id, name=proc.name),
                                 description=f"BRANCH factor key: {key}"))
        params = []
        for ch in model.choices:
            if label not in side_of.get(ch.name, ()):
                continue
            value = world[ch.name]
            shown = ch.decode(value)
            params.append(o.Parameter(
                id=str(uuid.uuid4()), name=_param_name(ch.name), value=float(value),
                is_input_parameter=True, parameter_scope=o.ParameterScope.PROCESS_SCOPE,
                description=(f"{ch.question} Value: {shown}. Decided by: {result['decided_by'][ch.name]}. "
                             f"Source of the default: {ch.source}")))
        desc = (f"Built by BRANCH. Comparison: {model.label_a} vs {model.label_b}, {fu}, "
                f"{model.meta.get('country')}. Verdict: {result['verdict']} "
                f"(probability wrong {result['p_flip']:.1%}, "
                f"{'certified' if result['certified'] else 'not certified'}). "
                f"Amounts at the human's answers and the most probable value of the remaining choices; "
                f"their distributions are in the BRANCH report. Data: {model.meta.get('citation')}.")
        process = o.Process(id=str(uuid.uuid4()), name=f"BRANCH | {label}", category=CATEGORY,
                            process_type=o.ProcessType.UNIT_PROCESS, description=desc,
                            exchanges=ex, parameters=params, last_internal_id=len(ex))
        out.append((flow, process))
    return out


def push_comparison(c, model, result, verify=True, jsonld_path=None):
    """Write both alternatives to the open openLCA database (see module doc).

    Returns {"processes": [Ref], "systems": [Ref], "check": {...} or None}.
    """
    objs = build_objects(c, model, result)
    procs, systems = [], []
    for flow, process in objs:
        c.put(flow)
        procs.append(c.put(process))
        systems.append(c.create_product_system(procs[-1], LINKING))
    if jsonld_path:
        write_jsonld(jsonld_path, objs)
    check = verify_in_openlca(c, model, result, systems) if verify else None
    return {"processes": procs, "systems": systems, "check": check}


def verify_in_openlca(c, model, result, systems):
    """Calculate the pushed systems in openLCA and compare with BRANCH."""
    from .builder import factor
    method_name = model.meta.get("method")
    category = model.meta.get("category")
    method = c.find(o.ImpactMethod, method_name) if method_name else None
    if method is None:
        return {"error": f"impact method {method_name!r} not found in the open database"}
    inv = model.inventory(point_world(model, result))
    out = {}
    for (label, exchanges), system in zip(inv.items(), systems):
        res = c.calculate(o.CalculationSetup(target=system, impact_method=method, amount=1.0))
        res.wait_until_ready()
        try:
            olca = next(float(i.amount) for i in res.get_total_impacts()
                        if i.impact_category.name == category)
        finally:
            res.dispose()
        branch = sum(a * factor(model.factor_data, k, category) for k, a in exchanges.items())
        out[label] = {"openLCA": olca, "BRANCH": branch,
                      "relative_difference": abs(olca - branch) / abs(branch) if branch else None}
    return out


def write_jsonld(path, objs):
    """openLCA JSON-LD zip of the new flows and processes. Import it into the
    database that holds the BAFU processes so the providers resolve."""
    from olca_schema.zipio import ZipWriter
    w = ZipWriter(path)
    try:
        for extra in _CREATED:
            w.write(extra)
        for flow, process in objs:
            w.write(flow)
            w.write(process)
    finally:
        w.close()
    return path


class OpenLCA:
    """Small helpers kept for interactive use."""

    def __init__(self, port: int = 8080):
        self.client = client(port)

    def find_process(self, name: str):
        for d in self.client.get_descriptors(o.Process):
            if d.name == name:
                return self.client.get(o.Process, d.id)
        raise LookupError(name)

    def find_method(self, name: str):
        for d in self.client.get_descriptors(o.ImpactMethod):
            if name in d.name:
                return d
        raise LookupError(name)

    def push(self, model, result, **kw):
        return push_comparison(self.client, model, result, **kw)


def diagnose_in_openlca(c, model, result, labels=None):
    """Per exchange check: each linked BAFU exchange alone in a temporary process,
    calculated in openLCA and compared with amount x unit factor. Finds which
    exchange explains a difference reported by verify_in_openlca. Temporary
    objects are deleted afterwards.

    Returns {label: [(factor key, openLCA, BRANCH, relative difference), ...]}."""
    from .builder import factor
    method = c.find(o.ImpactMethod, model.meta.get("method"))
    category = model.meta.get("category")
    out = {}
    for flow, process in build_objects(c, model, result):
        label = process.name.replace("BRANCH | ", "")
        if labels and label not in labels:
            continue
        ref_ex = next(e for e in process.exchanges if e.is_quantitative_reference)
        rows = []
        for e in process.exchanges:
            if e.is_quantitative_reference:
                continue
            key = e.description.split(": ", 1)[1]
            f = o.Flow(id=str(uuid.uuid4()), name=f"BRANCH check | {key}", category=CATEGORY,
                       flow_type=o.FlowType.PRODUCT_FLOW, flow_properties=flow.flow_properties)
            r = o.Exchange(internal_id=1, flow=o.Ref(ref_type=o.RefType.Flow, id=f.id, name=f.name),
                           flow_property=ref_ex.flow_property, unit=ref_ex.unit, amount=1.0, is_input=False,
                           is_quantitative_reference=True)
            one = o.Exchange(internal_id=2, flow=e.flow, flow_property=e.flow_property, unit=e.unit,
                             amount=e.amount, is_input=e.is_input, default_provider=e.default_provider)
            pr = o.Process(id=str(uuid.uuid4()), name=f"BRANCH check | {key}", category=CATEGORY,
                           process_type=o.ProcessType.UNIT_PROCESS, exchanges=[r, one], last_internal_id=2)
            c.put(f)
            pref = c.put(pr)
            sys_ref = c.create_product_system(pref, LINKING)
            res = c.calculate(o.CalculationSetup(target=sys_ref, impact_method=method, amount=1.0))
            res.wait_until_ready()
            try:
                olca = next(float(i.amount) for i in res.get_total_impacts()
                            if i.impact_category.name == category)
            finally:
                res.dispose()
            branch = e.amount * factor(model.factor_data, key, category)
            rows.append((key, olca, branch, abs(olca - branch) / abs(branch) if branch else None))
            for obj in (sys_ref, pref, o.Ref(ref_type=o.RefType.Flow, id=f.id)):
                try:
                    c.delete(obj)
                except Exception:
                    pass
        out[label] = rows
    return out

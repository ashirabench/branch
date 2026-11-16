"""Unit impact factors from the open openLCA database (used by the connector and
experiments/extract_factors.py).

For every process BRANCH needs, builds a product system in openLCA, calculates it with
the chosen LCIA method and stores the impact per unit of the reference exchange (per kg,
kWh, t*km, MJ). The agent then works on these factors only and never calls openLCA in
its Monte Carlo loop. The factors stay on the user's computer: the BAFU terms of use do
not allow redistributing them.
"""
import json
import os
import re
import time

import olca_schema as o

# key -> list of name patterns tried in order (case insensitive substring).
# First unique match wins. When several datasets share the same name and
# differ only by location, LOCATION_PREFERENCE decides (see match()).
LOCATION_PREFERENCE = ["RER", "Europe", "GLO", "Global", "UCTE", "CH", "Switzerland"]
PROCESSES = {
    "pet_granulate_bottle_grade": ["Polyethylene terephthalate, granulate, bottle grade, at plant"],
    "pet_granulate_amorphous": ["Polyethylene terephthalate, granulate, amorphous, at plant"],
    "stretch_blow_moulding": ["Stretch blow moulding", "blow moulding"],
    # The BAFU names of these start with "xx"; three copies differ by location.
    "glass_packaging_white": ["xx Packaging glass, white, at plant"],
    "glass_packaging_green": ["xx Packaging glass, green, at plant"],
    "glass_packaging_brown": ["xx Packaging glass, brown, at plant"],
    "electricity_mv_PT": ["Electricity, medium voltage, production PT, at grid"],
    "electricity_mv_DE": ["Electricity, medium voltage, production DE, at grid"],
    "electricity_mv_BR": ["Electricity, medium voltage, production BR, at grid"],
    "lorry_16_32t": ["Transport, freight, lorry, 16t-32t gross weight, fleet average"],
    "tap_water_RER": ["Tap water, unspecified natural origin RER, at user"],
    "heat_natural_gas_furnace": ["Heat, natural gas, at industrial furnace 1MW"],
    # Disposal of plastics: the dataset of the polymer where BAFU:2026 has a current one
    # (list of 14 November 2026: PET incineration, polyethylene incineration and landfill).
    # The PET landfill dataset of the database is marked obsolete ("xx"), so the landfill
    # of PET uses the plastics mixture, a PROXY; so do the materials with no dataset at all.
    "disposal_polyethylene_terephthalate_incineration": [
        "Disposal, polyethylene terephtalate, 0.2% water, to municipal incineration"],
    "disposal_polyethylene_incineration": ["Disposal, polyethylene, 0.4% water, to municipal incineration"],
    "disposal_polyethylene_landfill": ["Disposal, polyethylene, 0.4% water, to sanitary landfill"],
    "disposal_plastics_mixture_incineration": ["Disposal, plastics, mixture, 15.3% water, to municipal incineration"],
    "disposal_plastics_mixture_landfill": ["Disposal, plastics, mixture, 15.3% water, to sanitary landfill"],
    "disposal_glass_incineration": ["Disposal, glass, 0% water, to municipal incineration"],
    "disposal_glass_landfill": ["Disposal, glass, 0% water, to inert material landfill",
                                "Disposal, glass, 0% water, to construction waste landfill"],
    # Primary metal: the production mix of wrought alloy already holds 46% of secondary aluminium.
    "aluminium_primary": ["Aluminium, primary, at plant"],
    # Only for a sensitivity run of the energy credit of the Circular Footprint Formula.
    "district_heat_ch_average": ["District heat, at consumer, swiss average, allocation exergy"],
    "aluminium_secondary_old_scrap": ["Aluminium, secondary, from old scrap, at plant"],
    "liquid_packaging_board": ["Liquid packaging board, at plant"],
    # Added for the generic builder (catalogue.py). UNVERIFIED names: check with
    # --find and edit the pattern if a key ends up in "unresolved".
    "hdpe_granulate": ["Polyethylene, HDPE, granulate, at plant"],
    "ldpe_granulate": ["Polyethylene, LDPE, granulate, at plant"],
    "injection_moulding": ["Injection moulding"],
    "film_extrusion": ["Extrusion, plastic film"],
    "sheet_rolling_aluminium": ["Sheet rolling, aluminium"],
    "disposal_aluminium_incineration": ["Disposal, aluminium, 0% water, to municipal incineration"],
    "disposal_aluminium_landfill": ["Disposal, aluminium, 0% water, to sanitary landfill"],
    "disposal_board_incineration": ["Disposal, packaging cardboard, 19.6% water, to municipal incineration"],
    "disposal_board_landfill": ["Disposal, packaging cardboard, 19.6% water, to sanitary landfill"],
    # Regions (data/regions/). UNVERIFIED names. Factors must be per kWh and per t*km.
    "transport_barge": ["Transport, barge"],
    "transport_freight_rail": ["Transport, freight, rail"],
    # BAFU:2026 has no Brazilian oil fired plant: UCTE (European average) is a PROXY.
    "electricity_oil_power_plant": ["Electricity, oil, at power plant"],
    # Secondary packaging (names checked in lists exported from the database, kept out of git). RER is preferred over CH.
    "corrugated_board_box": ["Packaging, corrugated board, mixed fibre, single wall, at plant"],
    "packaging_film_ldpe": ["Packaging film, LDPE, at plant"],
    "eur_pallet": ["EUR-flat pallet"],
    # More packaging materials (data/materials/). Names read in the BAFU-2026 v1.1 database files.
    "pp_granulate": ["Polypropylene, granulate, at plant"],
    "ps_gpps": ["Polystyrene, general purpose, GPPS, at plant"],
    "ps_hips": ["Polystyrene, high impact, HIPS, at plant"],
    "eps_expandable": ["Polystyrene, expandable, at plant"],
    "pvc_regional_storage": ["Polyvinylchloride, at regional storage"],
    "pla_granulate": ["Polylactide, granulate, at plant"],
    "thermoforming": ["Thermoforming, with calendering"],
    "steel_unalloyed": ["Steel, converter, unalloyed, at plant"],
    "sheet_rolling_steel": ["Sheet rolling, steel"],
    "kraft_paper_unbleached": ["Kraft paper, unbleached, at plant"],
    "kraft_paper_bleached": ["Kraft paper, bleached, at plant"],
    "folding_boxboard": ["Folding boxboard, FBB, at plant"],
    "solid_bleached_board": ["Solid bleached board, SBB, at plant"],
    "solid_unbleached_board": ["Solid unbleached board, SUB, at plant"],
    "whitelined_chipboard": ["Whitelined chipboard, WLC, at plant"],
    "disposal_pp_incineration": ["Disposal, polypropylene, 15.9% water, to municipal incineration"],
    "disposal_ps_incineration": ["Disposal, polystyrene, 0.2% water, to municipal incineration"],
    "disposal_expanded_polystyrene_incineration": [
        "Disposal, expanded polystyrene, 5% water, to municipal incineration"],
    "disposal_ps_landfill": ["Disposal, polystyrene, 0.2% water, to sanitary landfill"],
    "disposal_pvc_incineration": ["Disposal, polyvinylchloride, 0.2% water, to municipal incineration"],
    "disposal_pvc_landfill": ["Disposal, polyvinylchloride, 0.2% water, to sanitary landfill"],
    "disposal_tin_sheet_incineration": ["Disposal, tin sheet, 0% water, to municipal incineration"],
    "disposal_tin_sheet_landfill": ["Disposal, tin sheet, 0% water, to sanitary landfill"],
    "disposal_packaging_paper_incineration": ["Disposal, packaging paper, 13.7% water, to municipal incineration"],
    "disposal_paper_landfill": ["Disposal, paper, 11.2% water, to sanitary landfill"],
}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def all_processes(client):
    return client.get_descriptors(o.Process)


def loc(d):
    return getattr(d, "location", None) or ""


def by_location(cands):
    """Same name, different locations: pick by LOCATION_PREFERENCE."""
    if len({norm(c.name) for c in cands}) != 1:
        return None
    for pref in LOCATION_PREFERENCE:
        hit = [c for c in cands if norm(loc(c)) == norm(pref)]
        if len(hit) == 1:
            return hit[0]
    return None


def match(descs, patterns):
    """Alternatives tried in order; then all fragments AND-ed."""
    for p in patterns:
        hits = [d for d in descs if norm(p) in norm(d.name)]
        if len(hits) == 1:
            return hits[0], hits
        exact = [d for d in hits if norm(d.name) == norm(p)] or hits
        if len(exact) == 1:
            return exact[0], hits
        chosen = by_location(exact)
        if chosen is not None:
            return chosen, hits
    # all fragments together
    hits = [d for d in descs if all(norm(p) in norm(d.name) for p in patterns)]
    return (hits[0] if len(hits) == 1 else None), hits


def resolve(descs, key, procs=None):
    """(process descriptor or None, candidates) for a factor key: a catalogue key
    (name patterns in PROCESSES) or any process chosen by its exact name ("proc:<name>",
    builder.process_key), with " @<location>" when several locations share the name."""
    from .builder import parse_process_key
    chosen = parse_process_key(key)
    if chosen is None:
        return match(descs, (procs or PROCESSES).get(key, [key]))
    name, location = chosen
    hits = [d for d in descs if norm(d.name) == norm(name)]
    if location:
        hits = [d for d in hits if norm(loc(d)) == norm(location)]
    if len(hits) == 1:
        return hits[0], hits
    return (by_location(hits) if hits else None), hits


def find_method(client, name):
    hits = [d for d in client.get_descriptors(o.ImpactMethod) if norm(name) in norm(d.name)]
    if not hits:
        raise LookupError(f"No LCIA method contains {name!r}. Run with --methods to list them.")
    return sorted(hits, key=lambda d: len(d.name))[0]


def linking(proc):
    """How openLCA may connect the process to the rest of the database.

    A unit process (BAFU) needs its inputs linked to their providers. An aggregated process (an
    "LCI result", as in ELCD) already holds its whole inventory: letting openLCA link what is left
    over attaches it to unrelated data sets (on 16 November 2026 it sent the spoil of the Portuguese
    electricity of ELCD to container glass and almost doubled the result). There only the default
    providers are linked."""
    aggregated = getattr(proc, "process_type", None) == o.ProcessType.LCI_RESULT
    return o.LinkingConfig(prefer_unit_processes=False,
                           provider_linking=(o.ProviderLinking.ONLY_DEFAULTS if aggregated
                                             else o.ProviderLinking.PREFER_DEFAULTS))


def linking_for(process_types):
    """Linking for a process BRANCH builds on several providers: only the default providers when every
    provider is an aggregated process, as in `linking`; otherwise the linking of unit processes. A
    database that mixes the two kinds gets the linking of unit processes, and the check that openLCA
    runs after a send (olca_bridge.verify_in_openlca) shows whether that was right."""
    types = [t for t in process_types if t is not None]
    aggregated = bool(types) and all(t == o.ProcessType.LCI_RESULT for t in types)
    return o.LinkingConfig(prefer_unit_processes=False,
                           provider_linking=(o.ProviderLinking.ONLY_DEFAULTS if aggregated
                                             else o.ProviderLinking.PREFER_DEFAULTS))


def unit_impacts(client, proc_ref, method_ref):
    """Impacts per unit of the reference flow of one process."""
    proc = client.get(o.Process, proc_ref.id)
    ref_ex = next(e for e in proc.exchanges if e.is_quantitative_reference)
    system = client.create_product_system(proc_ref, linking(proc))
    # amount 1 in the unit of the reference EXCHANGE (e.g. kWh), not of the flow's
    # reference unit (e.g. MJ): BRANCH multiplies these factors by amounts in that unit.
    setup = o.CalculationSetup(target=system, impact_method=method_ref, amount=1.0,
                               unit=ref_ex.unit, flow_property=ref_ex.flow_property)
    result = client.calculate(setup)
    result.wait_until_ready()
    try:
        impacts = {i.impact_category.name: float(i.amount) for i in result.get_total_impacts()}
    finally:
        result.dispose()
        client.delete(system)
    return {"process": proc.name, "id": proc.id,
            "location": proc.location.name if proc.location else None,
            "unit": ref_ex.unit.name if ref_ex.unit else None,
            "flow": ref_ex.flow.name if ref_ex.flow else None,
            "impacts": impacts}


def simulate_impacts(client, proc_ref, method_ref, runs, tick=None):
    """Monte Carlo of one process in openLCA: {category: [impact of one unit in each run]}.

    Every run draws the exchanges of the whole product system from the distributions that the
    database states for them, and calculates again. tick(i, runs) is called after each run."""
    proc = client.get(o.Process, proc_ref.id)
    ref_ex = next(e for e in proc.exchanges if e.is_quantitative_reference)
    system = client.create_product_system(proc_ref, linking(proc))
    setup = o.CalculationSetup(target=system, impact_method=method_ref, amount=1.0,
                               unit=ref_ex.unit, flow_property=ref_ex.flow_property)
    result = client.simulate(setup)
    out = {}
    try:
        result.wait_until_ready()
        if getattr(result, "error", None) is not None:
            raise RuntimeError(result.error.error)
        for i in range(runs):
            state = result.simulate_next()
            if getattr(state, "error", None):
                raise RuntimeError(state.error)
            result.wait_until_ready()
            for imp in result.get_total_impacts():
                out.setdefault(imp.impact_category.name, []).append(float(imp.amount))
            if tick:
                tick(i + 1, runs)
    finally:
        result.dispose()
        client.delete(system)
    return out


def spread(values, central):
    """Summary of the runs of one category: geometric standard deviation and how the runs sit
    around the value BRANCH uses. No geometric standard deviation when more than 5% of the runs
    have the other sign or are zero: a lognormal multiplier cannot describe such a factor."""
    import math
    n = len(values)
    if n < 2 or not central:
        return {"gsd": None, "n": n, "note": "too few runs or a factor of zero"}
    same = [v / central for v in values if v / central > 0]
    out = {"n": n, "other_sign": n - len(same)}
    if len(same) < 0.95 * n:
        return dict(out, gsd=None, note="more than 5% of the runs have the other sign")
    logs = [math.log(v) for v in same]
    mean = sum(logs) / len(logs)
    sd = math.sqrt(sum((x - mean) ** 2 for x in logs) / (len(logs) - 1))
    ordered = sorted(same)
    return dict(out, gsd=math.exp(sd), median_ratio=ordered[len(ordered) // 2], mean_ratio=sum(same) / len(same))


def citation_for(database):
    year = re.search(r"20\d\d", database or "")
    return ("Life Cycle Inventory database of the Swiss Federal Administration, BAFU:"
            + (year.group(0) if year else "20XY"))


def extract(client, path, method="EF 3.1", database="bafu2026", all_grids=True, keys=None,
            update=False, progress=print):
    """Extract factors into the JSON file at path. Returns the saved dict.

    progress(done, total, message) is called after every dataset when it accepts three
    arguments; a one argument callable (print) receives the message only."""
    def say(i, n, msg):
        try:
            progress(i, n, msg)
        except TypeError:
            progress(msg)

    descs = all_processes(client)
    m = find_method(client, method)
    out = {"database": database, "method": m.name, "method_id": m.id, "citation": citation_for(database),
           "extracted": time.strftime("%Y-%m-%d"), "factors": {}, "unresolved": {}}
    chosen = []                      # processes people chose by name stay in the file across extractions
    if os.path.exists(path):
        with open(path) as fh:
            old = json.load(fh).get("factors", {})
        if update:
            out["factors"] = old
        else:
            chosen = [k for k in old if k.startswith("proc:")]
    procs = dict(PROCESSES)
    if all_grids:
        pat = re.compile(r"^Electricity, medium voltage, production ([A-Za-z-]+), at grid$")
        for d in descs:
            mm = pat.match((d.name or "").strip())
            if mm:
                procs.setdefault(f"electricity_mv_{mm.group(1)}", [d.name])
    todo = [k for k in list(keys or procs) + chosen if k not in out["factors"]]
    todo = list(dict.fromkeys(todo))
    for i, key in enumerate(todo, 1):
        ref, hits = resolve(descs, key, procs)
        if ref is None:
            out["unresolved"][key] = [f"{h.name} [{loc(h)}]" for h in hits[:15]]
            say(i, len(todo), f"?  {key}: {len(hits)} candidates")
            continue
        try:
            out["factors"][key] = unit_impacts(client, ref, m)
            say(i, len(todo), f"ok {key}: {ref.name} [{loc(ref)}]")
        except Exception as exc:  # keep going, report at the end
            out["unresolved"][key] = [f"calculation failed: {exc}"]
            say(i, len(todo), f"!! {key}: {exc}")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    return out

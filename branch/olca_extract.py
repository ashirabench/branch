"""Unit impact factors from the open openLCA database (used by the connector and
experiments/openlca/extract_factors.py).

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

from .paths import data_path
from .spec import parse_process_key

# Which process of the database stands for each thing BRANCH needs is not code: it is a file,
# data/databases/<database>.json, one per database (docs/BRING_YOUR_DATABASE.md). This module reads
# it into the names below, which the rest of the code uses.
#   PROCESSES            key -> names tried in order (case insensitive). The first that matches
#                        exactly one process wins.
#   LOCATION_PREFERENCE  when several processes share the name and differ by location (see match()).
#   GRID_PATTERN         how the database names the electricity of a country; group 1 is the code.
MAP_DIR = data_path("databases")
DEFAULT_MAP = "bafu2026"
REQUIRED = ("database", "citation", "location_preference", "grid_name_pattern", "datasets")


def load_database_map(name=None):
    """The map of one database: a name in data/databases/ (without .json) or the path of a file."""
    name = name or os.environ.get("BRANCH_DATABASE_MAP") or DEFAULT_MAP
    path = name if os.path.isfile(name) else os.path.join(MAP_DIR, name + ".json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No map of the database at {path}. docs/BRING_YOUR_DATABASE.md says how to write one.")
    with open(path, encoding="utf-8") as fh:
        m = json.load(fh)
    missing = [k for k in REQUIRED if k not in m]
    if missing:
        raise ValueError(f"{path} lacks {missing}")
    re.compile(m["grid_name_pattern"])
    for key, entry in m["datasets"].items():
        if not entry.get("names") or not all(isinstance(n, str) and n.strip() for n in entry["names"]):
            raise ValueError(f"{path}: {key} needs a list of names")
        if not entry.get("unit"):
            raise ValueError(f"{path}: {key} needs the unit of its factor")
    return m


DATABASE_MAP = load_database_map()
PROCESSES = {k: list(v["names"]) for k, v in DATABASE_MAP["datasets"].items()}
LOCATION_PREFERENCE = list(DATABASE_MAP["location_preference"])
GRID_PATTERN = re.compile(DATABASE_MAP["grid_name_pattern"])


def use_database_map(name):
    """Switch to the map of another database. The names above change in place, so every module that
    imported them sees the new ones."""
    global GRID_PATTERN
    m = load_database_map(name)
    DATABASE_MAP.clear()
    DATABASE_MAP.update(m)
    PROCESSES.clear()
    PROCESSES.update({k: list(v["names"]) for k, v in m["datasets"].items()})
    LOCATION_PREFERENCE[:] = m["location_preference"]
    GRID_PATTERN = re.compile(m["grid_name_pattern"])
    return m


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
    try:                              # the product system is removed again whatever openLCA answers
        result = client.calculate(setup)
        try:
            result.wait_until_ready()
            impacts = {i.impact_category.name: float(i.amount) for i in result.get_total_impacts()}
        finally:
            result.dispose()
    finally:
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
    try:
        result = client.simulate(setup)
    except Exception:
        client.delete(system)         # nothing of this run stays in the database
        raise
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
    """How every report credits the database: the text of its map, when the map is of this database."""
    if database == DATABASE_MAP["database"]:
        return DATABASE_MAP["citation"]
    year = re.search(r"20\d\d", database or "")
    return ("Life Cycle Inventory database of the Swiss Federal Administration, BAFU:"
            + (year.group(0) if year else "20XY"))


def grid_processes(descs):
    """{electricity_mv_<country code>: [name]} for every process the database names as a national grid."""
    out = {}
    for d in descs:
        mm = GRID_PATTERN.match((d.name or "").strip())
        if mm:
            out.setdefault(f"electricity_mv_{mm.group(1)}", [d.name])
    return out


def extract(client, path, method="EF 3.1", database="bafu2026", all_grids=True, keys=None,
            update=False, progress=print, keep_chosen=True):
    """Extract factors into the JSON file at path. Returns the saved dict.

    progress(done, total, message) is called after every dataset when it accepts three
    arguments; a one argument callable (print) receives the message only.
    keep_chosen: read again the processes that people chose by name (keys "proc:...") and that the
    file already holds, so that a full extraction does not lose them."""
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
        elif keep_chosen:
            chosen = [k for k in old if k.startswith("proc:")]
    procs = dict(PROCESSES)
    if all_grids:
        for key, names in grid_processes(descs).items():
            procs.setdefault(key, names)
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

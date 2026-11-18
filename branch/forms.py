"""What the person types in the page, turned into what the engine reads. No page here, only rules.

The lists the page offers (regions, materials, example products), the two tables of a product (bill
of materials, other inputs from the database) checked and turned into a product description, and
the sentences that say what is wrong with an entry.
"""
import os
import re

from . import catalogue as cat
from .regions import list_regions, load_region
from .spec import BENCHMARK_DIR, load_spec, parse_process_key, process_key

COLUMNS = ["component", "material", "mass (g)"]
INPUT_COLUMNS = ["what it is for", "stage", "openLCA process (exact name)", "smallest amount", "largest amount"]


# ------------------------------------------------------------------ data


def available_regions(factors=None):
    """[(label, code)]: every country first, alphabetically, each followed by its subregions
    ("Brazil > Amazonas (Manaus)"), then the multi country grids ("Region: Europe").

    Sources: the region files in data/regions/ and every electricity mix extracted from openLCA
    (keys electricity_mv_<code>), labelled with the location name openLCA gives it."""
    entries = {}                                   # code -> (country label, path below it)
    groups = []
    for code in list_regions():
        try:
            r = load_region(code)
        except ValueError:
            continue
        if r.chain[0].get("group"):                # a set of countries, listed with the grids
            groups.append((f"Region: {r.name}", code))
            continue
        names = [x["name"] for x in reversed(r.chain) if x["code"] != "GLO" and not x.get("group")]
        if names:
            entries[code] = (names[0], names[1:])
    grids = {k[len("electricity_mv_"):]: (f or {}) for k, f in
             ((factors or {}).get("factors") or {}).items() if k.startswith("electricity_mv_")}
    country_name = {c: (f.get("location") or c) for c, f in grids.items() if re.fullmatch(r"[A-Z]{2}", c)}
    country_name.update({c: e[0] for c, e in entries.items() if re.fullmatch(r"[A-Z]{2}", c) and not e[1]})
    regions = list(groups)
    for code, f in grids.items():
        if code in entries:
            continue
        loc = f.get("location") or code
        if re.fullmatch(r"[A-Z]{2}", code):
            entries[code] = (loc, [])
        elif re.fullmatch(r"[A-Z]{2}-.+", code) and code[:2] in country_name:
            parent = country_name[code[:2]]
            sub = loc.split(", ", 1)[1] if loc.startswith(parent + ", ") else loc
            entries[code] = (parent, [sub])
        else:                                      # grids that span several countries
            regions.append((f"Region: {loc}", code))
    out = sorted(((" > ".join([c] + sub), code) for code, (c, sub) in entries.items()),
                 key=lambda x: (x[0].split(" > ")[0].lower(), x[0].count(" > "), x[0].lower()))
    return out + sorted(regions, key=lambda x: x[0].lower())


def materials(factors=None):
    """{id: label}. With a factor file, only the materials whose factors are all in it."""
    if factors is None:
        return {k: v["label"] for k, v in cat.load_materials().items()}
    return {k: v["label"] for k, v in cat.split_by_factors(factors)[0].items()}


def materials_waiting(factors):
    """Labels of the materials in the catalogue whose factors are not in the file yet."""
    return sorted(v["label"] for v in cat.split_by_factors(factors)[1].values()) if factors else []


def templates():
    """{label: benchmark name} of the product files shipped in data/benchmark/."""
    out = {}
    for f in sorted(os.listdir(BENCHMARK_DIR)):
        if f.endswith(".json"):
            out[load_spec(f[:-5])["name"]] = f[:-5]
    return out


def template_fields(name):
    """(product name, volume in litres, refillable, rows) to prefill the form.
    Masses are the typical value of the template's range; the user edits them."""
    spec = load_spec(templates()[name])
    rows = []
    for c in spec["components"]:
        if "mass_g" in c:
            m = c["mass_g"]
        else:
            dist, params, _ = c["mass_prior"][:3]
            m = params.get("mode", params.get("mean", (params.get("low", 0) + params.get("high", 0)) / 2))
        rows.append([c["id"].replace("_", " "), c["material"], float(m)])
    return spec["name"], float(spec["volume_l"]), bool(spec["refillable"]), rows


def _rows(table):
    if table is None:
        return []
    if hasattr(table, "values") and hasattr(table, "columns"):     # pandas DataFrame
        table = table.values.tolist()
    return [r for r in table if any(str(x).strip() not in ("", "nan", "None") for x in r)]


STAGE_WORDS = {"material": "material", "materials": "material", "raw material": "material",
               "manufacturing": "manufacturing", "production": "manufacturing", "making": "manufacturing",
               "transport": "transport", "distribution": "transport", "use": "use", "use phase": "use",
               "end of life": "end_of_life", "end_of_life": "end_of_life", "disposal": "end_of_life",
               "waste": "end_of_life", "other": "other", "": "other"}


def _number(text):
    return float(str(text).strip().replace(",", "."))


def inputs_from_table(name, table):
    """Rows of the "other inputs" table -> builder "exchanges". One row per input:
    what it is for, stage, openLCA process (exact name, " @CH" for a location), smallest and
    largest amount. The same number twice (or only one of the two) is a known amount."""
    out = []
    for i, r in enumerate(_rows(table), 1):
        r = list(r) + [""] * (len(INPUT_COLUMNS) - len(r))
        blank = lambda x: str(x).strip() in ("", "nan", "None")  # noqa: E731
        what = "" if blank(r[0]) else str(r[0]).strip()
        proc = "" if blank(r[2]) else str(r[2]).strip()
        if not proc:
            raise ValueError(f"{name}, input {i}: write the name of the openLCA process (use the search below).")
        stage = STAGE_WORDS.get("" if blank(r[1]) else str(r[1]).strip().lower())
        if stage is None:
            raise ValueError(f"{name}, input {i}: the stage must be one of material, manufacturing, transport, "
                             "use, end of life or other.")
        try:
            lo = None if blank(r[3]) else _number(r[3])
            hi = None if blank(r[4]) else _number(r[4])
        except ValueError:
            raise ValueError(f"{name}, input {i}: the amounts of {what or proc} must be numbers.") from None
        if lo is None and hi is None:
            raise ValueError(f"{name}, input {i}: give the amount of {what or proc}, or the smallest and the "
                             "largest it could be if you do not know it.")
        lo, hi = (hi if lo is None else lo), (lo if hi is None else hi)
        if lo < 0 or hi < 0:
            raise ValueError(f"{name}, input {i}: amounts cannot be negative.")
        if lo > hi:
            raise ValueError(f"{name}, input {i}: the smallest amount is larger than the largest one.")
        pname, _, location = proc.partition(" @")
        out.append({"id": what or f"input {i}", "stage": stage, "process": pname.strip(),
                    "location": location.strip() or None, "key": process_key(pname, location),
                    "amount": lo if lo == hi else [lo, hi]})
    return out


def spec_from_fields(name, volume_l, refillable, table, used_ids=(), inputs=None, units=1.0, service=None):
    """Product description (builder format) from the form. Errors are plain sentences.

    inputs: rows of the "other inputs" table (any process of the database); with them the
    bill of materials may be empty, which is how a product that is not a container is described.
    units: how many of this product deliver the same service as the other one.
    service: what both products do (the functional unit), in the person's words."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Give each product a name.")
    volume_l = _positive(volume_l, f"{name}: the volume must be a number of litres.",
                         f"{name}: the volume must be larger than zero.")
    comps = _components(name, table)
    exchanges = inputs_from_table(name, inputs)
    if not comps and not exchanges:
        raise ValueError(f"{name}: add at least one component to the bill of materials, or one input from "
                         "the openLCA database.")
    units = _positive(1.0 if units in (None, "") else units,
                      f"{name}: how many are needed for the same use must be a number.",
                      f"{name}: how many are needed for the same use must be larger than zero.")
    pid = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "product"
    while pid in used_ids:
        pid += "_b"
    spec = {"id": pid, "name": name, "volume_l": volume_l, "refillable": bool(refillable) and bool(comps),
            "components": comps, "exchanges": exchanges, "units_per_functional_unit": units}
    if service and str(service).strip():
        spec["functional_unit"] = str(service).strip()
    return load_spec(spec)


def _positive(value, not_a_number, not_positive):
    """A number larger than zero, or the sentence that says what is wrong."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(not_a_number) from None
    if value <= 0:
        raise ValueError(not_positive)
    return value


def _components(name, table):
    """The rows of the bill of materials as components: part, material, mass in grams."""
    mats = materials()
    by_label = {v.lower(): k for k, v in mats.items()}
    comps, seen = [], set()
    for i, r in enumerate(_rows(table), 1):
        comp = str(r[0]).strip() or f"part {i}"
        mat = str(r[1]).strip().lower()
        mat = mat if mat in mats else by_label.get(mat)
        if mat is None:
            raise ValueError(f"{name}, line {i}: unknown material {r[1]!r}. Use one of: "
                             + ", ".join(sorted(mats)) + ".")
        mass = _positive(str(r[2]).replace(",", "."), f"{name}, line {i}: the mass of {comp} must be a number of grams.",
                         f"{name}, line {i}: the mass of {comp} must be larger than zero.")
        cid = re.sub(r"[^a-z0-9]+", "_", comp.lower()).strip("_") or f"part_{i}"
        while cid in seen:
            cid += "_2"
        seen.add(cid)
        comps.append({"id": cid, "material": mat, "mass_g": mass})
    return comps


def missing_process_keys(specs, factors):
    """Keys of the processes chosen by name whose factors are not in the factor file yet."""
    have = (factors or {}).get("factors") or {}
    return sorted({e["key"] for spec in specs for e in spec.get("exchanges") or [] if e["key"] not in have})


def explain_unresolved(bad):
    """Plain words for the processes BRANCH could not read (connector.read_process_factors)."""
    parts = []
    for key, why in sorted(bad.items()):
        name = (parse_process_key(key) or (key, None))[0]
        if not why:
            parts.append(f'no process of the open database is called exactly "{name}"')
        elif str(why[0]).startswith("calculation failed"):
            parts.append(f'openLCA could not calculate "{name}" ({why[0]})')
        else:
            parts.append(f'several processes are called "{name}"; add the location after the name, one of: '
                         + ", ".join(f'"{name} @{w.rsplit("[", 1)[-1].rstrip("]")}"' for w in why))
    return "; ".join(parts) + ". Use the search to copy the exact name."


def search_text(results):
    """Markdown for the result of connector.search_processes."""
    if not results:
        return "No process of the open database has all these words in its name. Try fewer or other words."
    lines = ["| openLCA process (copy this name) | location | amounts in |", "|---|---|---|"]
    names = [r["name"] for r in results]
    for r in results:
        name = r["name"] + (f" @{r['location']}" if names.count(r["name"]) > 1 and r["location"] else "")
        lines.append(f"| {name} | {r['location'] or ''} | {r['unit'] or ''} |")
    return "\n".join(lines)

"""Web app for non-experts: bill of materials in, questions one by one, report out.

The logic functions below have no Gradio dependency (and are tested); build_ui
wires them to a Gradio page. Run with `python app.py`.

Factors: the server reads them from the path in BRANCH_FACTORS (a file made
by experiments/openlca/extract_factors.py). They stay on the server: the page never
offers them for download, it only shows results. Without that file the app
refuses to start a comparison, unless BRANCH_DEMO=1, which uses illustrative
numbers and says so on every screen and report.
"""
import os
import re
import tempfile

import numpy as np

from . import __version__, connector
from . import catalogue as cat
from . import help as qhelp
from .agent import ISO_PUBLIC_NOTICE, Session
from .builder import build_model, load_spec
from .demo_factors import demo_factors
from .factors import load_factors
from .indicators import available, describe
from .manager_report import manager_pdf
from .regions import list_regions, load_region
from .report import markdown_report
from .spec import BENCHMARK_DIR, parse_process_key, process_key

COLUMNS = ["component", "material", "mass (g)"]
INPUT_COLUMNS = ["what it is for", "stage", "openLCA process (exact name)", "smallest amount", "largest amount"]


# ------------------------------------------------------------------ data

def load_server_factors():
    """(factors, is_demo). Raises a clear error when nothing is configured."""
    if os.environ.get("BRANCH_DEMO") == "1":
        return demo_factors(), True
    path = os.environ.get("BRANCH_FACTORS")
    if path and os.path.exists(path):
        return load_factors(path), False
    try:                                   # newest file made by extract_factors.py
        return load_factors(), False
    except FileNotFoundError:
        pass
    raise RuntimeError("No impact factors configured on this server. Set BRANCH_FACTORS to the file made "
                       "by experiments/openlca/extract_factors.py (or BRANCH_DEMO=1 for illustrative numbers).")


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
    try:
        volume_l = float(volume_l)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: the volume must be a number of litres.") from None
    if volume_l <= 0:
        raise ValueError(f"{name}: the volume must be larger than zero.")
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
        try:
            mass = float(str(r[2]).replace(",", "."))
        except (TypeError, ValueError):
            raise ValueError(f"{name}, line {i}: the mass of {comp} must be a number of grams.") from None
        if mass <= 0:
            raise ValueError(f"{name}, line {i}: the mass of {comp} must be larger than zero.")
        cid = re.sub(r"[^a-z0-9]+", "_", comp.lower()).strip("_") or f"part_{i}"
        while cid in seen:
            cid += "_2"
        seen.add(cid)
        comps.append({"id": cid, "material": mat, "mass_g": mass})
    exchanges = inputs_from_table(name, inputs)
    if not comps and not exchanges:
        raise ValueError(f"{name}: add at least one component to the bill of materials, or one input from "
                         "the openLCA database.")
    try:
        units = 1.0 if units in (None, "") else float(units)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: how many are needed for the same use must be a number.") from None
    if units <= 0:
        raise ValueError(f"{name}: how many are needed for the same use must be larger than zero.")
    pid = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "product"
    while pid in used_ids:
        pid += "_b"
    spec = {"id": pid, "name": name, "volume_l": volume_l, "refillable": bool(refillable) and bool(comps),
            "components": comps, "exchanges": exchanges, "units_per_functional_unit": units}
    if service and str(service).strip():
        spec["functional_unit"] = str(service).strip()
    return load_spec(spec)


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


# --------------------------------------------------------------- session

# Certificate and questions per round chosen from the benchmark (re-run on 13 Nov 2026 with
# the national priors): with tau = 2.5% and 3 questions per round, 2.2% of certified verdicts
# are wrong under tail experts on new seeds 1000 to 1029 (4.3% with 2 per round) and at most
# 0.7% under prior experts, for about half a question more than 2 per round.
TAU = 0.025
BATCH = 3

# When the person does not know the answers, the agent keeps asking until nothing is left:
# "I don't know" keeps the prior and settles nothing. After this many skips in a row the app
# says so and points to "Finish now", which closes the session on the defaults and lets the
# report say how sure BRANCH is and what would settle the comparison.
UNKNOWN_STREAK_HINT = 2
UNKNOWN_HINT = ("**You have skipped two questions in a row.** Skipped questions keep BRANCH's defaults, so they "
                "do not settle the comparison. If the next questions are also beyond what you know, press "
                "**Finish now**: the report will say how sure BRANCH is and which answers would settle it. "
                "Or ask a colleague or your supplier and come back.")


def start_session(region, spec_a, spec_b, factors, public=False, n_samples=20_000, seed=0,
                  category="Climate change", system_model="cut-off", tau=TAU, batch_size=BATCH):
    """category: the indicator the questions aim to settle; the reports show all of them."""
    if spec_a["name"] == spec_b["name"]:
        raise ValueError("The two products need different names.")
    model = build_model(spec_a, spec_b, region, category, factors, system_model=system_model)
    s = Session(model, n_samples=n_samples, seed=seed, public_comparison=public, tau=tau,
                batch_size=batch_size)
    s.public = public
    s.unknown_streak = 0
    return s


def record_answer(s, name, value):
    """Pass the answer to the session and count the skips in a row.

    Returns True when the person has skipped UNKNOWN_STREAK_HINT questions in a
    row, which is when the app suggests "Finish now".
    """
    s.answer(name, value)
    s.unknown_streak = getattr(s, "unknown_streak", 0) + 1 if value is None else 0
    return s.unknown_streak >= UNKNOWN_STREAK_HINT


def status_text(s):
    m = s.model
    p = s.p_a_lower()
    lower = m.label_a if p >= 0.5 else m.label_b
    sure = max(p, 1 - p) * 100
    sure_txt = "more than 99%" if sure > 99 else f"{sure:.0f}%"
    return (f"So far: **{lower}** looks lower, with **{sure_txt}** confidence "
            f"(BRANCH stops when it reaches {qhelp.fmt_pct(1 - s.tau)}). Questions so far: {len(s.asked)}.")


def question_view(s):
    """What to show next: {"done": bool, "name", "text", "kind", "options" | "range", "default"}."""
    name = s.next_question()
    if name is None:
        return {"done": True}
    c = s.model.by_name[name]
    pct = qhelp.is_percent(name)
    text = c.question or name
    why, where = qhelp.help_for(name) or ("", "")
    view = {"done": False, "name": name, "text": qhelp.percent_question(text) if pct else text,
            "kind": c.kind, "why": why, "where": where, "percent": pct,
            "source": c.source.split(":", 1)[-1].strip(),
            "default_kind": "published source" if c.source.startswith("SOURCE") else "assumption"}
    if c.kind == "categorical":
        view["options"] = c.labels
        view["default"] = c.labels[int(np.argmax(c.probs))]
    else:
        k = 100.0 if pct else 1.0
        lo, hi = c._frozen().ppf([0.05, 0.95])
        view["range"] = (k * float(lo), k * float(hi))
        view["default"] = k * float(c._frozen().ppf(0.5))
    return view


def parse_answer(s, name, raw):
    """Engine number for a form answer, or None for "I don't know"."""
    c = s.model.by_name[name]
    if raw is None or str(raw).strip() in ("", "?"):
        return None
    if c.kind == "categorical":
        if raw not in c.labels:
            raise ValueError("Choose one of the options.")
        return float(c.labels.index(raw))
    pct = qhelp.is_percent(name)
    try:
        v = float(str(raw).strip().rstrip("%").strip().replace(",", "."))
    except ValueError:
        raise ValueError("Type a number.") from None
    k = 100.0 if pct else 1.0
    a, b = c._frozen().support()
    if not (k * a <= v <= k * b):
        u = "%" if pct else ""
        raise ValueError(f"{v:g}{u} is outside what is possible here ({k * a:g}{u} to {k * b:g}{u}).")
    return v / k


def finish(s, outdir=None):
    """(markdown summary, path of the manager PDF, path of the technical markdown)."""
    r = s.result()
    outdir = outdir or tempfile.mkdtemp(prefix="branch_")
    pdf = os.path.join(outdir, "BRANCH_report.pdf")
    manager_pdf(r, s.model, pdf, public=getattr(s, "public", False))
    md = os.path.join(outdir, "BRANCH_technical_report.md")
    with open(md, "w") as fh:
        fh.write(markdown_report(r, s.model))
    m = s.model
    (ma, _, _), (mb, _, _) = r["impacts"][m.label_a], r["impacts"][m.label_b]
    low, high = (m.label_a, m.label_b) if r["verdict_a_lower"] else (m.label_b, m.label_a)
    pct = abs(ma - mb) / max(ma, mb) * 100 if max(ma, mb) else 0
    sure = (1 - r["p_flip"]) * 100
    head = (f"### {low} has the lower climate impact, about {pct:.0f}% less than {high}."
            if r["certified"] else
            f"### Not settled yet: {low} looks lower, but BRANCH is only {sure:.0f}% confident.")
    summary = (f"{head}\n\nConfidence: {'more than 99%' if sure > 99 else f'{sure:.0f}%'}. "
               f"Questions asked: {r['questions']}. The PDF explains where the impact comes from, "
               f"how much disposal weighs and what would change the answer.\n\n"
               f"> {ISO_PUBLIC_NOTICE if getattr(s, 'public', False) else 'Before any public claim, read the ISO 14044 notice in the report.'}")
    return summary, pdf, md


# -------------------------------------------------------------------- UI

def build_ui():
    import gradio as gr

    try:
        server_factors, demo = load_server_factors()
        factors_error = None
        cats = available(server_factors) or ["Climate change"]
    except RuntimeError as exc:
        server_factors, demo, factors_error, cats = None, False, str(exc), ["Climate change"]
    cat_choices = [(describe(c)[0], c) for c in cats]
    tmpl = templates()
    regions = available_regions(server_factors)
    mats = materials(server_factors)
    waiting = materials_waiting(server_factors)
    names = list(tmpl)

    with gr.Blocks(title="BRANCH: compare two products", analytics_enabled=False) as ui:
        gr.Markdown("# BRANCH for openLCA\nCompare two products from their bill of materials, or from processes "
                    "of the openLCA database. BRANCH fills in what you do not know, asks only the questions that "
                    "can change the answer, and gives you a report you can share. Free and open source. "
                    f"Version {__version__}. An independent project, not affiliated with or endorsed by GreenDelta, "
                    "the developer of openLCA.")
        if demo:
            gr.Markdown("**ILLUSTRATIVE NUMBERS.** This server runs on demo values, not real inventory "
                        "data. Do not use the results for decisions or claims.")
        if factors_error:
            gr.Markdown("**Not ready yet:** BRANCH needs the impact factors of your openLCA database. "
                        "Open the **openLCA connection** panel below and press **Read factors from openLCA** "
                        "(once, about 15 minutes).")
        state = gr.State(None)

        ok0, msg0 = connector.status()
        with gr.Accordion("openLCA connection", open=bool(factors_error) or not ok0):
            have = server_factors is not None and not demo     # demo numbers are not the user's factors
            olca_msg = gr.Markdown(msg0 + "\n\n" + connector.checklist_markdown(factors=have)
                                   + ("" if factors_error else
                                      f"\n\nFactors in use: `{os.path.basename(server_factors.get('path', 'demo'))}`."
                                      if server_factors else ""))
            with gr.Row():
                check_btn = gr.Button("Check again")
                read_btn = gr.Button("Read factors from openLCA (once, about 15 minutes)")
            read_msg = gr.Markdown()

        with gr.Column(visible=True) as setup:
            region = gr.Dropdown(choices=regions, value="PT" if any(c == "PT" for _, c in regions)
                                 else regions[0][1], label="Where is it produced and sold? (type a country to search)")
            gr.Markdown("Materials: " + ", ".join(f"`{k}` ({v})" for k, v in sorted(mats.items()))
                        + ("" if not waiting or demo else
                           "\n\nAlso in the catalogue, once you press **Read factors from openLCA** again: "
                           + ", ".join(waiting) + "."))
            forms = []
            for side, default in (("A", names[0]), ("B", names[1] if len(names) > 1 else names[0])):
                with gr.Group():
                    gr.Markdown(f"### Product {side}")
                    with gr.Row():
                        tpl = gr.Dropdown(choices=names, value=default, label="Start from an example")
                        n0, v0, r0, rows0 = template_fields(default)
                        name = gr.Textbox(value=n0, label="Name")
                        vol = gr.Number(value=v0, label="Content of one container (litres)")
                        refill = gr.Checkbox(value=r0, label="Refillable (washed and filled again)")
                    table = gr.Dataframe(value=rows0, headers=COLUMNS, datatype=["str", "str", "number"],
                                         label="Bill of materials (one line per part)", interactive=True,
                                         row_count=len(rows0), column_count=3)
                    units = gr.Number(value=1, label="How many are needed for the same use? (1, unless the "
                                                     "two products do not last or hold the same)")
                    with gr.Accordion("Other inputs from the openLCA database (for any product, not only containers)",
                                      open=False):
                        gr.Markdown("One line per input: what it is for, the stage (material, manufacturing, "
                                    "transport, use, end of life), the exact name of the openLCA process (use the "
                                    "search below) and the amount for one product, in the unit the search shows. "
                                    "If you do not know the amount, give the smallest and the largest it could be: "
                                    "BRANCH asks you for the exact value only if it can change the answer. "
                                    "For a product that is not a container, empty the bill of materials above.")
                        inputs = gr.Dataframe(value=[["", "", "", None, None]], headers=INPUT_COLUMNS,
                                              datatype=["str", "str", "str", "number", "number"],
                                              label="Inputs (one line per input)", interactive=True,
                                              row_count=1, column_count=len(INPUT_COLUMNS))
                    tpl.change(lambda t: template_fields(t), tpl, [name, vol, refill, table])
                    forms.append((name, vol, refill, table, units, inputs))
            service = gr.Textbox(value="", label="What do both products do? (optional, for products that are not "
                                                 "containers, for example: one T-shirt worn for two years)")
            with gr.Accordion("Search the openLCA database (any material, energy, transport or disposal process)",
                              open=False):
                with gr.Row():
                    find_text = gr.Textbox(label="Words in the name of the process, for example: cotton textile")
                    find_btn = gr.Button("Search")
                find_out = gr.Markdown()
            main_cat = gr.Dropdown(choices=cat_choices, value="Climate change" if "Climate change" in cats else cats[0],
                                   label="Which indicator matters most to you? (the report shows all of them)")
            rules = [("Cut-off (recycled content approach, 100:0)", "cut-off")]
            if cat.load_cff():
                rules.append(("EU Circular Footprint Formula (PEF)", "cff"))
            rule = gr.Radio(choices=rules, value="cut-off", label="How to count recycling")
            public = gr.Checkbox(value=False, label="I may use this comparison in public (marketing, labels)")
            go = gr.Button("Compare", variant="primary")
            setup_msg = gr.Markdown()

        with gr.Column(visible=False) as asking:
            status = gr.Markdown()
            q_text = gr.Markdown()
            q_choice = gr.Radio(choices=[], label="Your answer", visible=False)
            q_number = gr.Number(label="Your answer", visible=False)
            with gr.Row():
                ok = gr.Button("Answer", variant="primary")
                dunno = gr.Button("I don't know (keep the default)")
                stop = gr.Button("Finish now (keep all the defaults)")
            q_msg = gr.Markdown()
            q_name = gr.State(None)

        with gr.Column(visible=False) as done:
            summary = gr.Markdown()
            files = gr.File(label="Reports", file_count="multiple")
            with gr.Row():
                send_btn = gr.Button("Send to openLCA")
                again = gr.Button("New comparison")
            backup_ok = gr.Checkbox(label="The database open in openLCA is a copy, or I have a backup of it", value=False)
            send_msg = gr.Markdown()

        def show(s):
            v = question_view(s)
            if v["done"]:
                text, pdf, md = finish(s)
                return (s, gr.Column(visible=False), gr.Column(visible=True), "", "",
                        gr.Radio(visible=False), gr.Number(visible=False), None, text, [pdf, md], "")
            hint = ""
            if v["why"]:
                hint += f"\n\n**Why it matters:** {v['why']}\n\n**Where to find it:** {v['where']}"
            hint += (f"\n\n<small>If you do not know, BRANCH keeps its default ({v['default_kind']}: {v['source']}). "
                     f"You can also finish now: the report then says how sure BRANCH is and what would settle it.</small>")
            if v["kind"] == "categorical":
                radio = gr.Radio(choices=v["options"], value=None, visible=True)
                number = gr.Number(visible=False, value=None)
            else:
                lo, hi = v["range"]
                radio = gr.Radio(visible=False, choices=[])
                number = gr.Number(visible=True, value=None, label=f"Your answer{' in %' if v['percent'] else ''} (typical: {lo:.3g} to {hi:.3g})")
            return (s, gr.Column(visible=True), gr.Column(visible=False), status_text(s),
                    f"### {v['text']}{hint}", radio, number, v["name"], "", None, "")

        outs = [state, asking, done, status, q_text, q_choice, q_number, q_name, summary, files, q_msg]

        def on_find(text):
            if demo:
                return "The search needs openLCA and real factors: this page runs on demo numbers."
            ready, msg = connector.status()
            if not ready:
                return msg
            try:
                return search_text(connector.search_processes(text))
            except Exception as exc:
                return f"**The search stopped:** {exc}"

        find_btn.click(on_find, find_text, find_out)

        def on_start(reg, na, va, ra, ta, ua, ia, nb, vb, rb, tb, ub, ib, serv, main, rul, pub,
                     progress=gr.Progress()):
            try:
                factors, is_demo = load_server_factors()
                a = spec_from_fields(na, va, ra, ta, inputs=ia, units=ua, service=serv)
                b = spec_from_fields(nb, vb, rb, tb, used_ids={a["id"]}, inputs=ib, units=ub, service=serv)
                todo = missing_process_keys((a, b), factors)
                if todo:
                    if is_demo:
                        raise ValueError("inputs from the openLCA database need real factors: this page runs on "
                                         "demo numbers.")
                    ready, msg = connector.status()
                    if not ready:
                        raise ValueError("BRANCH has to read the factors of the processes you chose, and openLCA "
                                         "is not connected. " + msg)
                    _, bad = connector.read_process_factors(
                        todo, factors.get("path"),
                        progress=lambda i, n, m: progress(i / max(n, 1), desc=f"{i}/{n} {m[:60]}"))
                    if bad:
                        raise ValueError(explain_unresolved(bad))
                    factors, is_demo = load_server_factors()
                ready = cat.split_by_factors(factors)[0]
                for spec in (a, b):
                    for comp in spec["components"]:
                        if comp["material"] not in ready:
                            label = cat.load_materials()[comp["material"]]["label"]
                            raise ValueError(f"the factors of {label} are not in your factor file yet. Open the "
                                             "openLCA connection panel and press Read factors from openLCA again.")
                s = start_session(reg, a, b, factors, public=pub, category=main, system_model=rul)
                s.demo = is_demo
            except (ValueError, RuntimeError) as exc:
                return (gr.Column(visible=True), f"**Please check:** {exc}") + tuple(gr.skip() for _ in outs)
            return (gr.Column(visible=False), "") + show(s)

        go.click(on_start, [region, *forms[0], *forms[1], service, main_cat, rule, public], [setup, setup_msg, *outs])

        def on_answer(s, name, choice, number, unknown):
            if s is None or name is None:
                return tuple(gr.skip() for _ in outs)
            try:
                value = None if unknown else parse_answer(s, name, choice if s.model.by_name[name].kind ==
                                                          "categorical" else number)
                if value is None and not unknown:
                    raise ValueError("Give an answer, or press \"I don't know\".")
            except ValueError as exc:
                return tuple(gr.skip() for _ in outs[:-1]) + (f"**{exc}**",)
            suggest_finish = record_answer(s, name, value)
            out = show(s)
            if suggest_finish and not s.done:
                out = out[:-1] + (UNKNOWN_HINT,)
            return out

        def on_finish(s):
            if s is None:
                return tuple(gr.skip() for _ in outs)
            s.finish_early()
            return show(s)

        ok.click(lambda s, n, c, x: on_answer(s, n, c, x, False), [state, q_name, q_choice, q_number], outs,
                 api_name="answer")
        dunno.click(lambda s, n, c, x: on_answer(s, n, c, x, True), [state, q_name, q_choice, q_number], outs,
                    api_name="skip")
        stop.click(on_finish, [state], outs)
        again.click(lambda: (gr.Column(visible=True), gr.Column(visible=False), None, ""), None,
                    [setup, done, state, send_msg])

        def on_check():
            try:
                f, is_demo = load_server_factors()
                have_now = f is not None and not is_demo
            except RuntimeError:
                have_now = False
            return connector.status()[1] + "\n\n" + connector.checklist_markdown(factors=have_now)

        def on_read(progress=gr.Progress()):
            ready, msg = connector.status()
            if not ready:
                return msg, "", gr.skip(), gr.skip()
            try:
                _, summary = connector.read_factors(
                    progress=lambda i, n, m: progress(i / max(n, 1), desc=f"{i}/{n} {m[:60]}"))
            except Exception as exc:
                return msg, f"**Reading stopped:** {exc}", gr.skip(), gr.skip()
            factors, _ = load_server_factors()
            regs = available_regions(factors)
            cats_now = available(factors) or ["Climate change"]
            return (msg, summary + " You can compare now.",
                    gr.Dropdown(choices=regs, value="PT" if any(c == "PT" for _, c in regs) else regs[0][1]),
                    gr.Dropdown(choices=[(describe(c)[0], c) for c in cats_now], value="Climate change"
                                if "Climate change" in cats_now else cats_now[0]))

        def on_send(s, backup_ok=False):
            if s is None:
                return "Run a comparison first."
            if getattr(s, "demo", False):
                return "This server runs on demo numbers: there is nothing real to send to openLCA."
            ready, msg = connector.status()
            if not ready:
                return msg
            try:
                return connector.send(s.model, s.result(), backup_confirmed=bool(backup_ok))
            except Exception as exc:
                return f"**openLCA did not accept it:** {exc}"

        check_btn.click(on_check, None, olca_msg)
        read_btn.click(on_read, None, [olca_msg, read_msg, region, main_cat])
        send_btn.click(on_send, [state, backup_ok], send_msg)
    return ui

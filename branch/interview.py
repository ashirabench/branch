"""One comparison from the first form to the reports, with no page in it.

The page (webapp.py) only shows what these functions return, so everything a person can do in the
page can be tested, and done from a script, without a browser: prepare a comparison from the two
forms, see the next question, answer or skip it, finish, read the factors, send the model to openLCA.

Factors: the server reads them from the path in BRANCH_FACTORS (a file made by
experiments/openlca/extract_factors.py) or from the newest file it finds. They stay on the server:
the page never offers them for download, it only shows results. Without a file no comparison
starts, unless BRANCH_DEMO=1, which uses illustrative numbers and says so on every screen and report.
"""
import os
import tempfile

import numpy as np

from . import catalogue as cat
from . import connector
from . import help as qhelp
from .agent import BATCH, ISO_PUBLIC_NOTICE, TAU, Session
from .builder import build_model
from .demo_factors import demo_factors
from .factors import load_factors
from .forms import available_regions, explain_unresolved, missing_process_keys, search_text, spec_from_fields
from .indicators import available, describe
from .manager_report import manager_pdf
from .report import markdown_report

DEFAULT_CATEGORY = "Climate change"
PRIVATE_NOTICE = "Before any public claim, read the ISO 14044 notice in the report."


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
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(markdown_report(r, s.model))
    m = s.model
    (ma, _, _), (mb, _, _) = r["impacts"][m.label_a], r["impacts"][m.label_b]
    low, high = (m.label_a, m.label_b) if r["verdict_a_lower"] else (m.label_b, m.label_a)
    pct = abs(ma - mb) / max(ma, mb) * 100 if max(ma, mb) else 0
    sure = (1 - r["p_flip"]) * 100
    indicator = describe(m.meta.get("category", "Climate change"))[0].lower()
    head = (f"### {low} has the lower impact on {indicator}, about {pct:.0f}% less than {high}."
            if r["certified"] else
            f"### Not settled yet: {low} looks lower, but BRANCH is only {sure:.0f}% confident.")
    summary = (f"{head}\n\nConfidence: {'more than 99%' if sure > 99 else f'{sure:.0f}%'}. "
               f"Questions asked: {r['questions']}. The PDF explains where the impact comes from, "
               f"how much disposal weighs and what would change the answer.\n\n"
               f"> {ISO_PUBLIC_NOTICE if getattr(s, 'public', False) else PRIVATE_NOTICE}")
    return summary, pdf, md

# ---------------------------------------------------------------- what the buttons of the page do

def prepare(region, form_a, form_b, service, category, rule, public, progress=None):
    """A session ready for its first question, from the two product forms.

    form_a, form_b: (name, volume in litres, refillable, bill of materials, units, other inputs).
    Raises ValueError or RuntimeError with a sentence the page can show."""
    factors, is_demo = load_server_factors()
    na, va, ra, ta, ua, ia = form_a
    nb, vb, rb, tb, ub, ib = form_b
    a = spec_from_fields(na, va, ra, ta, inputs=ia, units=ua, service=service)
    b = spec_from_fields(nb, vb, rb, tb, used_ids={a["id"]}, inputs=ib, units=ub, service=service)
    if missing_process_keys((a, b), factors):
        factors, is_demo = _read_chosen_processes((a, b), factors, is_demo, progress)
    _check_materials_have_factors((a, b), factors)
    s = start_session(region, a, b, factors, public=public, category=category, system_model=rule)
    s.demo = is_demo
    return s


def _read_chosen_processes(specs, factors, is_demo, progress):
    """Read from openLCA the factors of the processes the person chose by name; the factors again."""
    if is_demo:
        raise ValueError("inputs from the openLCA database need real factors: this page runs on "
                         "demo numbers.")
    ready, msg = connector.status()
    if not ready:
        raise ValueError("BRANCH has to read the factors of the processes you chose, and openLCA "
                         "is not connected. " + msg)
    _, bad = connector.read_process_factors(missing_process_keys(specs, factors), factors.get("path"),
                                            progress=progress)
    if bad:
        raise ValueError(explain_unresolved(bad))
    return load_server_factors()


def _check_materials_have_factors(specs, factors):
    ready = cat.split_by_factors(factors)[0]
    for spec in specs:
        for comp in spec["components"]:
            if comp["material"] not in ready:
                label = cat.load_materials()[comp["material"]]["label"]
                raise ValueError(f"the factors of {label} are not in your factor file yet. Open the "
                                 "openLCA connection panel and press Read factors from openLCA again.")


def answer(s, name, choice, number, unknown):
    """Record what the person answered to one question. True when it is time to suggest "Finish now"."""
    raw = choice if s.model.by_name[name].kind == "categorical" else number
    value = None if unknown else parse_answer(s, name, raw)
    if value is None and not unknown:
        raise ValueError("Give an answer, or press \"I don't know\".")
    return record_answer(s, name, value)


def question_hint(view):
    """Why the question matters, where to find the answer, and what happens without one."""
    hint = ""
    if view["why"]:
        hint += f"\n\n**Why it matters:** {view['why']}\n\n**Where to find it:** {view['where']}"
    return hint + (f"\n\n<small>If you do not know, BRANCH keeps its default ({view['default_kind']}: {view['source']}). "
                   f"You can also finish now: the report then says how sure BRANCH is and what would settle it.</small>")


def number_label(view):
    lo, hi = view["range"]
    return f"Your answer{' in %' if view['percent'] else ''} (typical: {lo:.3g} to {hi:.3g})"


def search(text, demo):
    """The processes of the open database whose name contains the words, as text for the page."""
    if demo:
        return "The search needs openLCA and real factors: this page runs on demo numbers."
    ready, msg = connector.status()
    if not ready:
        return msg
    try:
        return search_text(connector.search_processes(text))
    except Exception as exc:            # whatever openLCA or the network raises is shown, never hidden
        return f"**The search stopped:** {exc}"


def connection_text():
    """The state of the connection to openLCA and the steps that are still missing."""
    try:
        factors, is_demo = load_server_factors()
        have = factors is not None and not is_demo
    except RuntimeError:
        have = False
    return connector.status()[1] + "\n\n" + connector.checklist_markdown(factors=have)


def read_factors(progress=None):
    """Read the factors from openLCA. (connection text, message, regions, categories); the last two
    are None when nothing was read."""
    ready, msg = connector.status()
    if not ready:
        return msg, "", None, None
    try:
        _, summary = connector.read_factors(progress=progress)
    except Exception as exc:            # shown to the person as it is
        return msg, f"**Reading stopped:** {exc}", None, None
    factors, _ = load_server_factors()
    return msg, summary + " You can compare now.", available_regions(factors), categories(factors)


def categories(factors):
    """[(label, name)] of the impact categories the factor file has."""
    names = (available(factors) if factors else None) or [DEFAULT_CATEGORY]
    return [(describe(c)[0], c) for c in names]


def default_of(choices, wanted):
    """The wanted value when it is among the (label, value) choices, else the first."""
    return wanted if any(value == wanted for _, value in choices) else choices[0][1]


def send(s, backup_ok=False):
    """Send the finished comparison to openLCA; the text the page shows."""
    if s is None:
        return "Run a comparison first."
    if getattr(s, "demo", False):
        return "This server runs on demo numbers: there is nothing real to send to openLCA."
    ready, msg = connector.status()
    if not ready:
        return msg
    try:
        return connector.send(s.model, s.result(), backup_confirmed=bool(backup_ok))
    except Exception as exc:            # shown to the person as it is
        return f"**openLCA did not accept it:** {exc}"

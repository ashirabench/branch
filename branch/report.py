"""Report (Step 7): verdict, its probability of being wrong, and who decided
every modelling choice, where the impact comes from (with end of life shown
on its own), and the smallest single change that reverses the verdict.
Structured after the ISO 14044 reporting items that the agent can fill; the
model itself goes back to openLCA through olca_bridge.push_comparison.
"""
import math

from .help import fmt_pct
from .real_cases import assumptions
from .whatif import indicators, reversals, stages


def _fmt(x):
    return f"{x:.4g}" if isinstance(x, float) else str(x)


def markdown_report(result, model, title="BRANCH comparative LCA", analysis=True):
    """The whole report as Markdown: one function below per section, in the order of the page."""
    meta = getattr(model, "meta", {})
    lines = _verdict(result, title) + _study(meta) + _impacts(result)
    if analysis:
        lines += _stages(model, result) + _reversals(model, result) + _categories(model, result)
    for note in result.get("notices", []):
        lines += [f"> {note}", ""]
    lines += (_choices(model, result) + _sourced_priors(model, result) + _database_uncertainty(model)
              + _placeholders(model) + LIMITS + _data_source(meta))
    return "\n".join(lines) + "\n"


LIMITS = ["", "## Limits", "",
          "- Attributional study, ILCD Situation A.",
          "- Priors are only as good as the regional statistics behind them.",
          "- BRANCH follows ISO 14040 and ISO 14044 and prepares the study for the critical "
          "review required for comparisons disclosed to the public, but it does not replace "
          "the panel of reviewers."]


def _verdict(result, title):
    return [f"# {title}", "",
            f"**Verdict:** {result['verdict']}  ",
            f"**Probability the verdict is wrong:** {result['p_flip']:.1%} "
            f"({'certified' if result['certified'] else 'NOT certified'} at tau = {fmt_pct(result['tau'])})  ",
            f"**Questions asked:** {result['questions']}  ",
            f"**Why the questions stopped:** {result.get('stop_reason') or 'not recorded'}", ""]


def _study(meta):
    """Functional unit, location, impact category."""
    if not meta:
        return []
    containers = any(p.get("components") for p in meta.get("products", []))
    where = (f"Location: {meta.get('country')}." if containers else
             "Location: that of each process chosen from the database (the region does not enter).")
    return [f"Functional unit: {meta.get('functional_unit')}. {where} "
            f"Impact category: {meta.get('category')} ({meta.get('method')}).", ""]


def _impacts(result):
    if not result.get("impacts"):
        return []
    lines = ["| Alternative | Mean | 90% interval |", "|---|---|---|"]
    for name, (mean, lo, hi) in result["impacts"].items():
        lines.append(f"| {name} | {mean:.4g} | {lo:.4g} to {hi:.4g} |")
    return lines + [""]


def _stages(model, result):
    """Where the impact comes from, with end of life on its own line and first."""
    st = stages(model, result)
    names = sorted({k for side in st.values() for k in side}, key=lambda k: (k != "end_of_life", k))
    lines = ["## Where the impact comes from (mean per functional unit)", "",
             "| Stage | " + " | ".join(st) + " |", "|---|" + "---|" * len(st)]
    for k in names:
        label = "**end of life (disposal)**" if k == "end_of_life" else k.replace("_", " ")
        lines.append(f"| {label} | " + " | ".join(_fmt(side.get(k, 0.0)) for side in st.values()) + " |")
    return lines + [""]


def _reversals(model, result):
    rev = reversals(model, result)
    lines = ["## What would reverse the verdict", ""]
    if not rev:
        return lines + ["No change in a single choice, within its plausible range, reverses the verdict.", ""]
    lines += ["Smallest change in a single choice, every other answer kept.", "",
              "| Choice | Now | Verdict reverses at | P(A < B) after |", "|---|---|---|---|"]
    for r in rev:
        lines.append(f"| {r['name']} | {_fmt(r['now'])} | {_fmt(r['reverses_at'])} | {r['p_after']:.0%} |")
    return lines + [""]


def _categories(model, result):
    """Every impact category, with the trade offs marked. Nothing for a model not built by builder.py."""
    if not hasattr(model, "build_args"):
        return []
    rows = indicators(model, result)
    if len(rows) <= 1:
        return []
    lines = ["## All impact categories (mean per functional unit)", "",
             f"| Category | Unit | {model.label_a} | {model.label_b} | Lower | P({model.label_a} lower) |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        flag = "" if r["agrees"] else " (trade off)"
        lines.append(f"| {r['category']} | {r['unit']} | {_fmt(r['mean_a'])} | {_fmt(r['mean_b'])} | "
                     f"{r['lower']}{flag} | {r['p_a_lower']:.0%} |")
    return lines + [""]


def _choices(model, result):
    """Every choice a person could be asked: its value and who decided it."""
    lines = ["## Modelling choices", "", "| Choice | Value | Decided by |", "|---|---|---|"]
    for c in model.choices:
        if not c.askable:
            continue
        if c.name in result["fixed"]:
            val = c.decode(result["fixed"][c.name])
            val = f"{val:.4g}" if isinstance(val, float) else val
        else:
            val = "distribution kept"
        lines.append(f"| {c.name} | {val} | {result['decided_by'][c.name]} |")
    return lines


def _sourced_priors(model, result):
    sourced = [c for c in model.choices if c.source.startswith("SOURCE") and c.name not in result["fixed"]
               and c.askable]
    if not sourced:
        return []
    return (["", "## Priors from published sources (kept as distributions)", ""]
            + [f"- {c.name}: {c.source}" for c in sourced])


def _database_uncertainty(model):
    noise = [c for c in model.choices if not c.askable]
    if not noise:
        return []
    return (["", "## Uncertainty of the database (in every result, never asked)", "",
             "Each dataset varies in the Monte Carlo draws by the uncertainty that the database states for it. "
             "Two products that use the same dataset share its draw.", ""]
            + [f"- {c.name[len('factor.'):] if c.name.startswith('factor.') else c.name}: "
               f"geometric standard deviation {math.exp(c.prior[1]['sigma']):.3g}" for c in noise])


def _placeholders(model):
    pending = assumptions(model)
    if not pending:
        return []
    return (["", "## Placeholder priors (to be replaced by sourced data)", ""]
            + [f"- {n}: {model.by_name[n].source}" for n in pending])


def _data_source(meta):
    if not meta.get("citation"):
        return []
    return ["", "## Data source", "", f"{meta['citation']}. Unit impact factors from {meta.get('factors_file')}."]

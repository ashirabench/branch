"""Report (Step 7): verdict, its probability of being wrong, and who decided
every modelling choice, where the impact comes from (with end of life shown
on its own), and the smallest single change that reverses the verdict.
Structured after the ISO 14044 reporting items that the agent can fill; the
model itself goes back to openLCA through olca_bridge.push_comparison.
"""
from .help import fmt_pct
from .whatif import indicators, reversals, stages


def _fmt(x):
    return f"{x:.4g}" if isinstance(x, float) else str(x)


def markdown_report(result, model, title="BRANCH comparative LCA", analysis=True):
    lines = [f"# {title}", ""]
    lines.append(f"**Verdict:** {result['verdict']}  ")
    lines.append(f"**Probability the verdict is wrong:** {result['p_flip']:.1%} "
                 f"({'certified' if result['certified'] else 'NOT certified'} at tau = {fmt_pct(result['tau'])})  ")
    lines.append(f"**Questions asked:** {result['questions']}")
    lines.append("")
    meta = getattr(model, "meta", {})
    if meta:
        containers = any(p.get("components") for p in meta.get("products", []))
        where = (f"Location: {meta.get('country')}." if containers else
                 "Location: that of each process chosen from the database (the region does not enter).")
        lines.append(f"Functional unit: {meta.get('functional_unit')}. {where} "
                     f"Impact category: {meta.get('category')} ({meta.get('method')}).")
        lines.append("")
    if result.get("impacts"):
        lines += ["| Alternative | Mean | 90% interval |", "|---|---|---|"]
        for name, (mean, lo, hi) in result["impacts"].items():
            lines.append(f"| {name} | {mean:.4g} | {lo:.4g} to {hi:.4g} |")
        lines.append("")
    if analysis:
        st = stages(model, result)
        names = sorted({k for side in st.values() for k in side},
                       key=lambda k: (k != "end_of_life", k))
        lines += ["## Where the impact comes from (mean per functional unit)", "",
                  "| Stage | " + " | ".join(st) + " |", "|---|" + "---|" * len(st)]
        for k in names:
            label = "**end of life (disposal)**" if k == "end_of_life" else k.replace("_", " ")
            lines.append(f"| {label} | " + " | ".join(_fmt(side.get(k, 0.0)) for side in st.values()) + " |")
        lines.append("")
        rev = reversals(model, result)
        lines += ["## What would reverse the verdict", ""]
        if rev:
            lines += ["Smallest change in a single choice, every other answer kept.", "",
                      "| Choice | Now | Verdict reverses at | P(A < B) after |", "|---|---|---|---|"]
            for r in rev:
                lines.append(f"| {r['name']} | {_fmt(r['now'])} | {_fmt(r['reverses_at'])} | {r['p_after']:.0%} |")
        else:
            lines.append("No change in a single choice, within its plausible range, reverses the verdict.")
        lines.append("")
    if analysis and hasattr(model, "build_args"):
        rows = indicators(model, result)
        if len(rows) > 1:
            lines += ["## All impact categories (mean per functional unit)", "",
                      f"| Category | Unit | {model.label_a} | {model.label_b} | Lower | P({model.label_a} lower) |",
                      "|---|---|---|---|---|---|"]
            for r in rows:
                flag = "" if r["agrees"] else " (trade off)"
                lines.append(f"| {r['category']} | {r['unit']} | {_fmt(r['mean_a'])} | {_fmt(r['mean_b'])} | "
                             f"{r['lower']}{flag} | {r['p_a_lower']:.0%} |")
            lines.append("")
    for note in result.get("notices", []):
        lines += [f"> {note}", ""]
    lines += ["## Modelling choices", "", "| Choice | Value | Decided by |", "|---|---|---|"]
    for c in model.choices:
        if c.name in result["fixed"]:
            val = c.decode(result["fixed"][c.name])
            val = f"{val:.4g}" if isinstance(val, float) else val
        else:
            val = "distribution kept"
        lines.append(f"| {c.name} | {val} | {result['decided_by'][c.name]} |")
    sourced = [c for c in model.choices if c.source.startswith("SOURCE") and c.name not in result["fixed"]]
    if sourced:
        lines += ["", "## Priors from published sources (kept as distributions)", ""]
        lines += [f"- {c.name}: {c.source}" for c in sourced]
    pending = [c.name for c in model.choices if c.source.startswith("ASSUMPTION")]
    if pending:
        lines += ["", "## Placeholder priors (to be replaced by sourced data)", ""]
        lines += [f"- {n}: {model.by_name[n].source}" for n in pending]
    lines += ["", "## Limits", "",
              "- Attributional study, ILCD Situation A.",
              "- Priors are only as good as the regional statistics behind them.",
              "- BRANCH follows ISO 14040 and ISO 14044 and prepares the study for the critical "
              "review required for comparisons disclosed to the public, but it does not replace "
              "the panel of reviewers."]
    if meta.get("citation"):
        lines += ["", "## Data source", "", f"{meta['citation']}. Unit impact factors from {meta.get('factors_file')}."]
    return "\n".join(lines) + "\n"

"""One page for the experiments of version 0.2: results/v02/SUMMARY.md and results/v02/verdicts.csv.

    python experiments/v02_summary.py

Reads the ALL_summary.csv of every block that experiments/run_v02_experiments.sh wrote, applies the
readings fixed beforehand in experiments/PLAN_2026-11-15.md, and lists, case by case, the sign of
the verdict under each model (the central value of every choice, and the share of prior draws in
which A is lower). It only reports: nothing here chooses between results.
"""
import csv
import itertools
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "results", "v02")
BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
TAU = 2.5


def rows(block, truth):
    path = os.path.join(OUT, f"{block}_{truth}", "ALL_summary.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    return df[df.batch_size == 3].set_index("strategy")


def interval(text):
    lo, hi = str(text).split(" to ")
    return float(lo), float(hi)


def table(lines, blocks):
    lines += ["| Block | Expert | Cases | Certified from the priors | Questions: decision flip | Sobol | entropy | random | "
              "entropy minus decision flip (95%) | Wrong certified, decision flip (95% over cases) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for block in blocks:
        for truth in ("prior", "tails"):
            r = rows(block, truth)
            if r is None:
                continue
            d = r.loc["decision_flip"]
            lines.append(f"| {block} | {truth} | {int(d.cases)} | {int(d.cases_no_question)} | {d.q_mean:.2f} | "
                         f"{r.loc['sobol'].q_mean:.2f} | {r.loc['entropy'].q_mean:.2f} | {r.loc['random'].q_mean:.2f} | "
                         f"{r.loc['entropy'].dq_vs_decision_flip:.2f} ({r.loc['entropy'].dq_ci95}) | "
                         f"{d.wrong_when_certified_pct:.1f}% ({d.wrong_ci95}) |")
    lines.append("")


def reading_questions(block):
    r = rows(block, "prior")
    if r is None:
        return None
    lo, hi = interval(r.loc["entropy"].dq_ci95)
    if lo > 0:
        return "holds: the interval of entropy minus decision flip lies entirely above zero"
    if hi < 0:
        return "FAILS: the interval lies entirely below zero, entropy asks less"
    return "not shown with these cases: the interval contains zero"


def reading_certificate(block):
    r = rows(block, "tails")
    if r is None:
        return None
    lo, hi = interval(r.loc["decision_flip"].wrong_ci95)
    if lo > TAU:
        return f"the certificate errs above its target: interval {lo} to {hi}%, entirely above {TAU}%"
    if hi <= TAU:
        return f"the target holds: interval {lo} to {hi}%, entirely at or below {TAU}%"
    return f"undecided: the interval {lo} to {hi}% contains {TAU}%"


def verdicts():
    """Sign of the verdict of each case under each model that could be built."""
    from branch.real_cases import compare, load_factors
    bafu = load_factors()
    models = {"BAFU cut-off": dict(factors=bafu), "BAFU CFF": dict(factors=bafu, system_model="cff")}
    for label, name in (("ELCD hybrid", "hybrid_elcd32.json"), ("ELCD hybrid, IPCC 2021", "hybrid_elcd32_ipcc2021.json")):
        path = os.path.join(ROOT, "data", "factors_second", name)
        if os.path.exists(path):
            models[label] = dict(factors=load_factors(path))
    out = []
    for region in ("PT", "DE", "BR"):
        for a, b in itertools.combinations(BENCH, 2):
            row = {"region": region, "a": a, "b": b}
            for label, kw in models.items():
                if label.startswith("ELCD") and region == "BR":
                    continue
                m = compare(a, b, region=region, **kw)
                point = {c.name: (float(np.argmax(c.probs)) if c.kind == "categorical" else float(c.ppf(np.array([0.5]))[0]))
                         for c in m.choices}
                S = m.sample(20_000, seed=0)
                p = float(np.mean(np.asarray(sum(m.term_value(i, S) for i in range(len(m.terms)))) < 0))
                row[label] = ("A" if m.delta_at(point) < 0 else "B") + f" ({p:.2f})"
            out.append(row)
    return out, list(models)


def main():
    if not os.path.isdir(OUT):
        sys.exit("no results/v02: run experiments/run_v02_experiments.sh first")
    lines = ["# Experiments of version 0.2", "",
             "Chosen setting: tau 2.5%, three questions per round. Readings as fixed in experiments/PLAN_2026-11-15.md.", ""]
    table(lines, ["families", "bafu12", "placebo12", "elcd", "elcd_ipcc2021", "cutoff", "cff", "uncertainty"])
    for title, block in (("B2, other product families", "families"), ("B3, second database (ELCD hybrid)", "elcd"),
                         ("A3, uncertainty of the datasets", "uncertainty")):
        q, c = reading_questions(block), reading_certificate(block)
        if q is not None:
            lines += [f"**{title}.** Fewer questions than entropy: {q}. Certificate with tail experts: {c}.", ""]
    v, labels = verdicts()
    with open(os.path.join(OUT, "verdicts.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["region", "a", "b"] + labels)
        w.writeheader()
        w.writerows(v)
    lines += ["## Verdict of each case under each model", "",
              "Lower product at the central value of every choice (A or B), and the share of prior draws in which A is lower.", "",
              "| Region | A | B | " + " | ".join(labels) + " |", "|---|---|---|" + "---|" * len(labels)]
    changed = {x: [] for x in labels[1:]}
    for r in v:
        lines.append(f"| {r['region']} | {r['a']} | {r['b']} | " + " | ".join(r.get(x, "") for x in labels) + " |")
        for x in labels[1:]:
            if r.get(x) and r[x][0] != r[labels[0]][0]:
                changed[x].append(f"{r['region']} {r['a']} against {r['b']}")
    lines.append("")
    for x, cases in changed.items():
        lines.append(f"Central verdict different from {labels[0]} under {x}: {len(cases)} case(s)"
                     + (": " + "; ".join(cases) if cases else "") + ".")
    with open(os.path.join(OUT, "SUMMARY.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

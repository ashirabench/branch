"""One page for the experiments of version 0.2: results/v02/SUMMARY.md and results/v02/verdicts.csv.

    python experiments/v02_summary.py

Reads what experiments/run_v02_experiments.sh wrote and applies the readings fixed beforehand in
experiments/PLAN_2026-11-15.md (section "Changes of 16 November 2026"):

  primary reading   one: block families, statement 1 (fewer questions than entropy), expert drawn
                    from the priors, interval over PAIRS of products
  secondary         everything else, reported with the same rules and named as secondary
  B3 (ELCD)         read by the size of the effect against BAFU on the same 12 cases, because 12
                    cases cannot confirm anything
  sensitivity       wash_old, cff_heat_none, cff_heat_district, cff_pet_ssp, uncertainty_correlated:
                    reported, never read as a statement

It only reports: nothing here chooses between results.
"""
import csv
import glob
import itertools
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from summarize_benchmark import boot_ratio, pair_index  # noqa: E402

OUT = os.path.join(ROOT, "results", "v02")
BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
TAU = 2.5
READ = ["families", "bafu12", "placebo12", "elcd", "elcd_ipcc2021", "cutoff", "cff", "uncertainty"]
SENSITIVITY = ["wash_old", "cff_heat_none", "cff_heat_district", "cff_pet_ssp", "uncertainty_correlated"]
PRIMARY = "families"


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
    lines += ["| Block | Expert | Cases | Pairs | Certified from the priors | Questions: decision flip | Sobol | entropy | "
              "random | entropy minus decision flip | 95% by pair | 95% by case | Wrong certified, decision flip | "
              "95% by pair | 95% by case |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for block in blocks:
        for truth in ("prior", "tails"):
            r = rows(block, truth)
            if r is None:
                continue
            d, e = r.loc["decision_flip"], r.loc["entropy"]
            lines.append(f"| {block} | {truth} | {int(d.cases)} | {int(d.pairs)} | {int(d.cases_no_question)} | "
                         f"{d.q_mean:.2f} | {r.loc['sobol'].q_mean:.2f} | {e.q_mean:.2f} | {r.loc['random'].q_mean:.2f} | "
                         f"{e.dq_vs_decision_flip:.2f} | {e.dq_ci95_pair} | {e.dq_ci95} | "
                         f"{d.wrong_when_certified_pct:.1f}% | {d.wrong_ci95_pair} | {d.wrong_ci95} |")
    lines.append("")


def reading_questions(block):
    """Statement 1, expert from the priors, interval over pairs."""
    r = rows(block, "prior")
    if r is None:
        return None
    lo, hi = interval(r.loc["entropy"].dq_ci95_pair)
    if lo > 0:
        return "holds: the interval of entropy minus decision flip lies entirely above zero"
    if hi < 0:
        return "FAILS: the interval lies entirely below zero, entropy asks less"
    return "not shown with these cases: the interval contains zero"


def reading_certificate(block):
    """Statement 2, experts from the tails, interval over pairs."""
    r = rows(block, "tails")
    if r is None:
        return None
    lo, hi = interval(r.loc["decision_flip"].wrong_ci95_pair)
    if lo > TAU:
        return f"the certificate errs above its target: interval {lo} to {hi}%, entirely above {TAU}%"
    if hi <= TAU:
        return f"the target holds: interval {lo} to {hi}%, entirely at or below {TAU}%"
    return f"undecided: the interval {lo} to {hi}% contains {TAU}%"


def per_case_gap(block, truth="prior"):
    """{case: mean questions of entropy minus decision flip} from the runs of a block."""
    out = {}
    for f in sorted(glob.glob(os.path.join(OUT, f"{block}_{truth}", "*_runs.csv"))):
        df = pd.read_csv(f)
        q = df[df.batch_size == 3].groupby("strategy").questions.mean()
        out[os.path.basename(f)[: -len("_runs.csv")]] = float(q["entropy"] - q["decision_flip"])
    return out


def effect_against(x, y, cases):
    """Per case effects x (block) and y (base) on the same cases: (mean x, mean y, mean difference,
    its 95% interval over pairs, label). Compatible: same sign and the interval contains zero."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    idx, members = pair_index(cases)
    lo, hi = np.percentile(boot_ratio(x - y, np.ones(len(cases)), idx, members), [2.5, 97.5])
    same_sign = (x.mean() > 0) == (y.mean() > 0)
    label = ("compatible with the base: same sign and the interval of the difference contains zero"
             if same_sign and lo <= 0 <= hi else
             "NOT compatible with the base: " + ("the sign of the effect changes" if not same_sign
                                                  else "the interval of the difference excludes zero"))
    return float(x.mean()), float(y.mean()), float((x - y).mean()), float(lo), float(hi), label


def compare_effect(block, base):
    a, b = per_case_gap(block), per_case_gap(base)
    cases = sorted(set(a) & set(b))
    if not cases:
        return None
    return effect_against([a[c] for c in cases], [b[c] for c in cases], cases) + (len(cases),)


def verdicts():
    """Sign of the verdict of each case under each model that could be built."""
    from branch.real_cases import compare, load_factors
    from run_grid import PET_SSP, set_wash_kwh_high
    bafu = load_factors()
    models = {"BAFU cut-off": dict(factors=bafu),
              "cut-off, washing up to 0.03 kWh": dict(factors=bafu, wash=0.03),
              "BAFU CFF": dict(factors=bafu, system_model="cff"),
              "CFF, no heat credit": dict(factors=bafu, system_model="cff", cff_heat="none"),
              "CFF, PET quality 1": dict(factors=bafu, system_model="cff", cff_overrides=PET_SSP)}
    if "district_heat_ch_average" in bafu["factors"]:
        models["CFF, district heat"] = dict(factors=bafu, system_model="cff", cff_heat="district")
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
                kw = dict(kw)
                wash = kw.pop("wash", None)
                m = compare(a, b, region=region, **kw)
                if wash is not None:
                    set_wash_kwh_high(m, wash)
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
             "Chosen setting: tau 2.5%, three questions per round. Readings as fixed in experiments/PLAN_2026-11-15.md, "
             "section \"Changes of 16 November 2026\": intervals over pairs of products decide, intervals over cases are "
             "shown beside them.", ""]
    q = reading_questions(PRIMARY)
    lines += ["## Primary reading", "",
              "Other product families, expert drawn from the priors, fewer questions than entropy: "
              + (q if q is not None else "not run yet") + ".", "", "## All blocks (secondary readings)", ""]
    table(lines, READ)
    for title, block in (("B2, other product families", "families"), ("A3, uncertainty of the datasets", "uncertainty")):
        q, c = reading_questions(block), reading_certificate(block)
        if q is not None:
            lines += [f"**{title}.** Fewer questions than entropy: {q}. Certificate with tail experts: {c}.", ""]
    for title, block in (("B3, second database (ELCD hybrid)", "elcd"), ("B3, ELCD hybrid with IPCC 2021", "elcd_ipcc2021")):
        e = compare_effect(block, "bafu12")
        if e is not None:
            lines += [f"**{title}.** Twelve cases in six pairs cannot confirm a statement, so this block is read by the "
                      f"size of the effect. Entropy minus decision flip: {e[0]:.2f} questions with this database, "
                      f"{e[1]:.2f} with BAFU on the same {e[6]} cases; difference {e[2]:.2f} (95% over pairs "
                      f"{e[3]:.2f} to {e[4]:.2f}): {e[5]}. Compatible means that no difference was detected, "
                      f"not that the two are equal. Certificate with tail experts, for description: "
                      f"{reading_certificate(block)}.", ""]
    if any(rows(b, "prior") is not None for b in SENSITIVITY):
        lines += ["## Sensitivity runs (reported, not read as statements)", ""]
        table(lines, SENSITIVITY)
    from prior_sources import benchmark_counts, lines as source_lines
    lines += ["## How much of each prior has a source (benchmark, per region)", "",
              "The label SOURCE means that the centre has a source. The spread is my choice or my rule in the "
              "second column; no prior has an uncertainty that a source measured as such.", ""]
    lines += source_lines(benchmark_counts()) + [""]
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

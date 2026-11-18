"""One page for the experiments of version 0.2: results/v02/SUMMARY.md and results/v02/verdicts.csv.

    python experiments/benchmark/v02_summary.py

Reads what experiments/benchmark/run_v02_experiments.sh wrote and applies the readings fixed beforehand in
experiments/record/PLAN_2026-11-15.md (section "Changes of 16 November 2026"):

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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prior_sources import benchmark_counts  # noqa: E402
from prior_sources import lines as source_lines  # noqa: E402
from summarize_benchmark import boot_ratio, pair_index  # noqa: E402

OUT = os.path.join(ROOT, "results", "v02")
BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
TAU = 2.5
READ = ["families", "bafu12", "placebo12", "elcd", "elcd_ipcc2021", "cutoff", "cff", "uncertainty"]
SENSITIVITY = ["wash_old", "cff_heat_none", "cff_heat_district", "cff_pet_ssp", "uncertainty_correlated"]
PRIMARY = "families"
MARGIN = 0.5          # questions; equivalence with the Sobol index of the impact (plan, point 13)
EQUIVALENCE = [("other product families (the equivalence reading)", "eq_families"), ("the 18 benchmark cases", "eq_bench")]
STRESS = ["stress_families", "stress_bench"]


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
        for truth in ("prior", "tails", "adverse"):
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
    p = float(r.loc["entropy"].p_pair)
    tail = f" (exact test over pairs: p = {p:.3g})"
    if lo > 0 and p <= 0.05:
        return "holds: the interval of entropy minus decision flip lies entirely above zero and the exact test agrees" + tail
    if hi < 0 and p <= 0.05:
        return "FAILS: the interval lies entirely below zero, entropy asks less" + tail
    return "not shown with these cases: the interval contains zero, or the exact test over pairs does not agree" + tail


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


def reading_equivalence(block):
    """Sobol of the impact minus decision flip, experts from the priors, interval over pairs inside +-MARGIN."""
    r = rows(block, "prior")
    if r is None:
        return None
    s = r.loc["sobol"]
    lo, hi = interval(s.dq_ci95_pair)
    text = (f"Sobol of the impact {s.q_mean:.2f} questions, decision flip {r.loc['decision_flip'].q_mean:.2f}; "
            f"difference {s.dq_vs_decision_flip:.2f} (95% over {int(s.pairs)} pairs {lo:.2f} to {hi:.2f})")
    if -MARGIN < lo and hi < MARGIN:
        return text + f": equivalent within {MARGIN} question, the interval lies inside the margin"
    return text + f": equivalence within {MARGIN} question NOT shown, the interval leaves the margin"


def reading_adverse(block):
    r = rows(block, "adverse")
    if r is None:
        return None
    d = r.loc["decision_flip"]
    lo, hi = interval(d.wrong_ci95_pair)
    verdict = ("the certificate errs above its nominal level" if lo > TAU else
               "not shown to exceed the nominal level" + (" (the interval contains it)" if hi > TAU else ""))
    return (f"{d.wrong_when_certified_pct:.1f}% of the certified verdicts are wrong (95% over pairs {lo} to {hi}%), "
            f"{d.q_mean:.2f} questions: {verdict}")


def synthetic_lines():
    """Point 15: decision flip against the Sobol index of the impact on synthetic models. Illustration only."""
    path = os.path.join(OUT, "synthetic_runs.csv")
    if not os.path.exists(path):
        return []
    df = pd.read_csv(path)
    out = ["## Illustration on synthetic models (not evidence about real products)", "",
           f"{df.case_seed.nunique()} synthetic models of 40 choices, {df.seed.nunique()} sessions each, experts from the "
           "priors, tau 2.5%. Intervals: bootstrap over models.", "",
           "| Questions per round | Decision flip | Sobol of the impact | entropy | Sobol minus decision flip "
           "| 95% over models | "
           "Models where the two differ | Wrong certified: decision flip | Sobol |", "|---|---|---|---|---|---|---|---|---|"]
    rng = np.random.default_rng(0)
    for b, g in df.groupby("batch_size"):
        q = g.pivot_table(index="case_seed", columns="strategy", values="questions", aggfunc="mean")
        d = (q["sobol"] - q["decision_flip"]).to_numpy()
        boot = d[rng.integers(0, len(d), size=(10_000, len(d)))].mean(1)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        wrong = {s: 100 * (1 - x[x.certified].correct.mean()) for s, x in g.groupby("strategy")}
        out.append(f"| {b} | {q['decision_flip'].mean():.2f} | {q['sobol'].mean():.2f} | {q['entropy'].mean():.2f} | "
                   f"{d.mean():.2f} | {lo:.2f} to {hi:.2f} | {int((np.abs(d) > 1e-9).sum())} of {len(d)} | "
                   f"{wrong['decision_flip']:.1f}% | {wrong['sobol']:.1f}% |")
    return out + [""]


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
    from run_grid import PET_SSP, set_wash_kwh_high

    from branch.real_cases import compare, load_factors
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


HEAD = ["# Experiments of version 0.2", "",
        "Chosen setting: tau 2.5%, three questions per round. Readings as fixed in experiments/record/PLAN_2026-11-15.md, "
        "section \"Changes of 16 November 2026\": intervals over pairs of products decide, intervals over cases are "
        "shown beside them.", ""]


def primary_lines():
    q = reading_questions(PRIMARY)
    lines = ["## Primary reading", "",
             "Other product families, expert drawn from the priors, fewer questions than entropy: "
             + (q if q is not None else "not run yet") + ".", "", "## All blocks (secondary readings)", ""]
    table(lines, READ)
    for title, block in (("B2, other product families", "families"), ("A3, uncertainty of the datasets", "uncertainty")):
        q, c = reading_questions(block), reading_certificate(block)
        if q is not None:
            lines += [f"**{title}.** Fewer questions than entropy: {q}. Certificate with tail experts: {c}.", ""]
    return lines


def second_database_lines():
    lines = []
    for title, block in (("B3, second database (ELCD hybrid)", "elcd"), ("B3, ELCD hybrid with IPCC 2021", "elcd_ipcc2021")):
        e = compare_effect(block, "bafu12")
        if e is not None:
            lines += [f"**{title}.** Twelve cases in six pairs cannot confirm a statement, so this block is read by the "
                      f"size of the effect. Entropy minus decision flip: {e[0]:.2f} questions with this database, "
                      f"{e[1]:.2f} with BAFU on the same {e[6]} cases; difference {e[2]:.2f} (95% over pairs "
                      f"{e[3]:.2f} to {e[4]:.2f}): {e[5]}. Compatible means that no difference was detected, "
                      f"not that the two are equal. Certificate with tail experts, for description: "
                      f"{reading_certificate(block)}.", ""]
    return lines


def review_lines():
    """The blocks added by the review of the plan: equivalence, a second wrong expert, the synthetic models,
    the sensitivity runs."""
    lines = []
    eq = [(t, reading_equivalence(b)) for t, b in EQUIVALENCE]
    if any(r for _, r in eq):
        lines += ["## Equivalence with the Sobol index of the impact (new seeds 300 to 329)", ""]
        lines += [f"- {t.capitalize()}: {r}." for t, r in eq if r] + [""]
    if any(rows(b, "adverse") is not None for b in STRESS):
        lines += ["## A second wrong expert: beliefs wrong on the side against the verdict (description)", ""]
        lines += [f"- {b}: {reading_adverse(b)}." for b in STRESS if reading_adverse(b)] + [""]
        table(lines, STRESS)
    lines += synthetic_lines()
    if any(rows(b, "prior") is not None for b in SENSITIVITY):
        lines += ["## Sensitivity runs (reported, not read as statements)", ""]
        table(lines, SENSITIVITY)
    return lines


def sources_lines():
    return (["## How much of each prior has a source (benchmark, per region)", "",
             "The label SOURCE means that the centre has a source. The spread is my choice or my rule in the "
             "second column; no prior has an uncertainty that a source measured as such.", ""]
            + source_lines(benchmark_counts()) + [""])


def verdict_lines():
    """The verdict of every case under every model, written to verdicts.csv and as a table."""
    v, labels = verdicts()
    with open(os.path.join(OUT, "verdicts.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["region", "a", "b"] + labels)
        w.writeheader()
        w.writerows(v)
    lines = ["## Verdict of each case under each model", "",
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
    return lines


def main():
    if not os.path.isdir(OUT):
        sys.exit("no results/v02: run experiments/benchmark/run_v02_experiments.sh first")
    lines = HEAD + primary_lines() + second_database_lines() + review_lines() + sources_lines() + verdict_lines()
    with open(os.path.join(OUT, "SUMMARY.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

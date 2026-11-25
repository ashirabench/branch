"""Does the rule "never ask a question that cannot change the verdict" change any result of the paper?

Since 25 November 2026 the agent leaves out of a round every choice whose score is zero or below
(branch/agent.py, ASKS_ONLY_USEFUL). A session in which no round had such a choice among its best
ranked runs exactly as before, draw for draw, so its result is unchanged. This script runs the
settings of the paper with the agent's strategy and counts the sessions where the rule acted.

    python experiments/evals/check_useless_questions.py            # needs data/factors
    python experiments/evals/check_useless_questions.py --quick    # a few sessions, to see it run

Writes results/evals/useless_questions.csv: one row per setting, the sessions run and the
sessions where the rule acted.
"""
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))

import argparse
import csv
import itertools
import os
import re
from concurrent.futures import ProcessPoolExecutor

from branch.agent import Session
from branch.builder import build_model
from branch.cases import draw_truth, draw_truth_adverse, draw_truth_tails
from branch.factors import load_factors

BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
EXPERTS = {"prior": draw_truth, "tails": draw_truth_tails, "adverse": draw_truth_adverse}
SCRIPT = os.path.join("experiments", "benchmark", "run_v02_experiments.sh")


def family_pairs():
    """The ten pairs of other packages, read from the script that ran them (fixed on 16 Nov 2026)."""
    with open(SCRIPT, encoding="utf-8") as fh:
        block = re.search(r"FAMILIES=\((.*?)\n\)", fh.read(), re.S).group(1)
    pairs = re.findall(r'^\s+"(\S+) (\S+)"$', block, re.M)
    return [tuple(p.replace("$E", "data/examples") for p in pair) for pair in pairs]


def settings(quick):
    """(cases, batch, tau, expert, seeds) of the runs of the paper."""
    bench = [(a, b, r) for (a, b), r in itertools.product(itertools.combinations(BENCH, 2), ["PT", "DE", "BR"])]
    fams = [(a, b, r) for (a, b), r in itertools.product(family_pairs(), ["PT", "DE", "BR"])]
    if quick:
        return [(bench[:2], 3, 0.025, "prior", range(2)), (fams[:2], 3, 0.025, "prior", range(200, 202))]
    out = [(bench, batch, tau, expert, range(30)) for batch in (1, 2, 3, 4, 5)
           for tau in (0.05, 0.025) for expert in ("prior", "tails")]
    out += [(bench, 3, 0.025, "adverse", range(30))]
    out += [(fams, 3, 0.025, expert, range(200, 230)) for expert in ("prior", "tails", "adverse")]
    return out


def acted(job):
    """True when, in some round of this session, a best ranked choice had a score of zero or below."""
    (a, b, region), batch, tau, expert, seed, n = job
    model = build_model(a, b, region, "Climate change", load_factors())
    truth = EXPERTS[expert](model, seed)
    s = Session(model, "decision_flip", batch, n, tau, seed, truth=truth)
    hit, inner = [], s.score_fn

    def watched(state, rng):
        scores = inner(state, rng)
        k = min(batch, s.max_q - len(s.asked), len(state.open))
        hit.append(any(scores[x] <= 0.0 for x in sorted(state.open, key=lambda x: scores[x], reverse=True)[:k]))
        return scores
    s.score_fn = watched
    while (name := s.next_question()) is not None:
        s.answer(name, truth[name])
    return any(hit)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    a = ap.parse_args(argv)
    n = 2000 if a.quick else 20_000
    rows = []
    with ProcessPoolExecutor(a.workers) as pool:
        for cases, batch, tau, expert, seeds in settings(a.quick):
            jobs = [(c, batch, tau, expert, seed, n) for c in cases for seed in seeds]
            hits = sum(pool.map(acted, jobs, chunksize=8))
            rows.append({"cases": "beverage" if cases[0][0] in BENCH else "families", "batch": batch, "tau": tau,
                         "expert": expert, "sessions": len(jobs), "rule_acted": hits})
            print(rows[-1], flush=True)
    os.makedirs(os.path.join("results", "evals"), exist_ok=True)
    with open(os.path.join("results", "evals", "useless_questions.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"the rule acted in {sum(r['rule_acted'] for r in rows)} of {sum(r['sessions'] for r in rows)} sessions")


if __name__ == "__main__":
    main()

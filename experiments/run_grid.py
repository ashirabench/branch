"""Experiment grid: query strategy x batch size x samples x seeds.

Mirrors the design of Faria et al. (EPIA 2022): every configuration is run
over many seeds; each seed draws a different simulated expert world.

    python experiments/run_grid.py --case lca --J 40 --seeds 30 --workers 20
    python experiments/run_grid.py --case toy --batch 1 2 3 4 5
    python experiments/run_grid.py --case real --a pet_bottle_1l --b glass_refillable_1l --region PT

CPU runs are spread over processes (ProcessPoolExecutor). With
BRANCH_BACKEND=cupy use --workers 1 (one GPU, one process).
Writes results/<tag>_runs.csv and results/<tag>_traces.jsonl
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import argparse
import csv
import itertools
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor

from branch.agent import run_agent
from branch.backend import get_xp
from branch.cases import draw_truth, draw_truth_tails, synthetic, synthetic_lca, toy_packaging
from branch.query import STRATEGIES


ABLATIONS = ("none", "no_location", "uniform")


def no_location_region():
    """A region that knows nothing about the place: global electricity mix, default priors."""
    from branch.regions import REGION_DIR, Region, _raw
    return Region([{"code": "NOLOC", "name": "No location", "parent": "GLO",
                    "electricity": "electricity_mv_GLO"}, _raw("GLO", REGION_DIR)])


def make_uniform(model):
    """Every continuous prior uniform over its possible range, every categorical one equal."""
    for c in model.choices:
        if c.kind == "categorical":
            c.prior = {k: 1.0 for k in c.prior}
        else:
            lo, hi = float(c.ppf(0.0)), float(c.ppf(1.0))
            if not (lo < hi and abs(lo) != float("inf") and abs(hi) != float("inf")):
                raise ValueError(f"{c.name}: no finite range for a uniform prior")
            c.prior = ("uniform", {"low": lo, "high": hi})
    return model


def build(case, J, case_seed, xp, a=None, b=None, country="PT", category="Climate change"):
    if case == "real":
        from branch.real_cases import compare
        return compare(a, b, country, category=category, xp=xp)
    if case == "toy":
        return toy_packaging(xp)
    if case == "lca":
        return synthetic_lca(J, seed=case_seed, xp=xp)
    if case == "sym":
        return synthetic(J, seed=case_seed, xp=xp)
    raise ValueError(case)


def one_run(cfg):
    xp = get_xp(cfg["backend"])
    category, ablation = cfg.get("category", "Climate change"), cfg.get("ablation", "none")
    args = (cfg["case"], cfg["J"], cfg["case_seed"], xp, cfg.get("a"), cfg.get("b"))
    model = build(*args, cfg.get("country", "PT"), category)
    # The expert and the reference verdict always come from this model (the national one).
    truth = (draw_truth_tails(model, cfg["seed"]) if cfg.get("truth") == "tails"
             else draw_truth(model, cfg["seed"]))
    reference = None
    if ablation != "none":
        if cfg["case"] != "real":
            raise ValueError("ablations need --case real")
        reference = bool(model.delta_at(truth) < 0)
        agent = (build(*args, no_location_region(), category) if ablation == "no_location"
                 else make_uniform(build(*args, cfg.get("country", "PT"), category)))
        if [c.name for c in agent.choices] != [c.name for c in model.choices]:
            raise ValueError("the ablated model must have the choices of the national model")
        model = agent
    t0 = time.perf_counter()
    r = run_agent(model, lambda n: truth[n], strategy=cfg["strategy"], batch_size=cfg["batch"],
                  n_samples=cfg["n"], tau=cfg["tau"], seed=cfg["seed"], truth=truth,
                  reference_a_lower=reference)
    r["wall_s"] = time.perf_counter() - t0
    r.update({k: cfg[k] for k in ("case", "J", "case_seed")})
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="lca", choices=["toy", "lca", "sym", "real"])
    ap.add_argument("--a", default="pet_bottle_1l", help="--case real: product A")
    ap.add_argument("--b", default="glass_refillable_1l", help="--case real: product B")
    ap.add_argument("--region", "--country", dest="region", default="PT", help="--case real: region code")
    ap.add_argument("--J", type=int, default=40)
    ap.add_argument("--case_seeds", type=int, nargs="+", default=[0])
    ap.add_argument("--strategies", nargs="+", default=list(STRATEGIES))
    ap.add_argument("--batch", type=int, nargs="+", default=[1])
    ap.add_argument("--n", type=int, nargs="+", default=[20_000])
    ap.add_argument("--tau", type=float, default=0.05)
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--first-seed", dest="first_seed", type=int, default=0,
                    help="first seed; use fresh seeds (e.g. 1000) for a confirmation run")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--backend", default=os.environ.get("BRANCH_BACKEND", "numpy"))
    ap.add_argument("--tag", default=None)
    ap.add_argument("--truth", default="prior", choices=["prior", "tails"],
                    help="simulated expert drawn from the agent's priors, or from their tails (wrong priors)")
    ap.add_argument("--category", default="Climate change",
                    help="--case real: the impact category whose verdict the agent settles")
    ap.add_argument("--ablation", default="none", choices=ABLATIONS,
                    help="--case real: knowledge removed from the agent (experiments/PLAN_2026-11-13.md)")
    args = ap.parse_args()

    tag = args.tag or (f"real_{args.a}_vs_{args.b}_{args.region}" if args.case == "real"
                       else f"{args.case}_J{args.J}")
    cfgs = [dict(case=args.case, J=args.J, case_seed=cs, strategy=s, batch=b, n=n, seed=sd,
                 tau=args.tau, backend=args.backend, a=args.a, b=args.b, country=args.region,
                 truth=args.truth, category=args.category, ablation=args.ablation)
            for cs, s, b, n, sd in itertools.product(args.case_seeds, args.strategies, args.batch,
                                                     args.n, range(args.first_seed, args.first_seed + args.seeds))]
    print(f"{len(cfgs)} runs on {args.workers} workers")
    os.makedirs("results", exist_ok=True)
    cols = ["case", "J", "case_seed", "strategy", "batch_size", "n_samples", "seed", "tau",
            "questions", "certified", "correct", "p_flip", "latency_mean_s", "latency_max_s", "wall_s"]
    t0 = time.perf_counter()
    with open(f"results/{tag}_runs.csv", "w", newline="") as fc, \
            open(f"results/{tag}_traces.jsonl", "w") as ft, \
            ProcessPoolExecutor(max_workers=args.workers) as ex:
        w = csv.DictWriter(fc, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(ex.map(one_run, cfgs, chunksize=4), 1):
            w.writerow(r)
            ft.write(json.dumps({k: r[k] for k in ("strategy", "batch_size", "n_samples", "seed",
                                                    "case_seed", "trace", "asked")}) + "\n")
            if i % 50 == 0 or i == len(cfgs):
                print(f"  {i}/{len(cfgs)}  {time.perf_counter() - t0:.1f}s", flush=True)
    print(f"saved results/{tag}_runs.csv  total {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()

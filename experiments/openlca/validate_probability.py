"""Check the probability of BRANCH, not only its central value, against openLCA.

    python experiments/openlca/validate_probability.py                      # PET against glass, Portugal
    python experiments/openlca/validate_probability.py --a A --b B --region DE --worlds 200

The probability that product A has the lower impact is an integral: the share, over the priors, of the
worlds in which the impact of A is below that of B. BRANCH estimates it with N draws. This script checks
its three parts separately, because openLCA cannot be asked for the integral directly (its own simulation
would also draw the uncertainty of every exchange of the database):

1. The function. For K worlds drawn from the priors (seeds that no experiment uses), every choice is fixed
   at the value of the world, the model is sent to openLCA, and openLCA calculates both products. The
   impacts must agree, and so must the product that wins, world by world.
2. The integral on those worlds. The share of the K worlds in which openLCA says A wins is an estimate of
   the probability made with openLCA alone. Its exact 95% interval must contain the value of BRANCH.
3. The draws. They come from scipy's distributions; tests/test_sampler.py compares them with the
   distributions written in the priors.

Needs openLCA open with its IPC server started. Writes one line per world and product, and a summary.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

FIRST_SEED = 7000   # worlds 7000, 7001, ...: used by nothing else


def exact_interval(k, n, level=0.95):
    """Clopper and Pearson interval for k successes in n."""
    a = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else float(stats.beta.ppf(a, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1.0 - a, k + 1, n - k))
    return lo, hi


def summarise(worlds, p_branch):
    """worlds: [{"olca_a", "olca_b", "branch_a", "branch_b"}]. Returns the summary as a dict."""
    n = len(worlds)
    rel = [abs(w[f"olca_{s}"] - w[f"branch_{s}"]) / max(abs(w[f"branch_{s}"]), 1e-300) for w in worlds for s in "ab"]
    wins_olca = [w["olca_a"] < w["olca_b"] for w in worlds]
    wins_branch = [w["branch_a"] < w["branch_b"] for w in worlds]
    k = int(sum(wins_olca))
    lo, hi = exact_interval(k, n)
    return {"worlds": n, "largest_relative_difference": max(rel),
            "same_winner": int(sum(a == b for a, b in zip(wins_olca, wins_branch))),
            "p_openlca_worlds": k / n, "p_openlca_low": lo, "p_openlca_high": hi,
            "p_branch": p_branch, "branch_inside_interval": bool(lo <= p_branch <= hi)}


def fixed_world(model, seed):
    """Run the agent with an expert who answers everything, so every askable choice is fixed."""
    from branch.agent import run_agent
    from branch.cases import draw_truth
    truth = draw_truth(model, seed)
    return run_agent(model, lambda name: truth[name], tau=0.0, n_samples=2000, truth=truth), truth


def main():
    import olca_schema as o
    from branch import olca_bridge
    from branch.montecarlo import State
    from branch.real_cases import compare

    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="pet_bottle_1l")
    ap.add_argument("--b", default="glass_refillable_1l")
    ap.add_argument("--region", default="PT")
    ap.add_argument("--worlds", type=int, default=200)
    ap.add_argument("--first-seed", type=int, default=FIRST_SEED)
    ap.add_argument("--n", type=int, default=20000, help="draws of BRANCH for its own probability")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--out", default=os.path.join("results", "validation_probability.csv"))
    args = ap.parse_args()

    c = olca_bridge.client(args.port)
    try:
        c.get_descriptors(o.UnitGroup)
    except Exception:
        sys.exit("openLCA is not answering. In openLCA: open the database, then "
                 "Tools > Developer tools > IPC Server > Start.")
    prior = compare(args.a, args.b, args.region)
    p_branch = float((np.asarray(State(prior, prior.sample(args.n, 0)).delta) < 0).mean())
    print(f"BRANCH, {args.n} draws: P(A lower) = {p_branch:.4f}")
    rows, worlds = [], []
    for seed in range(args.first_seed, args.first_seed + args.worlds):
        model = compare(args.a, args.b, args.region)
        result, _ = fixed_world(model, seed)
        out = olca_bridge.push_comparison(c, model, result)
        (la, ca), (lb, cb) = list(out["check"].items())[:2]
        worlds.append({"olca_a": ca["openLCA"], "olca_b": cb["openLCA"], "branch_a": ca["BRANCH"], "branch_b": cb["BRANCH"]})
        for label, chk in ((la, ca), (lb, cb)):
            rows.append({"seed": seed, "product": label, "openLCA": chk["openLCA"], "BRANCH": chk["BRANCH"],
                         "relative_difference": chk["relative_difference"]})
        for ref in out["systems"] + out["processes"] + out.get("flows", []):
            try:
                c.delete(ref)
            except Exception:
                pass
        if (seed - args.first_seed + 1) % 10 == 0:
            print(f"  {seed - args.first_seed + 1} worlds")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    s = summarise(worlds, p_branch)
    with open(args.out.replace(".csv", "_summary.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["case"] + list(s))
        w.writeheader()
        w.writerow({"case": f"{args.a} vs {args.b}, {args.region}", **s})
    print(f"{s['worlds']} worlds: largest relative difference {s['largest_relative_difference']:.2g}; "
          f"same winner in {s['same_winner']} of {s['worlds']}")
    print(f"P(A lower) from openLCA on these worlds: {s['p_openlca_worlds']:.3f} "
          f"(exact 95% interval {s['p_openlca_low']:.3f} to {s['p_openlca_high']:.3f}); BRANCH {p_branch:.3f}; "
          + ("inside" if s["branch_inside_interval"] else "OUTSIDE"))
    print("Saved", args.out)


if __name__ == "__main__":
    main()

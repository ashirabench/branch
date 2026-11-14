"""Latency of one question choice (one BDI deliberation round).

Measures the HCAI x parallel computing question: can the agent choose the
next question within an interactive budget (about 1 s) as the number of
open choices J and Monte Carlo samples N grow?

    python experiments/bench_latency.py                       # CPU (NumPy)
    BRANCH_BACKEND=cupy python experiments/bench_latency.py   # GPU (DGX Spark)

Writes results/latency_<backend>.csv
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import argparse
import csv
import os
import statistics

import numpy as np

from branch.backend import Timer, get_xp
from branch.cases import synthetic_lca
from branch.montecarlo import State
from branch.query import STRATEGIES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--J", type=int, nargs="+", default=[10, 20, 40, 80, 160])
    ap.add_argument("--N", type=int, nargs="+", default=[1_000, 10_000, 100_000, 1_000_000])
    ap.add_argument("--strategy", default="decision_flip")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--backend", default=None)
    args = ap.parse_args()

    xp = get_xp(args.backend)
    name = xp.__name__
    os.makedirs("results", exist_ok=True)
    out = f"results/latency_{name}.csv"
    rng = np.random.default_rng(0)
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["backend", "strategy", "J", "N", "median_s", "min_s"])
        for J in args.J:
            model = synthetic_lca(J, seed=J, xp=xp)
            for N in args.N:
                state = State(model, model.sample(N, seed=1))
                STRATEGIES[args.strategy](state, rng)  # warm up (GPU kernels, caches)
                times = []
                for _ in range(args.repeats):
                    with Timer(xp) as t:
                        STRATEGIES[args.strategy](state, rng)
                    times.append(t.seconds)
                med = statistics.median(times)
                w.writerow([name, args.strategy, J, N, f"{med:.6f}", f"{min(times):.6f}"])
                fh.flush()
                flag = "  <1s ok" if med < 1 else "  OVER BUDGET"
                print(f"{name:5s} J={J:4d} N={N:8d}  {med*1000:9.2f} ms{flag}", flush=True)
    print(f"saved {out}")


if __name__ == "__main__":
    main()

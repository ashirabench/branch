"""Uncertainty of the unit factors, from the uncertainty that the database states for its exchanges.

For every factor it runs a Monte Carlo simulation of the dataset in openLCA and stores, per impact
category, the geometric standard deviation of the result under the factor in the factor file:

    "uncertainty": {"Climate change": {"gsd": 1.08, "n": 200, "median_ratio": 1.01, ...}, ...}

BRANCH then lets every factor vary in its own Monte Carlo draws (branch/builder.py), as a choice
that nobody is asked. Requirements as for extract_factors.py: openLCA open with the database, IPC
server on port 8080, and the factors already extracted.

    python experiments/openlca/extract_uncertainty.py --time-only        # three runs of one dataset, to see how long it takes
    python experiments/openlca/extract_uncertainty.py --runs 200         # the factors of the benchmark
    python experiments/openlca/extract_uncertainty.py --runs 200 --only pet_granulate_bottle_grade lorry_16_32t

It can be stopped and started again: factors already done with at least --runs runs are skipped,
and the file is saved after every factor (a copy of the file as it was is kept in outputs/).

What this does not capture: two factors simulated one at a time do not share the draws of the
processes they have in common (the same electricity inside PET and inside glass, say), so BRANCH
treats the uncertainties of different factors as independent.
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import olca_ipc as ipc  # noqa: E402
import olca_schema as o  # noqa: E402

from branch.builder import required_factor_keys  # noqa: E402
from branch.olca_extract import find_method, simulate_impacts, spread  # noqa: E402
from branch.real_cases import load_factors  # noqa: E402

BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]


def benchmark_keys(regions):
    keys = []
    for r in regions:
        keys += required_factor_keys(BENCH, r)
    return list(dict.fromkeys(keys))


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--regions", nargs="+", default=["PT", "DE", "BR"])
    ap.add_argument("--only", nargs="*", help="only these factor keys")
    ap.add_argument("--time-only", action="store_true", help="three runs of the first factor, print the time, save nothing")
    return ap.parse_args()


def keys_to_simulate(args, data, path):
    keys = args.only or benchmark_keys(args.regions)
    missing = [k for k in keys if k not in data["factors"]]
    if missing:
        sys.exit(f"not in {path}: {missing}. Extract them first with experiments/openlca/extract_factors.py")
    return keys


def open_database(args, data, path, keys):
    """(client, {process id: descriptor}, method), after checking that the open database is the one of the file."""
    client = ipc.Client(args.port)
    descs = {d.id: d for d in client.get_descriptors(o.Process)}
    method = find_method(client, data["method"])
    print(f"{len(descs)} processes in the open database, method {method.name}, {len(keys)} factors")
    gone = [k for k in keys if data["factors"][k]["id"] not in descs]
    if gone:
        sys.exit(f"the open database is not the one of {os.path.basename(path)}: {gone[:3]} not found")
    return client, descs, method


def time_three_runs(client, descs, method, data, keys, runs):
    t0 = time.time()
    simulate_impacts(client, descs[data["factors"][keys[0]]["id"]], method, 3)
    per = (time.time() - t0) / 3
    print(f"{per:.1f} s per run for {keys[0]}; {runs} runs of {len(keys)} factors: about "
          f"{per * runs * len(keys) / 3600:.1f} hours (other datasets can be faster or slower)")


def backup(path):
    """One copy of the factor file per day, before the first uncertainty is written into it."""
    os.makedirs("outputs", exist_ok=True)
    copy = os.path.join("outputs", "factors_before_uncertainty_" + time.strftime("%Y-%m-%d") + ".json")
    if not os.path.exists(copy):
        shutil.copy(path, copy)


def runs_done(factor):
    return min((u.get("n", 0) for u in (factor.get("uncertainty") or {}).values()), default=0)


def simulate_one(client, descs, method, factor, runs):
    """Run the simulation of one factor and write its spread into the factor. False when openLCA fails."""
    t0 = time.time()
    try:
        values = simulate_impacts(client, descs[factor["id"]], method, runs)
    except Exception as exc:  # keep going; the factor stays without uncertainty and is listed at the end
        print(f"!! {factor.get('process')}: {exc}")
        return False
    factor["uncertainty"] = {c: spread(v, factor["impacts"].get(c)) for c, v in values.items() if c in factor["impacts"]}
    factor["uncertainty_runs"] = time.strftime("%Y-%m-%d")
    factor["uncertainty_seconds"] = round(time.time() - t0, 1)
    return True


def save(data, path):
    """Written after every factor, through a temporary file: an interrupted run loses one factor at most."""
    with open(path + ".tmp", "w") as fh:
        json.dump(data, fh, indent=2)
    os.replace(path + ".tmp", path)


def main():
    args = parse_args()
    data = load_factors()
    path = data.pop("path")
    keys = keys_to_simulate(args, data, path)
    client, descs, method = open_database(args, data, path, keys)
    if args.time_only:
        return time_three_runs(client, descs, method, data, keys, args.runs)
    backup(path)
    todo = [k for k in keys if runs_done(data["factors"][k]) < args.runs]
    print(f"{len(keys) - len(todo)} already done, {len(todo)} to do")
    start = time.time()
    for i, key in enumerate(todo, 1):
        f = data["factors"][key]
        if not simulate_one(client, descs, method, f, args.runs):
            continue
        save(data, path)
        cc = f["uncertainty"].get("Climate change", {})
        left = (time.time() - start) / i * (len(todo) - i)
        print(f"ok {i}/{len(todo)} {key}: climate change gsd {cc.get('gsd')}, median/central {cc.get('median_ratio')} "
              f"({f['uncertainty_seconds']:.0f} s; about {left / 60:.0f} min left)")
    without = [k for k in keys if not (data["factors"][k].get("uncertainty") or {}).get("Climate change", {}).get("gsd")]
    print(f"done. Factors without a usable uncertainty for Climate change: {without or 'none'}")
    report(data, keys, os.path.join("outputs", "uncertainty_report.md"))


def report(data, keys, out):
    """What the simulation gave, factor by factor, for Climate change: the table the plan asks for (A3)."""
    rows, total = [], 0.0
    for k in keys:
        f = data["factors"][k]
        u = (f.get("uncertainty") or {}).get("Climate change") or {}
        total += f.get("uncertainty_seconds") or 0.0
        cell = lambda x: "" if x is None else f"{x:.3f}"  # noqa: E731
        rows.append(f"| {k} | {u.get('n', '')} | {cell(u.get('gsd'))} | {cell(u.get('median_ratio'))} | "
                    f"{cell(u.get('mean_ratio'))} | {u.get('other_sign', '')} | {f.get('uncertainty_seconds', '')} | "
                    f"{u.get('note', '')} |")
    gsd = [(data["factors"][k]["uncertainty"]["Climate change"]["gsd"], k) for k in keys
           if ((data["factors"][k].get("uncertainty") or {}).get("Climate change") or {}).get("gsd")]
    med = [abs(data["factors"][k]["uncertainty"]["Climate change"]["median_ratio"] - 1) for _, k in gsd]
    lines = ["# Uncertainty of the factors of the benchmark, Climate change", "",
             f"{len(gsd)} of {len(keys)} factors have a usable spread. Simulation time recorded: {total / 60:.1f} minutes.",
             (f"Geometric standard deviation from {min(gsd)[0]:.3f} ({min(gsd)[1]}) to {max(gsd)[0]:.3f} ({max(gsd)[1]}). "
              f"Largest distance between the median of the runs and the value BRANCH uses: {100 * max(med):.1f}%."
              if gsd else "No factor has a usable spread."), "",
             "| Factor | Runs | Geometric standard deviation | Median of the runs / value used | Mean / value used | "
             "Runs of the other sign | Seconds | Note |", "|---|---|---|---|---|---|---|---|"] + rows
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"report: {out}")


if __name__ == "__main__":
    main()

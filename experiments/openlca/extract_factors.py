"""Extract unit impact factors from openLCA, once (Step 2).

For every process the benchmark needs, builds a product system in openLCA,
calculates it with the chosen LCIA method and stores the impact per unit of
the process's reference flow (per kg, per kWh, per tkm, ...). The agent then
works on these factors only; it never calls openLCA in its Monte Carlo loop.

Requirements: openLCA 2.x open, the database selected (e.g. BAFU:2026 with the
openLCA LCIA Methods imported) and the IPC server running on port 8080.

    python experiments/openlca/extract_factors.py --methods            # list LCIA methods
    python experiments/openlca/extract_factors.py --find "packaging glass"
    python experiments/openlca/extract_factors.py --method "EF 3.1"   # extract all
    python experiments/openlca/extract_factors.py --update --specs aluminium_can_330ml beverage_carton_1l --region BR-AM

Output: data/factors/<database>_<method>.json (git ignored: the BAFU terms of
use do not allow redistributing the data, so every user extracts locally).
Source to cite: "Life Cycle Inventory database of the Swiss Federal
Administration, BAFU:20XY".
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import olca_ipc as ipc  # noqa: E402
import olca_schema as o  # noqa: E402

from branch import olca_extract as extract_module  # noqa: E402
from branch.olca_extract import (  # noqa: E402,F401
    LOCATION_PREFERENCE,
    PROCESSES,
    all_processes,
    citation_for,
    find_method,
    loc,
    match,
    norm,
    resolve,
    unit_impacts,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--methods", action="store_true", help="list LCIA methods and exit")
    ap.add_argument("--find", help="list processes whose name contains this text and exit")
    ap.add_argument("--method", default="EF 3.1")
    ap.add_argument("--map", default=None,
                    help="map of another database: a name in data/databases/ or a file (docs/BRING_YOUR_DATABASE.md)")
    ap.add_argument("--database", default=None, help="name written in the factor file (default: the one of the map)")
    ap.add_argument("--only", nargs="*", help="extract only these keys")
    ap.add_argument("--specs", nargs="+",
                    help="extract only the keys these products need (benchmark names or JSON files)")
    ap.add_argument("--all-grids", action="store_true",
                    help="also extract the medium voltage grid mix of every country in the database "
                         "(keys electricity_mv_<country code>)")
    ap.add_argument("--region", "--country", dest="region", default="PT",
                    help="region code for --specs (data/regions/)")
    ap.add_argument("--update", action="store_true",
                    help="keep factors already in the output file and add the new ones")
    args = ap.parse_args()
    if args.map:
        extract_module.use_database_map(args.map)
    args.database = args.database or extract_module.DATABASE_MAP["database"]

    client = ipc.Client(args.port)
    if args.methods:
        for d in sorted(client.get_descriptors(o.ImpactMethod), key=lambda d: d.name):
            print(d.name)
        return
    descs = all_processes(client)
    print(f"{len(descs)} processes in the open database")
    if args.find:
        for d in sorted(descs, key=lambda d: d.name):
            if norm(args.find) in norm(d.name):
                print(f"  {d.name}   [{getattr(d, 'location', '') or ''}]")
        return

    method = find_method(client, args.method)
    print(f"LCIA method: {method.name}")
    out = {"database": args.database, "method": method.name, "citation": citation_for(args.database),
           "extracted": time.strftime("%Y-%m-%d"), "factors": {}, "unresolved": {}}
    path = f"data/factors/{args.database}_{re.sub(r'[^A-Za-z0-9]+', '_', method.name)}.json"
    chosen = []                  # processes people chose by name stay in the file across full extractions
    if os.path.exists(path):
        with open(path) as fh:
            old = json.load(fh)
        if args.update:
            out["factors"] = old.get("factors", {})
        elif not (args.only or args.specs):
            chosen = [k for k in old.get("factors", {}) if k.startswith("proc:")]
    if args.all_grids:
        for d in descs:
            mm = extract_module.GRID_PATTERN.match((d.name or "").strip())
            if mm:
                PROCESSES.setdefault(f"electricity_mv_{mm.group(1)}", [d.name])
        print(f"{sum(k.startswith('electricity_mv_') for k in PROCESSES)} national grids found")
    if args.specs:
        from branch.builder import required_factor_keys
        needed = required_factor_keys(args.specs, args.region)
        unknown = [k for k in needed if k not in PROCESSES and not k.startswith("proc:")]
        if unknown:
            raise SystemExit(f"The map of the database (data/databases/) has no names for: {unknown}")
        keys = [k for k in needed if k not in out["factors"]]
    else:
        keys = args.only or [k for k in PROCESSES if k not in out["factors"]] + chosen
    for key in keys:
        ref, hits = resolve(descs, key, PROCESSES)
        if ref is None:
            out["unresolved"][key] = [h.name for h in hits[:15]]
            print(f"  ?  {key}: {len(hits)} candidates, choose one and write its exact name in the map of the database")
            for h in hits[:15]:
                print(f"       - {h.name}   [{loc(h)}]")
            continue
        t0 = time.perf_counter()
        try:
            out["factors"][key] = unit_impacts(client, ref, method)
            gwp = {k: v for k, v in out["factors"][key]["impacts"].items() if "climate" in k.lower()}
            print(f"  ok {key}: {ref.name} [{loc(ref)}]  {gwp}  ({time.perf_counter() - t0:.1f}s)")
        except Exception as exc:  # keep going, report at the end
            out["unresolved"][key] = [f"calculation failed: {exc}"]
            print(f"  !! {key}: {exc}")

    os.makedirs("data/factors", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nsaved {path}: {len(out['factors'])} factors, {len(out['unresolved'])} unresolved")
    if out["unresolved"] and (args.specs or args.only):
        for key, why in out["unresolved"].items():
            print(f"NOT READ: {key}: " + ("no process of the database has this exact name (a flow may have it; "
                                          "use --find to see the process names)" if not why else "; ".join(map(str, why))))
        sys.exit(1)


if __name__ == "__main__":
    main()

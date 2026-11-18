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
Source to cite: the citation in the map of the database (data/databases/); for BAFU:2026,
"Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026".
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import olca_ipc as ipc  # noqa: E402
import olca_schema as o  # noqa: E402

from branch import olca_extract  # noqa: E402
from branch.builder import required_factor_keys  # noqa: E402
from branch.olca_extract import all_processes, norm  # noqa: E402


def parse_args():
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
    return ap.parse_args()


def list_methods(client):
    for d in sorted(client.get_descriptors(o.ImpactMethod), key=lambda d: d.name):
        print(d.name)


def list_matching(descs, text):
    for d in sorted(descs, key=lambda d: d.name):
        if norm(text) in norm(d.name):
            print(f"  {d.name}   [{getattr(d, 'location', '') or ''}]")


def wanted_keys(args, descs, database_map):
    """The keys to read: the ones named, the ones the products need, or None for all of the map."""
    if not args.specs:
        return args.only or None
    known = set(database_map["datasets"])
    if args.all_grids:
        known |= set(olca_extract.grid_processes(descs, re.compile(database_map["grid_name_pattern"])))
    needed = required_factor_keys(args.specs, args.region)
    unknown = [k for k in needed if k not in known and not k.startswith("proc:")]
    if unknown:
        raise SystemExit(f"The map of the database (data/databases/) has no names for: {unknown}")
    return needed


def show(done, total, message):
    print(f"  [{done}/{total}] {message}")


def report(path, out, strict):
    """The last line every guide quotes, and, when keys were asked for by name, why one was not read."""
    for key, why in out["unresolved"].items():
        if why and not str(why[0]).startswith("calculation failed"):
            print(f"  ?  {key}: {len(why)} candidates, choose one and write its exact name in the map of the database")
            for name in why:
                print(f"       - {name}")
    print(f"\nsaved {path}: {len(out['factors'])} factors, {len(out['unresolved'])} unresolved")
    if out["unresolved"] and strict:
        for key, why in out["unresolved"].items():
            print(f"NOT READ: {key}: " + ("no process of the database has this exact name (a flow may have it; "
                                          "use --find to see the process names)" if not why else "; ".join(map(str, why))))
        sys.exit(1)


def main():
    args = parse_args()
    database_map = olca_extract.load_database_map(args.map)
    database = args.database or database_map["database"]
    client = ipc.Client(args.port)
    if args.methods:
        return list_methods(client)
    descs = all_processes(client)
    print(f"{len(descs)} processes in the open database")
    if args.find:
        return list_matching(descs, args.find)
    method = olca_extract.find_method(client, args.method)
    print(f"LCIA method: {method.name}")
    path = f"data/factors/{database}_{re.sub(r'[^A-Za-z0-9]+', '_', method.name)}.json"
    out = olca_extract.extract(client, path, method=args.method, database=database, all_grids=args.all_grids,
                               keys=wanted_keys(args, descs, database_map), update=args.update, progress=show,
                               keep_chosen=not (args.only or args.specs), database_map=database_map)
    report(path, out, strict=bool(args.specs or args.only))


if __name__ == "__main__":
    main()

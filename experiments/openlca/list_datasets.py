"""List every dataset in the open openLCA database, to grow the catalogue.

openLCA can assess any product whose processes exist in the database you
load; it does not have a fixed list of materials. This script writes that
list for the open database (BAFU:2026, or any other) to a CSV you can filter
in a spreadsheet, so you can see which materials, conversion processes,
transport modes, electricity mixes and disposal routes are available before
adding a material (data/materials/*.json) or a region (data/regions/*.json).

    python experiments/openlca/list_datasets.py                      # all processes
    python experiments/openlca/list_datasets.py --grep "disposal"    # only names containing a text
    python experiments/openlca/list_datasets.py --full               # also reference flow and unit (slower)

Output: outputs/datasets_<database>.csv with name, category, location, type
and, with --full, the reference flow, its unit and whether it is a waste flow.
Requires openLCA 2.x with the IPC server running (port 8080).
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import olca_ipc as ipc  # noqa: E402
import olca_schema as o  # noqa: E402

# Rough grouping by the first words of BAFU / ecoinvent v2 style names.
GROUPS = [
    ("disposal", ("disposal", "treatment of")),
    ("transport", ("transport",)),
    ("electricity", ("electricity",)),
    ("heat and fuels", ("heat", "natural gas", "diesel", "light fuel oil", "hard coal")),
    ("conversion", ("moulding", "extrusion", "rolling", "drawing", "forming", "thermoforming",
                    "injection", "blow", "printing", "welding")),
    ("packaging", ("packaging", "carton", "board", "bottle")),
]


def group(name):
    n = name.lower()
    for g, words in GROUPS:
        if any(w in n for w in words):
            return g
    return "materials and other"


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--grep", nargs="+", help="keep only names containing any of these texts")
    ap.add_argument("--full", action="store_true", help="read every process for its reference flow")
    ap.add_argument("--database", default="open_database")
    return ap.parse_args()


def main():
    args = parse_args()

    client = ipc.Client(args.port)
    descs = client.get_descriptors(o.Process)
    if args.grep:
        descs = [d for d in descs if any(g.lower() in (d.name or "").lower() for g in args.grep)]
    rows = []
    for i, d in enumerate(sorted(descs, key=lambda d: d.name or "")):
        row = {"group": group(d.name or ""), "name": d.name, "category": d.category or "",
               "location": getattr(d, "location", "") or "",
               "type": str(getattr(d, "process_type", "") or ""), "id": d.id}
        if args.full:
            p = client.get(o.Process, d.id)
            ref = next((e for e in p.exchanges or [] if e.is_quantitative_reference), None)
            row["reference_flow"] = ref.flow.name if ref and ref.flow else ""
            row["unit"] = ref.unit.name if ref and ref.unit else ""
            row["waste_flow"] = bool(ref and ref.flow and ref.flow.flow_type == o.FlowType.WASTE_FLOW)
            if i % 200 == 0:
                print(f"  {i}/{len(descs)}", flush=True)
        rows.append(row)

    os.makedirs("outputs", exist_ok=True)
    path = f"outputs/datasets_{args.database}.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["name"])
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["group"]] = counts.get(r["group"], 0) + 1
    print(f"{len(rows)} processes -> {path}")
    for g, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {g:22s} {n}")


if __name__ == "__main__":
    main()

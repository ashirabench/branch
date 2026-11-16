"""Check BRANCH against openLCA on every benchmark case (paper: Agreement with openLCA).

    python experiments/openlca/validate_openlca.py                 # 6 pairs x PT, DE, BR
    python experiments/openlca/validate_openlca.py --regions PT
    python experiments/openlca/validate_openlca.py --all-grids --pairs 1   # one pair in every country
                                                                   # (writes results/validation_all_grids.csv)
    python experiments/openlca/validate_openlca.py --specs data/examples/bag_in_box_3l.json glass_refillable_1l \
        --out paper/data/validation_corrugated_board.csv           # a product with an added material

For each case the resolved model (most probable value of every choice) is pushed to the
open openLCA database, openLCA builds and calculates the product systems, and the result
is compared with BRANCH's own sum of amount x unit factor. When a case differs by more
than 0.01%, every exchange is checked alone to name the cause. The pushed objects are
deleted afterwards (use --keep to leave them in the BRANCH folder).

Writes paper/data/validation_openlca.csv. Needs openLCA open with the IPC server on 8080.
"""
import argparse
import csv
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import olca_schema as o  # noqa: E402

from branch import olca_bridge  # noqa: E402
from branch.agent import run_agent  # noqa: E402
from branch.real_cases import compare  # noqa: E402

PRODUCTS = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "paper", "data", "validation_openlca.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", nargs="+", default=["PT", "DE", "BR"])
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--keep", action="store_true", help="keep the pushed processes in openLCA")
    ap.add_argument("--all-grids", action="store_true",
                    help="every country whose grid is in the factor file, plus the Brazilian subregions")
    ap.add_argument("--pairs", type=int, default=6, help="how many of the 6 product pairs per region")
    ap.add_argument("--out", default=None, help="output CSV")
    ap.add_argument("--specs", nargs=2, metavar=("A", "B"), default=None,
                    help="check this pair instead of the benchmark pairs: two product files or benchmark names")
    args = ap.parse_args()
    out_path = args.out or (os.path.join("results", "validation_all_grids.csv") if args.all_grids else OUT)
    pairs = list(itertools.combinations(PRODUCTS, 2))
    if args.pairs < 6:   # glass vs can first: it uses the most factors (glass, aluminium, washing, transport)
        pairs = [("glass_refillable_1l", "aluminium_can_330ml")] + [p for p in pairs if p != (
            "glass_refillable_1l", "aluminium_can_330ml")]
        pairs = pairs[:args.pairs]
    if args.specs:
        pairs = [tuple(args.specs)]
        if not args.out:
            sys.exit("--specs needs --out, so the benchmark table is not overwritten")
    if args.all_grids:
        from branch.real_cases import load_factors
        keys = load_factors()["factors"]
        args.regions = sorted(k[len("electricity_mv_"):] for k in keys
                              if k.startswith("electricity_mv_") and k != "electricity_mv_GLO")
        args.regions += ["BR-AM", "BR-N"]
        print(f"{len(args.regions)} regions x {len(pairs)} pairs")
    c = olca_bridge.client(args.port)
    try:
        c.get_descriptors(o.UnitGroup)
    except Exception:
        sys.exit("openLCA is not answering. In openLCA: open the database, then "
                 "Tools > Developer tools > IPC Server > Start.")
    rows, worst = [], 0.0
    for region in args.regions:
        for a, b in pairs:
            try:
                model = compare(a, b, region)
                result = run_agent(model, lambda name: None, n_samples=5000)
                out = olca_bridge.push_comparison(c, model, result)
            except Exception as exc:   # keep going: one broken region must not stop the audit
                rows.append({"region": region, "pair": f"{a} vs {b}", "product": "", "openLCA": "",
                             "BRANCH": "", "relative_difference": "", "cause": f"error: {exc}"})
                print(f"{region}  ERROR {exc}")
                continue
            for label, chk in out["check"].items():
                rel = chk["relative_difference"]
                worst = max(worst, rel or 0.0)
                cause = ""
                if rel and rel > 1e-4:
                    diag = olca_bridge.diagnose_in_openlca(c, model, result, labels=[label])
                    cause = "; ".join(f"{k} x{ol / br:.3g}" for k, ol, br, r in diag.get(label, [])
                                      if r and r > 1e-4 and br)
                rows.append({"region": region, "pair": f"{a} vs {b}", "product": label,
                             "openLCA": chk["openLCA"], "BRANCH": chk["BRANCH"],
                             "relative_difference": rel, "cause": cause})
                print(f"{region}  {label:28s} openLCA {chk['openLCA']:.6g}  BRANCH {chk['BRANCH']:.6g}  "
                      f"rel {rel:.2g}  {cause}")
            if not args.keep:
                for ref in out["systems"] + out["processes"] + out.get("flows", []):
                    try:
                        c.delete(ref)
                    except Exception:
                        pass
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    errors = [r for r in rows if str(r["cause"]).startswith("error")]
    checked = len(rows) - len(errors)
    print(f"\n{checked} products checked, largest relative difference {worst:.2g}. Saved {os.path.abspath(out_path)}")
    if errors:
        sys.exit(f"{len(errors)} comparison(s) could not be checked: see the rows marked error in the table.")


if __name__ == "__main__":
    main()

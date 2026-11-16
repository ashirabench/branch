"""Check every material added in data/materials/ against openLCA.

    python experiments/openlca/validate_materials.py              # PT, DE, BR
    python experiments/openlca/validate_materials.py --regions PT

For each example product in data/examples/ and each dataset option of its added material,
the product is compared with the benchmark PET bottle, the resolved model is pushed to the
open openLCA database, openLCA builds and calculates the product systems, and its result is
compared with BRANCH's own sum of amount x unit factor (same check as validate_openlca.py).
A material whose factors are not in the factor file yet is reported and skipped.

Writes paper/data/validation_new_materials.csv. Needs openLCA open with the IPC server on 8080.
"""
import argparse
import csv
import glob
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, ROOT)

import olca_schema as o  # noqa: E402

from branch import catalogue as cat  # noqa: E402
from branch import olca_bridge  # noqa: E402
from branch.agent import run_agent  # noqa: E402
from branch.real_cases import compare, load_factors  # noqa: E402

REFERENCE = "pet_bottle_1l"
OUT = os.path.join(ROOT, "paper", "data", "validation_new_materials.csv")
FIELDS = ["material", "dataset", "region", "example", "product", "openLCA", "BRANCH", "relative_difference", "cause"]


def variants(added):
    """(example file, spec, material id, dataset label): one per dataset option of each added material."""
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "examples", "*.json"))):
        with open(path) as fh:
            spec = json.load(fh)
        # examples described only by processes of the database have no component: nothing to do here
        for mid in sorted({c["material"] for c in spec.get("components", [])} & set(added)):
            for label in added[mid]["datasets"]:
                v = json.loads(json.dumps(spec))
                v.setdefault("materials", {}).setdefault(mid, {})["dataset"] = label
                yield os.path.basename(path), v, mid, label


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", nargs="+", default=["PT", "DE", "BR"])
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--keep", action="store_true", help="keep the pushed processes in openLCA")
    args = ap.parse_args()
    added = {k: v for k, v in cat.load_materials().items() if k not in cat.MATERIALS}
    ready = cat.split_by_factors(load_factors())[0]
    c = olca_bridge.client(args.port)
    try:
        c.get_descriptors(o.UnitGroup)
    except Exception:
        sys.exit("openLCA is not answering. In openLCA: open the database, then "
                 "Tools > Developer tools > IPC Server > Start.")
    rows, worst = [], 0.0
    for example, spec, mid, label in variants(added):
        base = {"material": mid, "dataset": label, "example": example}
        if mid not in ready:
            rows.append({**base, "region": "", "product": "", "openLCA": "", "BRANCH": "",
                         "relative_difference": "", "cause": "skipped: factors not extracted"})
            print(f"{mid:18s} {label:38s} SKIPPED, factors not extracted")
            continue
        for region in args.regions:
            try:
                model = compare(spec, REFERENCE, region)
                result = run_agent(model, lambda name: None, n_samples=5000)
                out = olca_bridge.push_comparison(c, model, result)
            except Exception as exc:
                rows.append({**base, "region": region, "product": "", "openLCA": "", "BRANCH": "",
                             "relative_difference": "", "cause": f"error: {exc}"})
                print(f"{mid:18s} {label:38s} {region}  ERROR {exc}")
                continue
            for product, chk in out["check"].items():
                if product != model.label_a:          # the PET bottle is already in the benchmark table
                    continue
                rel = chk["relative_difference"]
                worst = max(worst, rel or 0.0)
                cause = ""
                if rel and rel > 1e-4:
                    diag = olca_bridge.diagnose_in_openlca(c, model, result, labels=[product])
                    cause = "; ".join(f"{k} x{ol / br:.3g}" for k, ol, br, r in diag.get(product, [])
                                      if r and r > 1e-4 and br)
                rows.append({**base, "region": region, "product": product, "openLCA": chk["openLCA"],
                             "BRANCH": chk["BRANCH"], "relative_difference": rel, "cause": cause})
                print(f"{mid:18s} {label:38s} {region}  openLCA {chk['openLCA']:.6g}  BRANCH {chk['BRANCH']:.6g}  "
                      f"rel {rel:.2g}  {cause}")
            if not args.keep:
                for ref in out["systems"] + out["processes"]:
                    try:
                        c.delete(ref)
                    except Exception:
                        pass
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} rows, largest relative difference {worst:.2g}. Saved {os.path.abspath(OUT)}")
    bad = [r for r in rows if str(r["cause"]).startswith(("error", "skipped"))]
    if bad:
        sys.exit(f"{len(bad)} row(s) could not be checked: see the rows marked error or skipped in the table.")


if __name__ == "__main__":
    main()

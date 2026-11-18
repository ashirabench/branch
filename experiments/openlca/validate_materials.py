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
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path[:0] = [ROOT, HERE]

from checks import DIFFERENT, cause_of, connect, remove, save  # noqa: E402

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


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", nargs="+", default=["PT", "DE", "BR"])
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--keep", action="store_true", help="keep the pushed processes in openLCA")
    return ap.parse_args()


def unchecked(base, region, cause):
    return {**base, "region": region, "product": "", "openLCA": "", "BRANCH": "", "relative_difference": "",
            "cause": cause}


def check_variant(c, spec, base, region, keep):
    """The row of one example with one dataset in one region, against the reference bottle."""
    tag = f"{base['material']:18s} {base['dataset']:38s} {region}"
    try:
        model = compare(spec, REFERENCE, region)
        result = run_agent(model, lambda name: None, n_samples=5000)
        out = olca_bridge.push_comparison(c, model, result)
    except Exception as exc:       # keep going: one example that fails must not stop the others
        print(f"{tag}  ERROR {exc}")
        return [unchecked(base, region, f"error: {exc}")]
    product, chk = model.label_a, out["check"][model.label_a]     # the PET bottle is already in the benchmark table
    rel = chk["relative_difference"]
    cause = cause_of(c, model, result, product) if rel and rel > DIFFERENT else ""
    print(f"{tag}  openLCA {chk['openLCA']:.6g}  BRANCH {chk['BRANCH']:.6g}  rel {rel:.2g}  {cause}")
    if not keep:
        remove(c, out)
    return [{**base, "region": region, "product": product, "openLCA": chk["openLCA"],
             "BRANCH": chk["BRANCH"], "relative_difference": rel, "cause": cause}]


def main():
    args = parse_args()
    added = {k: v for k, v in cat.load_materials().items() if k not in cat.MATERIALS}
    ready = cat.split_by_factors(load_factors())[0]
    c = connect(args.port)
    rows = []
    for example, spec, mid, label in variants(added):
        base = {"material": mid, "dataset": label, "example": example}
        if mid not in ready:
            rows.append(unchecked(base, "", "skipped: factors not extracted"))
            print(f"{mid:18s} {label:38s} SKIPPED, factors not extracted")
            continue
        for region in args.regions:
            rows += check_variant(c, spec, base, region, args.keep)
    save(rows, OUT, FIELDS)
    worst = max((r["relative_difference"] or 0.0 for r in rows if r["product"]), default=0.0)
    print(f"\n{len(rows)} rows, largest relative difference {worst:.2g}. Saved {os.path.abspath(OUT)}")
    bad = [r for r in rows if str(r["cause"]).startswith(("error", "skipped"))]
    if bad:
        sys.exit(f"{len(bad)} row(s) could not be checked: see the rows marked error or skipped in the table.")


if __name__ == "__main__":
    main()

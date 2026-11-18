"""Factor file of the second database test: BAFU:2026 with the factors that ELCD 3.2 has replaced.

    python experiments/data/make_hybrid_factors.py                 # the 21 mapped factors come from ELCD
    python experiments/data/make_hybrid_factors.py --replace none  # placebo: nothing replaced
    python experiments/data/make_hybrid_factors.py --climate ipcc2021   # ELCD climate change by IPCC 2021

Writes data/factors_second/<name>.json (never data/factors/, where the newest file is the default
of every other command; the folder is not in git because the file carries BAFU values). To use it:

    BRANCH_FACTORS=data/factors_second/hybrid_elcd32.json python examples/demo_cli.py --region PT

A replaced factor keeps only the categories computed for ELCD (Climate change and Acidification),
so asking the hybrid file for any other category fails instead of mixing two databases silently.
"""
import argparse
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
SECOND = os.path.join(ROOT, "data", "second_database")
CATEGORIES = ("Climate change", "Acidification")
IPCC = "Climate change (IPCC 2021 GWP 100)"


def hybrid(base, elcd, replace="all", climate="ef30"):
    """base: a BRANCH factor file (dict); elcd: data/second_database/elcd32_factors.json (dict)."""
    out = copy.deepcopy(base)
    out.pop("path", None)
    swapped = []
    if replace == "all":
        for key, f in elcd["factors"].items():
            if key not in out["factors"]:
                continue                               # a factor this BAFU file never extracted
            old = out["factors"][key]
            if old["unit"] != f["unit"]:
                raise ValueError(f"{key}: unit {old['unit']} in the base file, {f['unit']} in ELCD")
            impacts = {c: f["impacts"][c] for c in CATEGORIES}
            if climate == "ipcc2021":
                impacts["Climate change"] = f["impacts"][IPCC]
            out["factors"][key] = {"process": f["process"], "id": f["id"], "location": f["location"],
                                   "unit": f["unit"], "flow": f["process"], "impacts": impacts,
                                   "database": "ELCD 3.2", "owner": f["owner"]}
            swapped.append(key)
        out["database"] = f"{base.get('database', 'bafu2026')} with {len(swapped)} factors from ELCD 3.2"
        out["method"] = f"{base.get('method', '')}; ELCD factors by " + \
                        ("IPCC 2021 GWP 100" if climate == "ipcc2021" else "EF 3.0 Method (adapted)")
        out["citation"] = f"{base.get('citation', '')}; {elcd['citation']}"
        out["replaced_by_elcd"] = sorted(swapped)
    return out


def main():
    from branch.real_cases import load_factors
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--replace", default="all", choices=["all", "none"])
    ap.add_argument("--climate", default="ef30", choices=["ef30", "ipcc2021"])
    ap.add_argument("--base", default=None, help="BAFU factor file (default: the newest in data/factors)")
    args = ap.parse_args()
    env = os.environ.pop("BRANCH_FACTORS", None)       # the base is always the BAFU file
    base = load_factors(args.base)
    if env:
        os.environ["BRANCH_FACTORS"] = env
    with open(os.path.join(SECOND, "elcd32_factors.json"), encoding="utf-8") as fh:
        elcd = json.load(fh)
    data = hybrid(base, elcd, args.replace, args.climate)
    name = "placebo_none" if args.replace == "none" else "hybrid_elcd32" + ("_ipcc2021" if args.climate == "ipcc2021" else "")
    out_dir = os.path.join(ROOT, "data", "factors_second")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    print(f"wrote {path}: {len(data.get('replaced_by_elcd', []))} factors from ELCD 3.2, "
          f"{len(data['factors']) - len(data.get('replaced_by_elcd', []))} from the base file")


if __name__ == "__main__":
    main()

"""Unit audit of the extracted factors (no openLCA needed).

    python experiments/audit_factors.py

BRANCH multiplies every factor by an amount in a fixed unit: kWh for electricity,
t*km for transport, MJ for heat, items for a pallet and kg for everything else. A
factor extracted per another unit (the MJ against kWh error found in the validation)
is wrong by a constant, so this script checks the reference unit of every factor,
flags empty or non positive climate results, and says which factors the openLCA
validation of the benchmark products covers. Writes results/factor_audit.csv.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from branch.builder import required_factor_keys  # noqa: E402
from branch.real_cases import load_factors  # noqa: E402

PRODUCTS = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
EXPECTED = [  # (key pattern, accepted unit names in openLCA)
    (r"^electricity_", {"kWh"}),
    (r"^(lorry_|transport_)", {"t*km", "tkm", "t km"}),
    (r"^heat_", {"MJ"}),
    (r"^eur_pallet$", {"Item(s)", "Items", "Item"}),
    (r".*", {"kg"}),
]


def expected_units(key):
    for pat, units in EXPECTED:
        if re.search(pat, key):
            return units
    return {"kg"}


def main():
    data = load_factors()
    factors = data["factors"]
    covered = set()
    for region in ("PT", "DE", "BR"):
        covered |= set(required_factor_keys(PRODUCTS, region))
    rows, bad = [], 0
    for key in sorted(factors):
        f = factors[key]
        unit = f.get("unit")
        ok_unit = unit in expected_units(key)
        climate = f.get("impacts", {}).get("Climate change")
        ok_value = climate is not None and climate > 0
        problem = []
        if not ok_unit:
            problem.append(f"unit {unit!r}, expected {sorted(expected_units(key))}")
        if not ok_value:
            problem.append(f"climate change {climate!r}")
        bad += bool(problem)
        rows.append({"key": key, "process": f.get("process"), "location": f.get("location"),
                     "unit": unit, "climate_change": climate,
                     "validated_in_openLCA": key in covered, "problem": "; ".join(problem)})
    os.makedirs("results", exist_ok=True)
    out = os.path.join("results", "factor_audit.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} factors, {bad} with a problem, "
          f"{sum(r['validated_in_openLCA'] for r in rows)} covered by the 36 product validation.")
    for r in rows:
        if r["problem"]:
            print(f"  !! {r['key']}: {r['problem']}")
    print(f"Not yet covered by an openLCA check: "
          f"{', '.join(r['key'] for r in rows if not r['validated_in_openLCA'] and not r['key'].startswith('electricity_mv_'))}"
          f" and {sum(1 for r in rows if not r['validated_in_openLCA'] and r['key'].startswith('electricity_mv_'))} national grids.")
    print(f"Saved {os.path.abspath(out)}")


if __name__ == "__main__":
    main()

"""The model builder gives exactly the models it gave before it was split into small functions.

For a set of comparisons with the illustrative factors (branch/demo_factors.py, no licensed value), the
names and order of the choices, their priors, the terms, the Monte Carlo difference and the inventory
written to openLCA are reduced to one line each and compared with tests/golden/builder.json, which was
written by the code of 18 November 2026 before the split. The order in which choices are created is the
order of the columns of the draws, so a change there changes every result: this test is what catches it.

To accept a change made on purpose:  python tests/test_builder_golden.py --write
"""
import hashlib
import itertools
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
GOLDEN = os.path.join(HERE, "golden", "builder.json")
BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]


def _h(data):
    return hashlib.sha256(data).hexdigest()[:16]


def _line(model):
    from branch.montecarlo import State
    state = State(model, model.sample(2000, 7))
    choices = [(c.name, c.kind, c.source, c.question, bool(c.value_laden),
                _h(np.asarray(c.ppf(np.linspace(0.01, 0.99, 25))).astype(float).round(12).tobytes()))
               for c in model.choices]
    world = {c.name: float(np.asarray(c.ppf(np.array([0.5])))[0]) for c in model.choices}
    inventory = [(t.name, sorted((k, round(float(a), 10)) for k, a in t.inventory(world).items()))
                 for t in model.terms if t.inventory]
    return {"choices": [c[0] for c in choices],
            "priors": _h(json.dumps(choices).encode()),
            "terms": [(t.name, list(t.deps), t.sign) for t in model.terms],
            "delta": [round(float(x), 9) for x in np.percentile(np.asarray(state.delta, dtype=float), [5, 50, 95])],
            "inventory": _h(json.dumps(inventory, sort_keys=True).encode())}


def cases():
    from branch.builder import build_model
    from branch.demo_factors import demo_factors
    factors = demo_factors()
    out = {}
    for a, b in itertools.combinations(BENCH, 2):
        for region in ("PT", "DE", "BR"):
            out[f"{a} | {b} | {region}"] = _line(build_model(a, b, region, factors=factors))
        out[f"{a} | {b} | PT | cff"] = _line(build_model(a, b, "PT", factors=factors, system_model="cff"))
        out[f"{a} | {b} | PT | distance known"] = _line(
            build_model(a, b, "PT", factors=factors, shared={"distribution_km": 120}))
    return json.loads(json.dumps(out))


def test_the_builder_gives_the_models_it_gave_before():
    with open(GOLDEN, encoding="utf-8") as fh:
        expected = json.load(fh)
    got = cases()
    assert set(got) == set(expected)
    for name in expected:
        for part in ("choices", "terms", "priors", "inventory"):
            assert got[name][part] == expected[name][part], f"{name}: {part} changed"
        assert np.allclose(got[name]["delta"], expected[name]["delta"], rtol=1e-9, atol=0), f"{name}: the result changed"


if __name__ == "__main__" and "--write" in sys.argv:
    os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
    with open(GOLDEN, "w", encoding="utf-8") as fh:
        json.dump(cases(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("written", GOLDEN)

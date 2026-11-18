"""The model builder gives exactly the models it gave before it was split into small functions.

For a set of comparisons with the illustrative factors (branch/demo_factors.py, no licensed value), the
names and order of the choices, their texts and quantiles, the terms, the Monte Carlo difference and the
inventory written to openLCA are compared with tests/golden/builder.json. The file was first written by the
code of 18 November 2026 before the split; it was written again the same day with numbers in place of
digests, by code that the first file still accepted, because Windows computes the last digit of some
quantiles differently and a digest cannot allow for that. Numbers are compared to a relative 1e-9. The
order in which choices are created is the order of the columns of the draws, so a change there changes
every result: this test is what catches it.

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
QUANTILES = np.array([0.01, 0.25, 0.5, 0.75, 0.99])
BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]


def _h(data):
    return hashlib.sha256(data).hexdigest()[:16]


def _line(model):
    from branch.montecarlo import State
    state = State(model, model.sample(2000, 7))
    texts = [(c.name, c.kind, c.source, c.question, bool(c.value_laden)) for c in model.choices]
    world = {c.name: float(np.asarray(c.ppf(np.array([0.5])))[0]) for c in model.choices}
    inventory = [[t.name, k, float(a)] for t in model.terms if t.inventory
                 for k, a in sorted(t.inventory(world).items())]
    return {"choices": [c.name for c in model.choices],
            "texts": _h(json.dumps(texts).encode()),
            "quantiles": [[float(q) for q in np.asarray(c.ppf(QUANTILES), dtype=float)] for c in model.choices],
            "terms": [(t.name, list(t.deps), t.sign) for t in model.terms],
            "delta": [float(x) for x in np.percentile(np.asarray(state.delta, dtype=float), [5, 50, 95])],
            "inventory": inventory}


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
        g, e = got[name], expected[name]
        for part in ("choices", "texts", "terms"):
            assert g[part] == e[part], f"{name}: {part} changed"
        assert [x[:2] for x in g["inventory"]] == [x[:2] for x in e["inventory"]], f"{name}: the exchanges changed"
        for part, a, b in (("quantiles", g["quantiles"], e["quantiles"]), ("delta", g["delta"], e["delta"]),
                           ("inventory", [x[2] for x in g["inventory"]], [x[2] for x in e["inventory"]])):
            assert np.allclose(np.array(a, dtype=float), np.array(b, dtype=float), rtol=1e-9, atol=1e-12), \
                f"{name}: the {part} changed"


if __name__ == "__main__" and "--write" in sys.argv:
    os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
    with open(GOLDEN, "w", encoding="utf-8") as fh:
        json.dump(cases(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("written", GOLDEN)

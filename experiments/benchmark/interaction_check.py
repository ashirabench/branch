"""How much of what a choice does to the verdict does the first order score miss?

    BRANCH_FACTORS=data/factors/<file>.json python experiments/benchmark/interaction_check.py

For every benchmark case, at the prior, and for every open choice j, two indices of the verdict V (1 when A
has the lower impact): the first order index S_j, the share of the variance of V that the answer to j
removes on its own, which is what decision flip ranks by; and the total index T_j, the share that remains
while j is unknown and everything else is known. T_j - S_j is what j does only together with other choices.
A choice with S_j near 0 and T_j large matters and is invisible to the ranking. Both come from the same
draws: the other choices keep their values while j runs over its represented answers.
"""
import csv
import itertools
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from branch.montecarlo import State  # noqa: E402
from branch.real_cases import compare  # noqa: E402

E = os.path.join(ROOT, "data", "examples")
BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
FAMILIES = [("ps_cup_05l.json", "pla_cup_05l.json"), ("ps_cup_05l.json", "eps_cup_03l.json"),
            ("pla_cup_05l.json", "eps_cup_03l.json"), ("pp_bottle_1l.json", "pet_bottle_1l"),
            ("pvc_bottle_1l.json", "pet_bottle_1l"), ("pp_bottle_1l.json", "pvc_bottle_1l.json"),
            ("steel_can_05l.json", "aluminium_can_330ml"), ("carton_box_1l.json", "paper_bag_1l.json"),
            ("bag_in_box_3l.json", "beverage_carton_1l"), ("carton_box_1l.json", "beverage_carton_1l")]


def indices(state):
    """{choice: (S, T)} for the verdict at this state; ({} , p) when the verdict has no variance."""
    v = (state.delta < 0).astype(float)
    p = float(v.mean())
    var = p * (1.0 - p)
    out = {}
    if var < 1e-12:
        return out, p
    for name in state.open:
        d, w = state.conditional_deltas(name)
        vk = (d < 0).astype(float)                       # (K, N): the verdict if j took answer k
        w = np.asarray(w, dtype=float).reshape(-1, 1)
        mean_i = (w * vk).sum(axis=0)                    # E[V | everything but j], per draw
        s = float((w[:, 0] * (vk.mean(axis=1) - (w[:, 0] * vk.mean(axis=1)).sum()) ** 2).sum()) / var
        t = float(((w * vk ** 2).sum(axis=0) - mean_i ** 2).mean()) / var
        out[name] = (s, t)
    return out, p


def path(x):
    return os.path.join(E, x) if x.endswith(".json") else x


def main(n=20000, seed=0):
    rows = []
    pairs = [("bench", a, b) for a, b in itertools.combinations(BENCH, 2)] + [("families", a, b) for a, b in FAMILIES]
    for (group, a, b), region in itertools.product(pairs, ("PT", "DE", "BR")):
        model = compare(path(a), path(b), region)
        ind, p = indices(State(model, model.sample(n, seed)))
        case = f"{os.path.basename(a).replace('.json', '')}_vs_{os.path.basename(b).replace('.json', '')}_{region}"
        for name, (s, t) in ind.items():
            rows.append({"group": group, "case": case, "p_a_lower": round(p, 4), "choice": name,
                         "first_order": round(s, 5), "total": round(t, 5), "interaction": round(t - s, 5)})
        if not ind:
            rows.append({"group": group, "case": case, "p_a_lower": round(p, 4), "choice": "", "first_order": "",
                         "total": "", "interaction": ""})
    out = os.path.join(ROOT, "results", "interactions", "interaction_check.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("saved", out, len(rows), "rows")


if __name__ == "__main__":
    main()

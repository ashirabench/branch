"""What the result rests on, for the report (Step 7, proposal section 4.4).

reversals    the smallest change in a single choice that reverses the
             verdict, with every other answer kept and every other open
             choice kept as a distribution.
stages       mean impact of each alternative by life cycle stage (material,
             end of life, transport, washing), so a firm sees how much
             disposal weighs in the result.
point_world  the single world written to openLCA: the human's answers, the
             most probable option of open categorical choices and the median
             of open continuous ones.
"""
import numpy as np

from .backend import to_numpy
from .montecarlo import State, p_a_lower


def _state(model, result):
    st = State(model, model.sample(result["n_samples"], result["seed"]))
    for name, value in result["fixed"].items():
        if name in st.open:
            st.fix(name, value)
    return st


def _current(choice, result):
    if choice.name in result["fixed"]:
        return float(result["fixed"][choice.name])
    if choice.kind == "categorical":
        return float(np.argmax(choice.probs))
    return float(choice._frozen().ppf(0.5))


def point_world(model, result):
    return {c.name: _current(c, result) for c in model.choices}


def reversals(model, result, grid=49, top=5):
    """Single choice changes that reverse the verdict, smallest first.

    Distance is measured in prior quantiles (0 to 1) for continuous choices,
    so a recycling rate and a distance in km are comparable; any other option
    of a categorical choice counts as distance 1. Returns a list of dicts:
    name, kind, now, reverses_at (value or option label), distance, p_after.
    """
    xp = model.xp
    st = _state(model, result)
    a_lower = float(p_a_lower(st.delta)) >= 0.5
    found = []
    for c in model.choices:
        if not c.askable:                          # nobody can change the uncertainty of the database
            continue
        now = _current(c, result)
        if c.kind == "categorical":
            vals = np.arange(len(c.labels), dtype=float)
        else:
            q = np.linspace(0.01, 0.99, grid)
            vals = np.unique(np.append(c._frozen().ppf(q), now))
        V = xp.asarray(vals, dtype=xp.float64).reshape(-1, 1)
        d = xp.broadcast_to(st.delta, (V.shape[0], st.delta.shape[0])).copy()
        for m in model.terms_of[c.name]:
            d += model.term_value(m, st.S, override=(c.name, V)) - st.contrib[m]
        p = to_numpy(p_a_lower(d))
        flips = (p >= 0.5) != a_lower
        if not flips.any():
            continue
        if c.kind == "categorical":
            k = next(i for i in range(len(vals)) if flips[i] and vals[i] != now)
            found.append({"name": c.name, "kind": c.kind, "now": c.labels[int(now)],
                          "reverses_at": c.labels[k], "distance": 1.0, "p_after": float(p[k])})
            continue
        F = c._frozen().cdf
        cand = [i for i in range(len(vals)) if flips[i]]
        k = min(cand, key=lambda i: abs(F(vals[i]) - F(now)))
        found.append({"name": c.name, "kind": c.kind, "now": now, "reverses_at": float(vals[k]),
                      "distance": float(abs(F(vals[k]) - F(now))), "p_after": float(p[k])})
    found.sort(key=lambda r: r["distance"])
    return found[:top]


def stages(model, result):
    """{alternative: {stage: mean impact per functional unit}} from the final state.

    The stage is the last part of the term name (builder.py names terms
    "<product>.<component>.material", ".end_of_life", ".transport",
    ".washing").
    """
    st = _state(model, result)
    out = {model.label_a: {}, model.label_b: {}}
    for i, t in enumerate(model.terms):
        side = out[model.label_a if t.sign > 0 else model.label_b]
        stage = t.name.rsplit(".", 1)[-1]
        side[stage] = side.get(stage, 0.0) + float(to_numpy(st.contrib[i]).mean()) * (1 if t.sign > 0 else -1)
    return out


def indicators(model, result):
    """Every impact category of the method, with the answers of this session.

    Returns a list of dicts: category, name, unit, mean_a, mean_b, lower
    (label of the alternative with the lower mean), p_a_lower and agrees
    (same winner as the verdict of the session). Each category is rebuilt
    with the same products and region and sampled with the same seed, so the
    open choices see the same draws in every category.
    """
    from .builder import rebuild
    from .indicators import available, describe
    out = []
    for cat in available(model.factor_data):
        m = model if cat == model.meta.get("category") else rebuild(model, cat)
        st = _state(m, result)
        a_terms = [i for i, t in enumerate(m.terms) if t.sign > 0]
        b_terms = [i for i, t in enumerate(m.terms) if t.sign < 0]
        ia = float(to_numpy(sum(st.contrib[i] for i in a_terms)).mean())
        ib = float(-to_numpy(sum(st.contrib[i] for i in b_terms)).mean())
        p = float(p_a_lower(st.delta))
        name, unit = describe(cat)
        out.append({"category": cat, "name": name, "unit": unit, "mean_a": ia, "mean_b": ib,
                    "lower": m.label_a if p >= 0.5 else m.label_b, "p_a_lower": p,
                    "agrees": (p >= 0.5) == result["verdict_a_lower"]})
    return out

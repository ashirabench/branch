"""Development and benchmark cases.

toy_packaging()   PET single use vs refillable glass, 1 L delivered.
                  ALL NUMBERS ARE PLACEHOLDERS for development only, not
                  taken from any database. Replace with unit impact factors
                  extracted from openLCA (EF reference package) before any
                  result is reported.
synthetic_lca(J)  LCA like random model: non negative impacts, each choice
                  adds to A or to B (one sided effects). Scalability runs.
synthetic(J)      symmetric random additive model, for robustness checks.
draw_truth(model) one plausible expert world drawn from the priors.
"""
import numpy as np

from .backend import to_numpy
from .beliefs import Choice
from .lca_model import Model, Term


def toy_packaging(xp=np):
    T = lambda vals: xp.asarray(vals, dtype=xp.float64)  # noqa: E731
    idx = lambda v: xp.asarray(v).astype(int)  # noqa: E731
    pet_dataset_f = T([2.15, 2.30, 2.50])   # kg CO2e / kg virgin PET (placeholder)
    pet_eol_f = T([0.05, 2.20, 0.00])       # landfill, incineration, recycling cut off
    capital_f = T([0.0, 0.004])             # exclude, include (per use)
    m_pet, m_glass = 0.035, 0.50            # kg packaging per 1 L (placeholder)

    choices = [
        Choice("pet_dataset", "categorical",
               {"PET granulate EU avg": 0.4, "PET bottle grade": 0.4, "PET amorphous": 0.2},
               "EF reference package candidates", question="Which dataset represents your PET?"),
        Choice("pet_recycled", "continuous", ("uniform", {"low": 0.0, "high": 0.5}),
               "supplier declaration", question="Recycled content of the PET bottle (0 to 1)?"),
        Choice("pet_eol", "categorical", {"landfill": 0.3, "incineration": 0.3, "recycling (cut off)": 0.4},
               "Eurostat env_waspac PT", question="End of life model for PET?"),
        Choice("glass_trips", "continuous", ("triangular", {"low": 5, "mode": 15.5, "high": 40}),
               "sector data", question="How many times is the glass bottle refilled?"),
        Choice("glass_km", "continuous", ("uniform", {"low": 50, "high": 400}),
               "EF transport defaults", question="One way distribution distance for glass (km)?"),
        Choice("wash_kwh", "continuous", ("uniform", {"low": 0.01, "high": 0.05}),
               "sector data", question="Washing electricity per bottle (kWh)?"),
        Choice("grid_ef", "continuous", ("lognormal", {"median": 0.20, "sigma": 0.25}),
               "ENTSO-E", question="Grid emission factor at the bottler (kg CO2e/kWh)?"),
        Choice("capital_goods", "categorical", {"exclude": 0.5, "include": 0.5},
               "Frischknecht et al. 2007", value_laden=True,
               question="Include capital goods (the washing line) in the system boundary?"),
    ]
    terms = [
        Term("pet_material", ["pet_dataset", "pet_recycled"],
             lambda xp, v: m_pet * ((1 - v["pet_recycled"]) * pet_dataset_f[idx(v["pet_dataset"])]
                                    + v["pet_recycled"] * 0.9)),
        Term("pet_eol", ["pet_eol"], lambda xp, v: m_pet * pet_eol_f[idx(v["pet_eol"])]),
        Term("pet_transport", [], lambda xp, v: m_pet * 200 / 1000 * 0.10),
        Term("glass_material", ["glass_trips"], lambda xp, v: m_glass * 0.9 / v["glass_trips"], sign=-1),
        Term("glass_transport", ["glass_km"], lambda xp, v: m_glass * 2 * v["glass_km"] / 1000 * 0.10, sign=-1),
        Term("glass_washing", ["wash_kwh", "grid_ef"], lambda xp, v: v["wash_kwh"] * v["grid_ef"], sign=-1),
        Term("glass_capital", ["capital_goods"], lambda xp, v: capital_f[idx(v["capital_goods"])], sign=-1),
    ]
    return Model(choices, terms, xp, label_a="PET", label_b="Glass")


def _dirichlet_prior(rng, k, conc):
    p = rng.dirichlet(np.ones(k) * conc)
    return {f"o{i}": float(p[i]) for i in range(k)}


def synthetic_lca(J, seed=0, xp=np):
    rng = np.random.default_rng(seed)
    choices, terms = [], []
    for j in range(J):
        name = f"c{j}"
        side = 1.0 if j % 2 == 0 else -1.0
        scale = float(rng.lognormal(-3, 1.2))
        if rng.random() < 0.4:
            k = int(rng.integers(2, 5))
            table = xp.asarray(np.sort(rng.lognormal(0, 1, k)) * scale)
            choices.append(Choice(name, "categorical", _dirichlet_prior(rng, k, 2.0), "synthetic"))
            terms.append(Term(name, [name], lambda xp_, v, n=name, t=table: t[xp_.asarray(v[n]).astype(int)],
                              sign=side))
        else:
            sigma = float(rng.uniform(0.2, 1.0))
            choices.append(Choice(name, "continuous", ("lognormal", {"median": 1.0, "sigma": sigma}), "synthetic"))
            terms.append(Term(name, [name], lambda xp_, v, n=name, s=scale: s * v[n], sign=side))
    return Model(choices, terms, xp)


def synthetic(J, seed=0, xp=np, frac_cat=0.4):
    rng = np.random.default_rng(seed)
    choices, terms = [], []
    for j in range(J):
        name = f"c{j}"
        if rng.random() < frac_cat:
            k = int(rng.integers(2, 5))
            choices.append(Choice(name, "categorical", _dirichlet_prior(rng, k, 1.0), "synthetic"))
            table = xp.asarray(rng.standard_cauchy(k).clip(-20, 20) * 0.05)
            terms.append(Term(f"t{j}", [name], lambda xp_, v, n=name, t=table: t[xp_.asarray(v[n]).astype(int)]))
        else:
            choices.append(Choice(name, "continuous", ("normal", {"mean": 0.0, "sd": 1.0}), "synthetic"))
            a = float(rng.standard_cauchy() * 0.05)
            terms.append(Term(f"t{j}", [name], lambda xp_, v, n=name, a=a: a * v[n]))
    for i in range(J // 4):
        a, b = rng.choice(J, 2, replace=False)
        na, nb, coef = f"c{a}", f"c{b}", float(rng.normal(0, 0.02))
        terms.append(Term(f"x{i}", [na, nb], lambda xp_, v, na=na, nb=nb, c=coef: c * v[na] * v[nb]))
    terms.append(Term("offset", [], lambda xp_, v, o=float(rng.normal(0, 0.05)): o))
    return Model(choices, terms, xp)


def draw_truth(model, seed):
    """One plausible expert world {name: engine number} drawn from the priors."""
    s = to_numpy(model.sample(1, seed + 10_000))
    return {c.name: float(s[0, j]) for j, c in enumerate(model.choices)}


def draw_truth_tails(model, seed, tail=0.1):
    """An expert world the agent's priors get WRONG (proposal v2, section 6, calibration).

    Continuous choices are drawn from the outer tails of the prior (the lowest or
    highest `tail` share of its probability); categorical choices take an option
    other than the most probable one. Choices already fixed keep their value.
    The agent still reasons with its own priors, so this checks whether a
    certified verdict holds when those priors are off.
    """
    rng = np.random.default_rng(np.random.SeedSequence([seed, 20_000]))
    out = {}
    for c in model.choices:
        if not c.is_open():
            out[c.name] = c.encode(c.fixed)
        elif c.kind == "categorical":
            probs = c.probs
            others = [i for i in range(len(probs)) if i != int(np.argmax(probs))]
            if not others:
                out[c.name] = 0.0
            else:
                w = probs[others] / probs[others].sum() if probs[others].sum() > 0 else None
                out[c.name] = float(rng.choice(others, p=w))
        else:
            u = rng.uniform(0, tail)
            u = u if rng.random() < 0.5 else 1 - u
            out[c.name] = float(c.ppf(np.array([u]))[0])
    return out

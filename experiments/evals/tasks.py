"""The tasks of the evaluation: what each one gives the agent, and what counts as success.

Two suites, as Anthropic's guide separates them:

  regression   properties the agent must keep on every trial; the target is 100%, and a failure is a
               defect to fix before anything else.
  capability   how well the agent does its job, on the benchmark comparisons, with simulated experts
               who answer from the prior, from a world chosen against the agent, or from one fixed world.

The set is balanced: for each behaviour there is a task where it should happen and one where it
should not (ask / do not ask, certify / do not certify, show the ISO notice / do not show it).
"""
import copy
import itertools
import json
import os
from dataclasses import dataclass, field
from typing import Callable

from branch.agent import Session
from branch.builder import build_model
from branch.cases import draw_truth, draw_truth_adverse, toy_packaging
from branch.interview import parse_answer
from branch.paths import data_path

from graders import (answers_read_as_meant, asked_nothing, asked_something, at_most_one_question,
                     certified_and_right, not_certified, right_if_certified, right_verdict,
                     scale_changes_nothing, swap_keeps_the_winner, value_laden_all_asked)
from harness import record_session

PACKAGES = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
REGIONS = ["PT", "DE", "BR"]
CATEGORY = "Climate change"


@dataclass
class Task:
    name: str
    suite: str                       # "regression" or "capability"
    expects: str                     # the behaviour, in words, for the report
    run: Callable                    # trial number -> list of transcripts
    outcome: list = field(default_factory=list)     # graders of each transcript's outcome
    pair: list = field(default_factory=list)        # graders of two transcripts compared
    loop: bool = True                # whether the graders of the loop apply (False: not a session)
    skip: tuple = ()                 # graders of the loop that do not apply to this task, said in the README


def _spec(name):
    with open(os.path.join(data_path("benchmark"), f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _variant(name, new_id, mass_factor=1.0):
    """A copy of a benchmark product under another id, its masses multiplied by mass_factor."""
    spec = copy.deepcopy(_spec(name))
    spec["id"], spec["name"] = new_id, f"{spec['name']} ({new_id})"
    for comp in spec["components"]:
        dist, params, source = comp["mass_prior"]
        comp["mass_prior"] = [dist, {k: v * mass_factor for k, v in params.items()}, source]
    return spec


def _truth_oracle(truth):
    return lambda name: truth[name]


def _scaled(factors, k):
    out = copy.deepcopy(factors)
    for entry in out["factors"].values():
        entry["impacts"] = {c: v * k for c, v in entry["impacts"].items()}
    return out


# ---------------------------------------------------------------- regression: the rules of the agent

def _session_task(name, expects, make, outcome, **kw):
    """make(trial) -> (model, truth or None, extra keywords of record_session)."""
    def run(trial):
        model, truth, extra = make(trial)
        oracle = extra.pop("oracle", None) or _truth_oracle(truth)
        return [record_session(model, oracle, seed=trial, truth=truth, **extra)]
    return Task(name, "regression", expects, run, outcome, **kw)


def _gap_and_tie(factors, region):
    def gap(trial):
        m = build_model(_spec("pet_bottle_1l"), _variant("pet_bottle_1l", "pet_heavy", 3.0), region, CATEGORY, factors)
        return m, draw_truth(m, 100 + trial), {}

    def tie(trial, skip=False):
        m = build_model(_spec("pet_bottle_1l"), _variant("pet_bottle_1l", "pet_twin"), region, CATEGORY, factors)
        return m, draw_truth(m, 200 + trial), ({"oracle": lambda n: None} if skip else {})
    return [
        _session_task(f"clear_gap_{region}", "PET against the same bottle three times heavier: certify, ask nothing",
                      gap, [asked_nothing, certified_and_right]),
        _session_task(f"near_tie_{region}", "PET against an identical PET bottle: ask before any verdict",
                      tie, [asked_something, right_if_certified]),
        _session_task(f"near_tie_all_unknown_{region}",
                      "the same tie, the person answers 'I don't know' to everything: do not certify",
                      lambda t: tie(t, skip=True), [not_certified]),
    ]


def _stop_public_laden(factors):
    def pet_glass(trial, **extra):
        m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CATEGORY, factors)
        return m, draw_truth(m, 300 + trial), extra

    def toy(trial):
        m = toy_packaging()
        return m, draw_truth(m, 400 + trial), {}
    return [
        _session_task("finish_after_one_question", "the person stops after one answer: say honestly whether it is certified",
                      lambda t: pet_glass(t, stop_after=1), [at_most_one_question]),
        _session_task("public_comparison", "a comparison for the public: show the ISO 14044 notice",
                      lambda t: pet_glass(t, public=True), [right_if_certified]),
        _session_task("value_laden_choice", "a value laden choice: always ask it, and first",
                      toy, [value_laden_all_asked, right_if_certified],
                      skip=("every_default_has_a_source",)),     # the toy model of the README has placeholder sources
    ]


def _pairs():
    return [(a, b, r) for (a, b), r in itertools.product(itertools.combinations(PACKAGES, 2), REGIONS)]


def _metamorphic(factors):
    """The same comparison asked in two ways that must not change the answer."""
    cases = _pairs()

    def swap(trial):
        a, b, r = cases[trial % len(cases)]
        ab, ba = (build_model(x, y, r, CATEGORY, factors) for x, y in ((a, b), (b, a)))
        t = draw_truth(ab, 500 + trial)
        return [record_session(m, _truth_oracle(t), seed=trial, truth=t) for m in (ab, ba)]

    def scale(trial):
        a, b, r = cases[trial % len(cases)]
        models = [build_model(a, b, r, CATEGORY, f) for f in (factors, _scaled(factors, 10.0))]
        t = draw_truth(models[0], 600 + trial)
        return [record_session(m, _truth_oracle(t), seed=trial, truth=t) for m in models]
    return [Task("swap_products", "regression", "A against B and B against A: the same product wins",
                 swap, [right_if_certified], [swap_keeps_the_winner]),
            Task("scale_all_factors", "regression", "every unit factor times ten: the same questions and verdict",
                 scale, [right_if_certified], [scale_changes_nothing])]


# what a person may type, and what the application must make of it: a number, "don't know", or a refusal
ANSWERS = [("distribution_km", "250", 250.0), ("distribution_km", "250,5", 250.5),
           ("distribution_km", "", None), ("distribution_km", "?", None),
           ("distribution_km", "far", "refused"), ("distribution_km", "-5", "refused"),
           ("pet.pet.recycling_rate", "40%", 0.4), ("pet.pet.recycling_rate", "40", 0.4),
           ("pet.pet.recycling_rate", "140", "refused"), ("glass.trips", "0", "refused"),
           ("glass.glass.end_of_life", "landfill", 1.0), ("glass.glass.end_of_life", "sea", "refused")]


def _read(session, name, raw):
    try:
        return parse_answer(session, name, raw)
    except ValueError:
        return "refused"


def _answers(factors):
    def run(trial):
        m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CATEGORY, factors)
        s = Session(m, n_samples=1000, seed=trial)
        return [{"answers": [(n, raw, want, _read(s, n, raw)) for n, raw, want in ANSWERS]}]
    return Task("answers_typed_in_the_form", "regression",
                "numbers, commas, percent, blanks and nonsense are read as meant or refused with a message",
                run, [answers_read_as_meant], loop=False)


def regression_tasks(factors):
    out = [t for r in REGIONS for t in _gap_and_tie(factors, r)]
    return out + _stop_public_laden(factors) + _metamorphic(factors) + [_answers(factors)]


# ---------------------------------------------------------------- capability: the benchmark comparisons

EXPERTS = {"prior": lambda m, seed: draw_truth(m, seed),
           "adverse": lambda m, seed: draw_truth_adverse(m, seed)}


def _benchmark_task(factors, a, b, region, expert):
    """One comparison of the paper; each trial a new expert (or, for 'fixed', the same expert)."""
    def run(trial):
        m = build_model(a, b, region, CATEGORY, factors)
        seed = 0 if expert == "fixed" else 1000 + trial
        t = (EXPERTS["prior"] if expert == "fixed" else EXPERTS[expert])(m, seed)
        return [record_session(m, _truth_oracle(t), seed=trial, truth=t)]
    outcome = [right_verdict] if expert == "fixed" else [right_if_certified]
    what = {"prior": "experts drawn from the priors: a certified verdict is right",
            "adverse": "experts whose world is chosen against the agent: a certified verdict is right",
            "fixed": "one expert, new Monte Carlo draws each trial: the agent ends on the expert's verdict"}[expert]
    return Task(f"{a}__{b}__{region}__{expert}", "capability", what, run, outcome)


def capability_tasks(factors, experts=("prior", "adverse", "fixed")):
    return [_benchmark_task(factors, a, b, r, e) for e in experts for a, b, r in _pairs()]

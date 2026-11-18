import numpy as np
import pytest

from branch.agent import ISO_PUBLIC_NOTICE, run_agent
from branch.cases import draw_truth, synthetic, synthetic_lca, toy_packaging
from branch.montecarlo import State
from branch.query import STRATEGIES
from branch.report import markdown_report


def test_incremental_update_matches_full_recompute():
    m = synthetic(12, seed=3)
    st = State(m, m.sample(2000, seed=1))
    for name in ["c0", "c5", "c7"]:
        st.fix(name, m.by_name[name].answers()[0][0])
    full = sum(m.term_value(k, st.S) for k in range(len(m.terms)))
    assert np.allclose(st.delta, full)


def test_conditional_deltas_match_fixing():
    m = toy_packaging()
    st = State(m, m.sample(3000, seed=2))
    d, w = st.conditional_deltas("glass_trips")
    v = m.by_name["glass_trips"].answers()[0][2]
    st.fix("glass_trips", v)
    assert np.allclose(d[2], st.delta)
    assert np.isclose(float(w.sum()), 1.0)


def test_common_random_numbers_are_reproducible():
    m = toy_packaging()
    assert np.array_equal(m.sample(500, seed=4), m.sample(500, seed=4))


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_every_strategy_reaches_a_verdict(strategy):
    m = toy_packaging()
    t = draw_truth(m, 0)
    r = run_agent(m, lambda n: t[n], strategy=strategy, n_samples=5000, truth=t)
    assert r["questions"] <= len(m.choices)
    assert r["certified"] or not r["trace"][-1]["p_flip"] < r["tau"]


def test_value_laden_choice_is_always_asked_first():
    m = toy_packaging()
    t = draw_truth(m, 1)
    r = run_agent(m, lambda n: t[n], n_samples=5000, truth=t)
    assert r["asked"][0] == "capital_goods"
    assert r["decided_by"]["capital_goods"] == "human"


def test_dont_know_keeps_prior_and_is_not_asked_again():
    m = toy_packaging()
    t = draw_truth(m, 2)
    oracle = lambda n: None if n == "glass_trips" else t[n]  # noqa: E731
    r = run_agent(m, oracle, n_samples=5000, truth=t)
    if "glass_trips" in r["asked"]:
        assert r["asked"].count("glass_trips") == 1
        assert r["decided_by"]["glass_trips"].startswith("human: don't know")
        assert "glass_trips" not in r["fixed"]


def test_public_comparison_notice_reaches_report():
    m = toy_packaging()
    t = draw_truth(m, 3)
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t, public_comparison=True)
    assert ISO_PUBLIC_NOTICE in r["notices"]
    assert "does not replace" in markdown_report(r, m)


def test_decision_flip_beats_uncertainty_sampling_on_lca_like_model():
    m = synthetic_lca(30, seed=2)
    q = {s: np.mean([run_agent(m, (lambda t: (lambda n: t[n]))(draw_truth(m, k)), strategy=s,
                               n_samples=4000, seed=k, truth=draw_truth(m, k))["questions"]
                     for k in range(8)])
         for s in ("decision_flip", "entropy")}
    assert q["decision_flip"] < q["entropy"]


def test_cli_rejects_out_of_range_and_bad_input():
    from branch.agent import ask_human_cli
    m = toy_packaging()
    answers = iter(["abc", "0", "n", "12"])  # bad text, 0 trips refused, then 12
    oracle = ask_human_cli(m, inp=lambda _: next(answers), out=lambda *_: None)
    assert oracle("glass_trips") == 12.0
    answers2 = iter(["9", "1"])
    oracle2 = ask_human_cli(m, inp=lambda _: next(answers2), out=lambda *_: None)
    assert oracle2("pet_eol") == 1.0


def _fake_factors(tmp_path):
    import json
    keys = ["pet_granulate_bottle_grade", "pet_granulate_amorphous", "stretch_blow_moulding",
            "glass_packaging_white", "glass_packaging_green", "glass_packaging_brown",
            "electricity_mv_PT", "electricity_mv_DE", "electricity_mv_BR", "lorry_16_32t",
            "heat_natural_gas_furnace", "tap_water_RER", "disposal_polyethylene_terephthalate_incineration",
            "disposal_plastics_mixture_landfill", "disposal_glass_incineration", "disposal_glass_landfill"]
    data = {"method": "test", "factors": {k: {"impacts": {"Climate change": 1.0}} for k in keys}}
    p = tmp_path / "f.json"
    p.write_text(json.dumps(data))
    return p


def test_real_case_builds_from_factor_file_and_lists_assumptions(tmp_path):
    from branch.real_cases import assumptions, compare, load_factors
    m = compare("pet_bottle_1l", "glass_refillable_1l", "PT", factors=load_factors(_fake_factors(tmp_path)))
    t = draw_truth(m, 0)
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t)
    rep = markdown_report(r, m)
    assert "Placeholder priors" in rep and "BAFU:2026" in rep
    assert "pet.bottle.mass_g" in assumptions(m)
    assert set(r["impacts"]) == {"PET single use", "Refillable glass"}

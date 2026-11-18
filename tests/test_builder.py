"""The generic builder must reproduce the hand written PET vs glass model exactly,
and build any pair of benchmark products. No openLCA needed: the unit impact
factors are synthetic numbers with the same keys as a real extraction."""
import os

import numpy as np
import pytest

from branch import catalogue as cat
from branch.agent import run_agent
from branch.builder import build_model, load_spec, required_factor_keys
from branch.cases import draw_truth
from branch.real_cases import assumptions, pet_vs_refillable_glass
from tests.legacy_pet_glass import legacy_pet_vs_refillable_glass

CAT = "Climate change"
BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]

# hand written name -> builder name
LEGACY_NAMES = {
    "pet_mass_g": "pet.bottle.mass_g", "pet_dataset": "pet.pet.dataset",
    "pet_recycled_share": "pet.pet.recycled_content", "rpet_burden_ratio": "pet.pet.recycled_ratio",
    "pet_recycling_rate": "pet.pet.recycling_rate", "pet_incineration_share": "pet.pet.incineration_share",
    "glass_mass_g": "glass.bottle.mass_g", "glass_colour": "glass.glass.dataset",
    "glass_trips": "glass.trips", "wash_kwh": "glass.wash_kwh", "wash_heat_mj": "glass.wash_heat_mj",
    "wash_water_kg": "glass.wash_water_kg", "glass_eol": "glass.glass.end_of_life",
    "distribution_km": "distribution_km",
}


# A country without a region file of its own: the catalogue priors apply unchanged there,
# while PT, DE, BR and the European countries override them with statistics (data/regions/*.json).
PLAIN = "US"


def fake_factors(seed=0):
    keys = (required_factor_keys(BENCH, "PT") + required_factor_keys(BENCH, "DE")
            + required_factor_keys(BENCH, PLAIN))
    rng = np.random.default_rng(seed)
    return {"method": "synthetic", "path": "synthetic.json", "citation": "synthetic",
            "factors": {k: {"impacts": {CAT: float(rng.uniform(0.01, 5))}} for k in sorted(set(keys))}}


def test_builder_reproduces_hand_written_pet_vs_glass():
    data = fake_factors()
    old = legacy_pet_vs_refillable_glass(data, country=PLAIN)
    new = pet_vs_refillable_glass(region=PLAIN, factors=data)
    assert set(LEGACY_NAMES.values()) == {c.name for c in new.choices}
    for c in old.choices:                     # same priors
        n = new.by_name[LEGACY_NAMES[c.name]]
        assert (c.kind, c.prior) == (n.kind, n.prior)
        assert c.source.split(":")[0] == n.source.split(":")[0]
    S = old.sample(300, seed=7)
    for row in range(S.shape[0]):             # same delta in every world
        world = {c.name: float(S[row, j]) for j, c in enumerate(old.choices)}
        mapped = {LEGACY_NAMES[k]: v for k, v in world.items()}
        assert np.isclose(old.delta_at(world), new.delta_at(mapped), rtol=1e-12)


@pytest.mark.parametrize("a,b", [(x, y) for x in BENCH for y in BENCH if x != y])
def test_any_benchmark_pair_builds_and_runs(a, b):
    m = build_model(a, b, "DE", CAT, fake_factors())
    t = draw_truth(m, 0)
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t)
    assert r["questions"] <= len(m.choices)
    assert m.label_a == load_spec(a)["name"]


def test_stated_bom_values_are_fixed_not_asked():
    spec = load_spec("pet_bottle_1l")
    spec["components"][0] = {"id": "bottle", "material": "pet", "mass_g": 30}
    spec["materials"] = {"pet": {"dataset": "bottle grade", "recycled_content": 0.3}}
    m = build_model(spec, "glass_refillable_1l", factors=fake_factors())
    names = {c.name for c in m.choices}
    assert not names & {"pet.bottle.mass_g", "pet.pet.dataset", "pet.pet.recycled_content"}
    assert "pet.pet.recycled_ratio" in names


def test_functional_unit_scales_small_containers():
    data = fake_factors()
    can = load_spec("aluminium_can_330ml")
    one_litre = dict(can, volume_l=1.0, id="can1l")
    m33 = build_model(can, "pet_bottle_1l", factors=data)
    m1 = build_model(one_litre, "pet_bottle_1l", factors=data)
    world = {c.name: c.answers()[0][0] for c in m33.choices}
    w1 = {k.replace("can.", "can1l.", 1): v for k, v in world.items()}
    i33 = sum(float(m33.term_value(k, m33.xp.asarray([[world[c.name] for c in m33.choices]]))[0])
              for k, t in enumerate(m33.terms) if t.sign > 0)
    i1 = sum(float(m1.term_value(k, m1.xp.asarray([[w1[c.name] for c in m1.choices]]))[0])
             for k, t in enumerate(m1.terms) if t.sign > 0)
    assert np.isclose(i33, i1 / 0.33)


def test_bad_bill_of_materials_is_rejected():
    with pytest.raises(ValueError, match="unknown material"):
        load_spec({"id": "x", "components": [{"material": "unobtainium", "mass_g": 1}]})
    with pytest.raises(ValueError, match="mass_g or mass_prior"):
        load_spec({"id": "x", "components": [{"material": "pet"}]})


def test_every_catalogue_prior_is_tagged():
    m = build_model("beverage_carton_1l", "aluminium_can_330ml", factors=fake_factors())
    assert all(c.source.startswith(("SOURCE", "ASSUMPTION")) for c in m.choices)
    assert assumptions(m)


def test_required_keys_are_all_known_to_the_extractor():
    import json
    known = set(json.load(open("data/databases/bafu2026.json", encoding="utf-8"))["datasets"])
    for country in ("PT", "DE", "BR"):
        missing = set(required_factor_keys(BENCH, country)) - known
        assert not missing, missing
    assert set(cat.MATERIALS) >= {"pet", "glass", "aluminium", "liquid_packaging_board"}


# ------------------------------------------------------------------ regions

def all_region_factors(seed=0):
    from branch.regions import list_regions
    keys = set()
    for r in list_regions():
        if r != "GLO":
            keys |= set(required_factor_keys(BENCH, r))
    rng = np.random.default_rng(seed)
    return {"method": "synthetic", "path": "synthetic.json", "citation": "synthetic",
            "factors": {k: {"impacts": {CAT: float(rng.uniform(0.01, 5))}} for k in keys}}


def test_region_chain_and_overrides():
    from branch.regions import load_region
    r = load_region("BR-AM")
    assert [x["code"] for x in r.chain] == ["BR-AM", "BR-N", "BR", "GLO"]
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "BR-AM", CAT, all_region_factors())
    names = {c.name for c in m.choices}
    assert {"electricity", "supply.barge_km", "distribution_km"} <= names
    assert m.by_name["pet.pet.recycling_rate"].prior == ("beta", {"a": 2, "b": 8})   # from BR-N
    assert m.by_name["distribution_km"].prior[0] == "triangular"                     # from BR-AM
    assert any(t.name == "pet.supply_transport" for t in m.terms)
    assert m.meta["region_path"].endswith("Amazonas (Manaus)")
    t = draw_truth(m, 0)
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t)
    assert r["questions"] <= len(m.choices)


@pytest.mark.parametrize("code", ["PT", "DE", "BR"])
def test_recycling_priors_of_the_three_countries_are_sourced(code):
    """What happens to the packaging after use comes from national statistics, not from a guess."""
    data = all_region_factors()
    for a, b in (("pet_bottle_1l", "glass_refillable_1l"), ("aluminium_can_330ml", "beverage_carton_1l")):
        m = build_model(a, b, code, CAT, data)
        for c in m.choices:
            if c.name.endswith((".recycling_rate", ".incineration_share", ".end_of_life")):
                assert c.source.startswith("SOURCE:"), (code, c.name, c.source)
    m = build_model("pet_bottle_1l", "glass_refillable_1l", code, CAT, data)
    assert m.by_name["pet.pet.recycled_content"].source.startswith("SOURCE:") or code == "BR"


def test_a_region_can_override_a_categorical_prior():
    data = all_region_factors()
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data)
    c = m.by_name["glass.glass.end_of_life"]
    assert c.labels == ["recycling (cut-off)", "landfill", "incineration"]
    assert np.allclose(c.probs, [0.56, 0.32, 0.12])
    assert "Eurostat" in c.source
    plain = build_model("pet_bottle_1l", "glass_refillable_1l", PLAIN, CAT, fake_factors())
    assert np.allclose(plain.by_name["glass.glass.end_of_life"].probs, [0.6, 0.3, 0.1])


def test_an_override_with_an_unknown_option_is_refused(tmp_path, monkeypatch):
    import json

    from branch import regions
    for code in ("GLO", "PT"):
        (tmp_path / f"{code}.json").write_text(open(f"data/regions/{code}.json").read())
    bad = json.loads((tmp_path / "PT.json").read_text())
    bad["priors"]["glass.end_of_life"] = {"weights": {"reuse": 1.0}, "source": "SOURCE: x"}
    (tmp_path / "PT.json").write_text(json.dumps(bad))
    monkeypatch.setattr(regions, "REGION_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="unknown options"):
        build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, all_region_factors())


def test_every_region_needs_only_known_factor_keys():
    import json
    import re

    from branch.regions import list_regions
    known = set(json.load(open("data/databases/bafu2026.json", encoding="utf-8"))["datasets"])
    for code in list_regions():
        if code == "GLO":
            continue
        missing = set(required_factor_keys(BENCH, code)) - known
        # the extractor finds the electricity mix of every other country in the database by its name
        missing = {k for k in missing if not re.fullmatch(r"electricity_mv_([A-Z]{2}|ENTSO-E)", k)}
        assert not missing, (code, missing)


def test_refillable_supply_is_spread_over_trips():
    data = all_region_factors()
    m = build_model("glass_refillable_1l", "pet_bottle_1l", "BR-AM", CAT, data)
    w = {c.name: c.answers()[0][len(c.answers()[0]) // 2] for c in m.choices}
    inv1 = m.inventory(dict(w, **{"glass.trips": 1.0}))["Refillable glass"]["transport_barge"]
    inv10 = m.inventory(dict(w, **{"glass.trips": 10.0}))["Refillable glass"]["transport_barge"]
    assert np.isclose(inv1, 10 * inv10)


def test_materials_can_be_added_as_data_files(tmp_path, monkeypatch):
    import json

    from branch import catalogue
    (tmp_path / "steel.json").write_text(json.dumps({
        "label": "tinplate", "datasets": {"tinplate": ["tinplate", 1.0]},
        "end_of_life": {"model": "split",
                        "recycling_rate": ["beta", {"a": 6, "b": 4}, "ASSUMPTION: test"],
                        "incineration_share": ["uniform", {"low": 0, "high": 1}, "ASSUMPTION: test"],
                        "incineration": "disposal_polyethylene_terephthalate_incineration", "landfill": "disposal_plastics_mixture_landfill"}}))
    real = catalogue.load_materials
    monkeypatch.setattr(catalogue, "load_materials", lambda root=None: real(tmp_path))
    data = fake_factors()
    data["factors"]["tinplate"] = {"impacts": {CAT: 2.0}}
    spec = {"id": "tin", "name": "Tin can", "volume_l": 0.5,
            "components": [{"id": "body", "material": "steel", "mass_g": 40}]}
    m = build_model(spec, "pet_bottle_1l", "PT", CAT, data)
    assert "tin.steel.recycling_rate" in {c.name for c in m.choices}


def test_session_answers_only_the_question_asked():
    from branch.agent import Session
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, fake_factors())
    s = Session(m, n_samples=2000)
    with pytest.raises(RuntimeError):
        s.result()
    q = s.next_question()
    other = next(c.name for c in m.choices if c.name != q)
    with pytest.raises(ValueError):
        s.answer(other, 1.0)


# ------------------------------------------------- Circular Footprint Formula

def _cff_dir(tmp_path, A):
    import json
    for mid in ("pet", "glass", "aluminium", "liquid_packaging_board", "ldpe", "hdpe"):
        p = {"A": A, "Qsin_Qp": 0.9, "Qsout_Qp": 0.8, "source": "TEST ONLY"}
        if mid in ("glass", "liquid_packaging_board", "ldpe", "hdpe"):
            p["recycling_eol_key"] = "tap_water_RER"          # any key: a stand in recycling process
        (tmp_path / f"{mid}.json").write_text(json.dumps(p))
    return tmp_path


def _cff(monkeypatch, tmp_path, A):
    from branch import catalogue
    root = _cff_dir(tmp_path, A)
    real = catalogue.load_cff
    monkeypatch.setattr(catalogue, "load_cff", lambda r=None: real(root))


def test_cff_with_A_equal_1_and_no_energy_credit_is_cut_off(monkeypatch, tmp_path):
    from branch import catalogue
    _cff(monkeypatch, tmp_path, 1.0)
    monkeypatch.setattr(catalogue, "load_energy_recovery", lambda r=None: {})
    data = fake_factors()
    for a, b in [("pet_bottle_1l", "glass_refillable_1l"), ("aluminium_can_330ml", "beverage_carton_1l")]:
        cut = build_model(a, b, "PT", CAT, data)
        cff = build_model(a, b, "PT", CAT, data, system_model="cff")
        S = cut.sample(50, seed=3)
        for r in range(S.shape[0]):
            w = {c.name: float(S[r, j]) for j, c in enumerate(cut.choices)}
            assert np.isclose(cut.delta_at(w), cff.delta_at(w), rtol=1e-12)


def test_cff_matches_the_formula_by_hand(monkeypatch, tmp_path):
    _cff(monkeypatch, tmp_path, 0.5)
    data = fake_factors()
    f = lambda k: data["factors"][k]["impacts"][CAT]  # noqa: E731
    m = build_model("aluminium_can_330ml", "pet_bottle_1l", "PT", CAT, data, system_model="cff")
    w = {c.name: c.answers()[0][len(c.answers()[0]) // 2] for c in m.choices}
    kg, r1, r2 = w["can.body_and_lid.mass_g"] / 1000, w["can.aluminium.recycled_content"], w["can.aluminium.recycling_rate"]
    ev, erec = f("aluminium_primary"), f("aluminium_secondary_old_scrap")
    n = 1 / 0.33
    content = (1 - r1) * ev + r1 * (0.5 * erec + 0.5 * ev * 0.9) + f("sheet_rolling_aluminium")
    credit = 0.5 * r2 * (erec - ev * 0.8)
    s = w["can.aluminium.incineration_share"]
    disposal = (1 - r2) * (s * f("disposal_aluminium_incineration") + (1 - s) * f("disposal_aluminium_landfill"))
    can_terms = [i for i, t in enumerate(m.terms) if t.name.startswith("can.") and "transport" not in t.name]
    X = m.xp.asarray([[w[c.name] for c in m.choices]])
    got = sum(float(m.term_value(i, X)[0]) for i in can_terms)
    assert np.isclose(got, n * kg * (content + credit + disposal), rtol=1e-12)


def test_cff_inventory_matches_engine_and_needs_annex_c(monkeypatch, tmp_path):
    from branch import catalogue
    from branch.builder import factor
    empty = tmp_path / "none"
    empty.mkdir()
    real = catalogue.load_cff
    with monkeypatch.context() as mp:                 # a folder without parameter files
        mp.setattr(catalogue, "load_cff", lambda r=None: real(str(empty)))
        with pytest.raises(ValueError, match="Annex C"):
            build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, fake_factors(), system_model="cff")
    _cff(monkeypatch, tmp_path, 0.2)
    data = fake_factors()
    m = build_model("beverage_carton_1l", "glass_refillable_1l", "PT", CAT, data, system_model="cff")
    S = m.sample(30, seed=9)
    for r in range(S.shape[0]):
        w = {c.name: float(S[r, j]) for j, c in enumerate(m.choices)}
        inv = m.inventory(w)
        tot = {k: sum(x * factor(data, key, CAT) for key, x in v.items()) for k, v in inv.items()}
        assert np.isclose(tot[m.label_a] - tot[m.label_b], m.delta_at(w), rtol=1e-10)


def test_tail_experts_are_drawn_away_from_the_priors():
    from branch.cases import draw_truth_tails
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, fake_factors())
    for seed in range(20):
        t = draw_truth_tails(m, seed)
        for c in m.choices:
            if c.kind == "continuous":
                u = float(c._frozen().cdf(t[c.name]))
                assert u <= 0.1 + 1e-9 or u >= 0.9 - 1e-9
            elif len(c.labels) > 1:
                assert int(t[c.name]) != int(np.argmax(c.probs))
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t)
    assert r["questions"] <= len(m.choices)


def test_cff_energy_credit_matches_the_formula_by_hand(monkeypatch, tmp_path):
    """Energy term with B = 0: R3 (E_ER - electricity delivered x E_SE,elec - steam delivered x E_SE,heat).
    R3 x E_ER is the incineration part of the end of life; the credit is what the formula adds."""
    from branch import catalogue
    _cff(monkeypatch, tmp_path, 1.0)                  # A = 1: the material part of the formula is cut-off
    data = fake_factors()
    f = lambda k: data["factors"][k]["impacts"][CAT]  # noqa: E731
    rec = {"pet": {"electricity_mj_per_kg": 3.6, "steam_mj_per_kg": 10.0, "source": "TEST ONLY"},
           "glass": {"electricity_mj_per_kg": -0.36, "steam_mj_per_kg": -0.5, "source": "TEST ONLY"}}
    monkeypatch.setattr(catalogue, "load_energy_recovery", lambda r=None: rec)
    cff = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, system_model="cff")
    monkeypatch.setattr(catalogue, "load_energy_recovery", lambda r=None: {})
    plain = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, system_model="cff")
    assert [t.name for t in cff.terms if "cff_energy" in t.name] == ["pet.bottle.cff_energy.end_of_life",
                                                                     "glass.bottle.cff_energy.end_of_life"]
    elec, heat = f("electricity_mv_PT"), f("heat_natural_gas_furnace")
    S = cff.sample(40, seed=5)
    for r in range(S.shape[0]):
        w = {c.name: float(S[r, j]) for j, c in enumerate(cff.choices)}
        r3_pet = (1 - w["pet.pet.recycling_rate"]) * w["pet.pet.incineration_share"]
        burnt = cff.by_name["glass.glass.end_of_life"].labels[int(round(w["glass.glass.end_of_life"]))] == "incineration"
        pet = -w["pet.bottle.mass_g"] / 1000 * r3_pet * (1.0 * elec + 10.0 * heat)
        glass = -w["glass.bottle.mass_g"] / 1000 * (1.0 if burnt else 0.0) * (-0.1 * elec - 0.5 * heat) / w["glass.trips"]
        assert np.isclose(cff.delta_at(w) - plain.delta_at(w), pet - glass, rtol=1e-9, atol=1e-15)
        inv = cff.inventory(w)                        # the inventory carries the credit too
        tot = {k: sum(x * f(key) for key, x in v.items()) for k, v in inv.items()}
        assert np.isclose(tot[cff.label_a] - tot[cff.label_b], cff.delta_at(w), rtol=1e-9)


def test_cff_runs_on_the_real_parameter_files_and_asks_about_missing_recycling_datasets():
    """Part C of Annex II is in data/cff/; glass, HDPE, LDPE and the board have no recycling dataset,
    so their recycling burden is an explicit ASSUMPTION choice instead of an error."""
    from branch import catalogue
    params = catalogue.load_cff()
    assert params["pet"]["A"] == 0.5 and params["aluminium"]["A"] == 0.2 and params["ldpe"]["Qsout_Qp"] == 0.75
    assert all(p["source"].startswith("SOURCE: ") and "Annex II" in p["source"] for p in params.values())
    data = fake_factors()
    for a, b in [("pet_bottle_1l", "glass_refillable_1l"), ("aluminium_can_330ml", "beverage_carton_1l")]:
        m = build_model(a, b, "DE", CAT, data, system_model="cff")
        asked = {c.name: c for c in m.choices if c.name.endswith(".recycling_ratio")}
        assert all(c.source.startswith("ASSUMPTION") for c in asked.values())
        if a == "pet_bottle_1l":
            assert set(asked) == {"glass.glass.recycling_ratio"}
        else:
            assert set(asked) == {"carton.liquid_packaging_board.recycling_ratio", "carton.ldpe.recycling_ratio",
                                  "carton.hdpe.recycling_ratio"}
        w = {c.name: c.answers()[0][len(c.answers()[0]) // 2] for c in m.choices}
        assert np.isfinite(m.delta_at(w))
    with pytest.raises(ValueError, match="Annex II"):   # no parameters for PLA in the official file
        build_model("data/examples/pla_cup_05l.json", "pet_bottle_1l", "PT", CAT, data, system_model="cff")


def test_the_annex_tables_in_the_repository_are_the_ones_read_from_the_commission():
    """Checksum of the packaging rows computed in the browser on the Commission's file on 16 November 2026."""
    import hashlib
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cff",
                        "annex_c_packaging_A_R1_R2.csv")
    with open(path, "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == "25a37bab86944f25ba2fd8560ec6402bb6b6abb08f30bad9e6aca57fd7643764"


def test_cff_heat_can_be_district_heat_or_nothing(monkeypatch, tmp_path):
    """Sensitivity runs of the energy credit: the heat replaced is another dataset, or there is no credit for heat."""
    from branch import catalogue
    _cff(monkeypatch, tmp_path, 1.0)
    data = fake_factors()
    data["factors"]["district_heat_ch_average"] = {"impacts": {CAT: 0.02}}
    f = lambda k: data["factors"][k]["impacts"][CAT]  # noqa: E731
    rec = {"pet": {"electricity_mj_per_kg": 3.6, "steam_mj_per_kg": 10.0, "source": "TEST ONLY"}}
    monkeypatch.setattr(catalogue, "load_energy_recovery", lambda r=None: rec)
    kw = dict(system_model="cff")
    gas = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, **kw)
    none = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, cff_heat="none", **kw)
    district = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, cff_heat="district", **kw)
    S = gas.sample(20, seed=2)
    for r in range(S.shape[0]):
        w = {c.name: float(S[r, j]) for j, c in enumerate(gas.choices)}
        burnt_kg = w["pet.bottle.mass_g"] / 1000 * (1 - w["pet.pet.recycling_rate"]) * w["pet.pet.incineration_share"]
        assert np.isclose(none.delta_at(w) - gas.delta_at(w), burnt_kg * 10.0 * f("heat_natural_gas_furnace"), rtol=1e-9)
        assert np.isclose(district.delta_at(w) - none.delta_at(w), -burnt_kg * 10.0 * 0.02, rtol=1e-9)
        inv = none.inventory(w)
        assert "heat_natural_gas_furnace" not in inv[none.label_a] or inv[none.label_a]["heat_natural_gas_furnace"] >= 0
    assert "district_heat_ch_average" not in required_factor_keys(["pet_bottle_1l"], "PT")   # never needed by default
    with pytest.raises(ValueError, match="cff_heat"):
        build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, cff_heat="coal", **kw)


def test_cff_parameters_can_be_overridden_for_a_sensitivity_run():
    """PET with the quality ratios of SSP recycling (1 and 1) instead of mechanical recycling (0.9)."""
    data = fake_factors()
    base = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, system_model="cff")
    ssp = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, system_model="cff",
                      cff_overrides={"pet": {"Qsin_Qp": 1.0, "Qsout_Qp": 1.0}})
    w = {c.name: c.answers()[0][len(c.answers()[0]) // 2] for c in base.choices}
    assert [c.name for c in base.choices] == [c.name for c in ssp.choices]
    assert ssp.delta_at(w) != base.delta_at(w)
    from branch import catalogue
    assert catalogue.load_cff()["pet"]["Qsout_Qp"] == 0.9          # the file itself is untouched


def test_aluminium_uses_primary_metal_beside_its_recycled_content():
    """The production mix of wrought alloy already holds secondary aluminium (a little over half primary in BAFU:2026),
    so beside a recycled content the virgin metal has to be the primary dataset."""
    assert cat.MATERIALS["aluminium"]["datasets"] == {"primary aluminium": ("aluminium_primary", 1.0)}
    assert "aluminium_primary" in required_factor_keys(["aluminium_can_330ml"], "PT")
    assert "aluminium_wrought_mix" not in required_factor_keys(["aluminium_can_330ml"], "PT")


def test_washing_electricity_includes_the_one_measurement():
    """0.044 kWh per bottle (Tua, Grosso and Rigamonti 2020) lies inside the prior since 16 November 2026."""
    dist, params = cat.REFILLABLE["wash_kwh"][:2]
    assert dist == "uniform" and params["low"] < 0.044 < params["high"]

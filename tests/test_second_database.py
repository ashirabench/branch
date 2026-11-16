"""Second database (ELCD 3.2): the mapping, the factors computed from the file, and the hybrid."""
import json
import os
import sys

import pytest

from branch.builder import required_factor_keys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "experiments"))
from make_hybrid_factors import CATEGORIES, IPCC, hybrid  # noqa: E402

BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]


def load(name):
    with open(os.path.join(ROOT, "data", "second_database", name)) as fh:
        return json.load(fh)


def fake_base():
    keys = sorted(set(required_factor_keys(BENCH, "PT")) | set(required_factor_keys(BENCH, "DE")))
    units = {k: f["unit"] for k, f in load("elcd32_factors.json")["factors"].items()}
    return {"database": "bafu2026", "method": "EF 3.1 Method (adapted)", "citation": "BAFU", "path": "x.json",
            "factors": {k: {"process": k, "id": k, "location": "x", "unit": units.get(k, "kg"), "flow": k,
                            "impacts": {"Climate change": 1.0, "Acidification": 1.0, "Water use": 1.0}} for k in keys}}


def test_the_map_covers_exactly_the_factors_of_the_twelve_cases():
    m = load("elcd32_map.json")
    needed = set(required_factor_keys(BENCH, "PT")) | set(required_factor_keys(BENCH, "DE"))
    assert set(m["mapped"]) | set(m["gaps"]) == needed
    assert not set(m["mapped"]) & set(m["gaps"])
    assert len(m["mapped"]) == 21 and len(m["gaps"]) == 8


def test_no_bafu_value_is_published_with_the_map():
    text = json.dumps(load("elcd32_map.json"))
    assert "bafu" not in text.lower().replace("branch", "") and "climate" not in text


def test_the_elcd_factors_follow_the_map_and_name_their_owner():
    m, f = load("elcd32_map.json"), load("elcd32_factors.json")
    assert set(f["factors"]) == set(m["mapped"]) and f["not_in_elcd"] == m["gaps"]
    for key, x in f["factors"].items():
        assert (x["process"], x["location"], x["id"], x["unit"]) == tuple(m["mapped"][key][k] for k in
                                                                         ("process", "location", "ref_id", "unit"))
        assert x["owner"] and set(x["impacts"]) == set(CATEGORIES) | {IPCC}
        assert all(v > 0 for v in x["impacts"].values()), key
    # no energy credit: the incineration data sets are the ones with a reference of 1000 kg
    assert f["factors"]["disposal_polyethylene_terephthalate_incineration"]["reference"] == "-1000 kg"
    assert f["factors"]["electricity_mv_PT"]["reference"] == "3.6 MJ"


def test_values_that_can_be_checked_by_hand():
    f = load("elcd32_factors.json")["factors"]
    pet = f["disposal_polyethylene_terephthalate_incineration"]["impacts"]["Climate change"]
    assert 2.29 * 0.99 < pet < 2.29 * 1.10          # carbon of PET (62.5%) burnt to CO2 is 2.29 kg per kg
    assert f["glass_packaging_white"]["impacts"] == f["glass_packaging_green"]["impacts"]
    for x in f.values():                             # IPCC 2021 weighs methane less than EF 3.0, nothing else differs much
        assert 0.8 < x["impacts"][IPCC] / x["impacts"]["Climate change"] <= 1.001


def test_placebo_replacing_nothing_gives_back_the_base_file():
    base = fake_base()
    out = hybrid(base, load("elcd32_factors.json"), replace="none")
    assert out["factors"] == base["factors"] and "replaced_by_elcd" not in out
    assert out["database"] == base["database"]


def test_hybrid_replaces_the_21_and_leaves_the_8():
    base, elcd = fake_base(), load("elcd32_factors.json")
    out = hybrid(base, elcd)
    assert len(out["replaced_by_elcd"]) == 21
    for key, f in out["factors"].items():
        if key in elcd["factors"]:
            assert f["database"] == "ELCD 3.2" and set(f["impacts"]) == set(CATEGORIES)
            assert f["impacts"]["Climate change"] == elcd["factors"][key]["impacts"]["Climate change"]
        else:
            assert f == base["factors"][key]
    assert base["factors"]["electricity_mv_PT"]["impacts"]["Climate change"] == 1.0      # the base is not touched
    ipcc = hybrid(base, elcd, climate="ipcc2021")
    assert ipcc["factors"]["disposal_board_landfill"]["impacts"]["Climate change"] == \
        elcd["factors"]["disposal_board_landfill"]["impacts"][IPCC]


def test_another_category_fails_on_a_replaced_factor_instead_of_mixing_databases():
    from branch.builder import factor
    out = hybrid(fake_base(), load("elcd32_factors.json"))
    assert factor(out, "aluminium_primary", "Water use") == 1.0
    with pytest.raises(KeyError):
        factor(out, "electricity_mv_PT", "Water use")


def test_branch_factors_points_every_command_at_another_file(tmp_path, monkeypatch):
    from branch.real_cases import load_factors
    path = tmp_path / "other.json"
    path.write_text(json.dumps(hybrid(fake_base(), load("elcd32_factors.json"))))
    monkeypatch.setenv("BRANCH_FACTORS", str(path))
    assert load_factors()["path"] == str(path) and len(load_factors()["replaced_by_elcd"]) == 21

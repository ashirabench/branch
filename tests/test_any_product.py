"""Products that are not containers: inputs chosen from the database by process name."""
import os
from types import SimpleNamespace

import numpy as np
import pytest

from branch import connector, webapp
from branch.agent import run_agent
from branch.builder import load_spec, parse_process_key, process_key, required_factor_keys
from branch.olca_bridge import point_world
from branch.olca_extract import resolve
from branch.real_cases import assumptions, compare
from tests.test_builder import BENCH, CAT

ROOT = os.path.join(os.path.dirname(__file__), "..")
COTTON = os.path.join(ROOT, "data", "examples", "cotton_bag.json")
PPBAG = os.path.join(ROOT, "data", "examples", "pp_bag.json")


def synthetic(specs, region="PT"):
    keys = required_factor_keys(specs, region)
    rng = np.random.default_rng(0)
    return {"method": "synthetic", "path": "synthetic.json", "citation": "synthetic",
            "factors": {k: {"unit": "kg", "process": k, "impacts": {CAT: float(rng.uniform(0.5, 5))}} for k in keys}}


def test_process_keys_round_trip():
    assert parse_process_key(process_key("Tap  water, at user", "RER")) == ("Tap water, at user", "RER")
    assert parse_process_key(process_key("Viscose fibres, at plant")) == ("Viscose fibres, at plant", None)
    assert parse_process_key("pet_granulate_bottle_grade") is None


def test_the_two_example_bags_build_and_the_result_is_amount_times_factor():
    f = synthetic([COTTON, PPBAG])
    assert all(k.startswith("proc:") for k in f["factors"])          # no container rule is involved
    model = compare(COTTON, PPBAG, region="PT", factors=f)
    assert model.meta["functional_unit"] == "carrying the shopping of one household for one year"
    assert {t.name.rsplit(".", 1)[-1] for t in model.terms} == {"material", "manufacturing", "transport", "end_of_life"}
    assert len(model.choices) == 7 and len(assumptions(model)) == 7   # every range is a labelled assumption
    world = point_world(model, {"fixed": {}})
    inv = model.inventory(world)
    total = {lab: sum(a * f["factors"][k]["impacts"][CAT] for k, a in ex.items()) for lab, ex in inv.items()}
    assert np.isclose(float(model.delta_at(world)), total[model.label_a] - total[model.label_b])
    result = run_agent(model, lambda name: None, n_samples=2000)
    assert result["verdict"]


def test_a_known_amount_is_not_asked_and_a_range_is():
    a = {"id": "a", "name": "A", "exchanges": [
        {"id": "Main Fabric", "stage": "material", "process": "Textile, woven cotton, at plant", "amount": 0.2},
        {"id": "power", "stage": "manufacturing", "process": "Electricity, low voltage, at grid",
         "location": "PT", "amount": [0.1, 0.9]}]}
    b = {"id": "b", "name": "B", "units_per_functional_unit": 3,
         "exchanges": [{"id": "fabric", "stage": "material", "process": "Viscose fibres, at plant", "amount": 0.2}]}
    f = synthetic([a, b])
    model = compare(a, b, region="PT", factors=f)
    assert [c.name for c in model.choices] == ["a.power.amount"]
    c = model.choices[0]
    assert c.source.startswith("ASSUMPTION:") and (c.ppf(0.0), c.ppf(1.0)) == (0.1, 0.9)
    assert "Electricity, low voltage, at grid" in c.question
    assert model.meta["functional_unit"] == "the same use of one product"
    inv = model.inventory(point_world(model, {"fixed": {}}))
    assert np.isclose(inv["B"]["proc:Viscose fibres, at plant"], 0.6)          # three bags for the same use
    assert np.isclose(inv["A"]["proc:Electricity, low voltage, at grid @PT"], 0.5)


def test_bad_inputs_are_refused_in_plain_words():
    ok = {"id": "x", "stage": "use", "process": "Tap water, at user", "amount": 1}
    for bad, word in (({**ok, "amount": [3, 1]}, "range"), ({**ok, "amount": -1}, "negative"),
                      ({**ok, "stage": "kitchen"}, "stage"), ({**ok, "process": ""}, "process name"),
                      ({**ok, "amount": None}, "amount")):
        with pytest.raises(ValueError, match=word):
            load_spec({"id": "p", "name": "P", "exchanges": [bad]})
    with pytest.raises(ValueError, match="no components"):
        load_spec({"id": "p", "name": "P"})
    a = {"id": "a", "name": "A", "functional_unit": "one year of light", "exchanges": [ok]}
    b = {"id": "b", "name": "B", "functional_unit": "one chair", "exchanges": [ok]}
    with pytest.raises(ValueError, match="same service"):
        compare(a, b, region="PT", factors=synthetic([a, b]))


def test_a_container_can_also_carry_inputs_from_the_database():
    spec = load_spec("pet_bottle_1l")
    spec["exchanges"] = [{"id": "label ink", "stage": "material", "process": "Printing colour, offset, at plant",
                          "amount": [0.0001, 0.001]}]
    f = synthetic([spec, "glass_refillable_1l"])
    plain = compare("pet_bottle_1l", "glass_refillable_1l", region="PT", factors=f)
    more = compare(spec, "glass_refillable_1l", region="PT", factors=f)
    assert [c.name for c in more.choices if c.name not in plain.by_name] == ["pet.label_ink.amount"]
    assert set(required_factor_keys(BENCH, "PT")) <= set(required_factor_keys(BENCH + [spec], "PT"))


def test_benchmark_products_need_the_same_factors_as_before():
    keys = set(required_factor_keys(["pet_bottle_1l", "glass_refillable_1l"], "PT"))
    assert {"heat_natural_gas_furnace", "tap_water_RER", "lorry_16_32t", "electricity_mv_PT"} <= keys
    assert not any(k.startswith("proc:") for k in keys)


# ------------------------------------------------------------ finding processes by name

def _d(name, location):
    return SimpleNamespace(name=name, location=location, id=f"{name}|{location}", category="c")


DESCS = [_d("Tap water, at user", "RER"), _d("Tap water, at user", "CH"), _d("Viscose fibres, at plant", "GLO"),
         _d("Soap, at plant", "ZZ"), _d("Soap, at plant", "YY"), _d("xx Soap, at plant", "RER")]


def test_a_process_is_found_by_its_exact_name_and_location():
    assert resolve(DESCS, process_key("Viscose fibres, at plant"))[0].location == "GLO"
    assert resolve(DESCS, process_key("viscose  fibres, AT plant"))[0].location == "GLO"
    assert resolve(DESCS, process_key("Tap water, at user", "CH"))[0].location == "CH"
    assert resolve(DESCS, process_key("Tap water, at user"))[0].location == "RER"       # the preferred location
    ref, hits = resolve(DESCS, process_key("Soap, at plant"))                            # two unknown locations
    assert ref is None and len(hits) == 2
    assert resolve(DESCS, process_key("Soap"))[0] is None                                # a part of a name is not a name
    assert resolve(DESCS, process_key("Nothing like this")) == (None, [])


def test_the_app_explains_names_it_could_not_read():
    text = webapp.explain_unresolved({process_key("Soap, at plant"): ["Soap, at plant [ZZ]", "Soap, at plant [YY]"],
                                      process_key("Nothing like this"): []})
    assert '"Soap, at plant @ZZ"' in text and '"Soap, at plant @YY"' in text
    assert 'no process of the open database is called exactly "Nothing like this"' in text


def test_search_lists_names_units_and_marks_shared_names(monkeypatch):
    unit = SimpleNamespace(name="kg")
    proc = SimpleNamespace(exchanges=[SimpleNamespace(is_quantitative_reference=True, unit=unit)])
    fake = SimpleNamespace(get_descriptors=lambda kind: DESCS, get=lambda kind, i: proc)
    monkeypatch.setattr(connector, "client", lambda port=None: fake)
    found = connector.search_processes("water tap")
    assert [(r["name"], r["location"], r["unit"]) for r in found] == [("Tap water, at user", "CH", "kg"),
                                                                    ("Tap water, at user", "RER", "kg")]
    text = webapp.search_text(found)
    assert "Tap water, at user @CH" in text and "| kg |" in text
    assert connector.search_processes("   ") == []
    assert "No process" in webapp.search_text([])


# ---------------------------------------------------------------------------- the form

def test_the_form_describes_a_product_that_is_not_a_container():
    rows = [["fabric", "Materials", "Textile, woven cotton, at plant", "0,10", "0,20"],
            ["washing", "use", "Tap water, at user @RER", 300, None],
            ["", "", "", None, None]]
    spec = webapp.spec_from_fields("Cotton bag", 1, True, [], inputs=rows, units="2", service=" one year of shopping ")
    assert spec["components"] == [] and spec["refillable"] is False
    assert spec["units_per_functional_unit"] == 2 and spec["functional_unit"] == "one year of shopping"
    fabric, washing = spec["exchanges"]
    assert fabric["amount"] == [0.1, 0.2] and fabric["stage"] == "material"
    assert washing["amount"] == 300 and washing["key"] == "proc:Tap water, at user @RER"
    assert webapp.missing_process_keys([spec], {"factors": {washing["key"]: {}}}) == [fabric["key"]]


@pytest.mark.parametrize("row,word", [
    (["x", "use", "", 1, 2], "name of the openLCA process"),
    (["x", "kitchen", "Soap, at plant", 1, 2], "stage"),
    (["x", "use", "Soap, at plant", None, None], "smallest and the largest"),
    (["x", "use", "Soap, at plant", 5, 2], "larger than the largest"),
    (["x", "use", "Soap, at plant", "many", 2], "must be numbers"),
    (["x", "use", "Soap, at plant", -1, 2], "negative"),
])
def test_the_form_refuses_a_bad_input_line_in_plain_words(row, word):
    with pytest.raises(ValueError, match=word):
        webapp.spec_from_fields("Thing", 1, False, [], inputs=[row])


def test_the_form_still_needs_something_to_compare():
    with pytest.raises(ValueError, match="at least one component"):
        webapp.spec_from_fields("Thing", 1, False, [], inputs=[["", "", "", None, None]])
    with pytest.raises(ValueError, match="larger than zero"):
        webapp.spec_from_fields("Thing", 1, False, [["body", "pet", 10]], units=0)


def test_split_toxicity_indicators_have_their_own_names():
    from branch.indicators import describe, is_subcategory
    names = [describe(c)[0] for c in ("Ecotoxicity freshwater", "Ecotoxicity freshwater (organics)",
                                      "Ecotoxicity freshwater (inorganics)", "Human toxicity cancer (inorganics)",
                                      "Human toxicity non-cancer (organics)")]
    assert len(set(names)) == len(names) and names[1].endswith("organics") and names[2].endswith("inorganics")
    assert is_subcategory("Human toxicity cancer (organics)") and not is_subcategory("Human toxicity cancer")
    assert describe("Climate change")[0] == "Climate change" and not is_subcategory("Land use")


def test_reports_of_a_product_that_is_not_a_container_do_not_talk_about_packaging(tmp_path):
    f = synthetic([COTTON, PPBAG])
    model = compare(COTTON, PPBAG, region="PT", factors=f)
    assert model.meta["sources_needed"] == []
    result = run_agent(model, lambda name: None, n_samples=2000)
    from branch.manager_report import _stage_labels, _uses_region
    from branch.report import markdown_report
    assert not _uses_region(model.meta)
    assert _stage_labels(model.meta)["material"] == "Materials"
    text = markdown_report(result, model)
    assert "the region does not enter" in text and "beverage" not in text
    bottles = compare("pet_bottle_1l", "glass_refillable_1l", region="PT", factors=synthetic(BENCH))
    assert _uses_region(bottles.meta) and _stage_labels(bottles.meta)["material"] == "Making the packaging"

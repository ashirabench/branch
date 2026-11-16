"""Materials added as data files (data/materials/): corrugated board."""
import numpy as np

from branch.builder import required_factor_keys
from branch.catalogue import load_materials
from branch.real_cases import assumptions, compare
from tests.test_builder import CAT

BOX = {"id": "box", "name": "Corrugated box", "volume_l": 1.0, "refillable": False,
       "components": [{"id": "box", "material": "corrugated_board", "mass_g": 150}]}
BAG = {"id": "bag", "name": "LDPE mailer", "volume_l": 1.0, "refillable": False,
       "components": [{"id": "bag", "material": "ldpe", "mass_g": 20}]}


def factors(regions=("PT", "DE", "BR")):
    keys = sorted({k for r in regions for k in required_factor_keys([BOX, BAG], r)})
    rng = np.random.default_rng(0)
    return {"method": "synthetic", "path": "synthetic.json", "citation": "synthetic",
            "factors": {k: {"impacts": {CAT: float(rng.uniform(0.01, 5))}} for k in keys}}


def test_corrugated_board_is_in_the_catalogue_with_labelled_priors():
    m = load_materials()["corrugated_board"]
    assert m["conversion"] is None and m["recycled"] is None
    for field in ("recycling_rate", "incineration_share"):
        assert m["end_of_life"][field][2].startswith(("SOURCE:", "ASSUMPTION:"))


def test_a_corrugated_box_builds_in_every_national_region():
    f = factors()
    for region in ("PT", "DE", "BR"):
        model = compare(BOX, BAG, region=region, factors=f)
        names = [c.name for c in model.choices]
        assert "box.corrugated_board.recycling_rate" in names
        assert model.by_name["box.corrugated_board.incineration_share"].source.startswith("SOURCE:")


def test_germany_has_a_sourced_rate_inside_the_default_range():
    f = factors()
    de = compare(BOX, BAG, region="DE", factors=f).by_name["box.corrugated_board.recycling_rate"]
    pt = compare(BOX, BAG, region="PT", factors=f).by_name["box.corrugated_board.recycling_rate"]
    assert de.source.startswith("SOURCE:") and "86.6%" in de.source
    assert abs(float(de._frozen().mean()) - 0.866) < 0.005
    assert pt.source.startswith("ASSUMPTION:")
    assert pt.ppf(0.0) <= 0.866 <= pt.ppf(1.0)          # the published German value is inside the default
    assert "box.corrugated_board.recycling_rate" in assumptions(compare(BOX, BAG, region="PT", factors=f))


# ---------------------------------------------------------------- every added material

import glob  # noqa: E402
import os  # noqa: E402

import pytest  # noqa: E402

from branch import catalogue as cat  # noqa: E402
from branch.demo_factors import demo_factors  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
ADDED = sorted(k for k in load_materials() if k not in cat.MATERIALS)
EXAMPLES = sorted(glob.glob(os.path.join(ROOT, "data", "examples", "*.json")))


def synthetic(specs, regions=("PT", "DE", "BR")):
    keys = sorted({k for r in regions for k in required_factor_keys(specs, r)})
    rng = np.random.default_rng(0)
    return {"method": "synthetic", "path": "synthetic.json", "citation": "synthetic",
            "factors": {k: {"impacts": {CAT: float(rng.uniform(0.01, 5))}} for k in keys}}


@pytest.mark.parametrize("mid", ADDED)
def test_every_added_material_has_labelled_priors_and_known_datasets(mid):
    from branch.olca_extract import PROCESSES
    m = load_materials()[mid]
    assert m["datasets_source"].startswith("SOURCE:")
    for field in ("recycling_rate", "incineration_share"):
        assert m["end_of_life"][field][2].startswith(("SOURCE:", "ASSUMPTION:"))
    assert abs(sum(w for _, w in m["datasets"].values()) - 1) < 1e-9
    assert cat.material_keys(m) <= set(PROCESSES), "every factor key needs a dataset name in olca_extract.PROCESSES"


def test_every_added_material_has_an_example_product():
    used = set()
    for path in EXAMPLES:
        import json
        with open(path) as fh:
            spec = json.load(fh)
        used |= {c["material"] for c in spec.get("components", [])}
        for c in spec.get("components", []):
            assert c["mass_prior"][2].startswith("ASSUMPTION:")
    assert set(ADDED) <= used


@pytest.mark.parametrize("path", EXAMPLES, ids=os.path.basename)
def test_every_example_builds_in_the_three_national_regions(path):
    f = synthetic([path, "pet_bottle_1l"])
    for region in ("PT", "DE", "BR"):
        model = compare(path, "pet_bottle_1l", region=region, factors=f)
        for c in model.choices:
            assert c.source.startswith(("SOURCE:", "ASSUMPTION:")), c.name
        share = [c for c in model.choices if c.name.endswith(".incineration_share")]
        assert share and all(c.source.startswith("SOURCE:") for c in share)


def test_germany_has_sourced_rates_for_paper_cartonboard_and_steel():
    for path, choice, value in (("paper_bag_1l.json", "pbag.kraft_paper.recycling_rate", 0.866),
                                ("carton_box_1l.json", "cbox.cartonboard.recycling_rate", 0.866),
                                ("steel_can_05l.json", "stc.steel.recycling_rate", 0.854)):
        path = os.path.join(ROOT, "data", "examples", path)
        f = synthetic([path, "pet_bottle_1l"])
        de = compare(path, "pet_bottle_1l", region="DE", factors=f).by_name[choice]
        pt = compare(path, "pet_bottle_1l", region="PT", factors=f).by_name[choice]
        assert de.source.startswith("SOURCE:") and pt.source.startswith("ASSUMPTION:")
        assert abs(float(de._frozen().mean()) - value) < 0.01
        assert pt.ppf(0.0) <= value <= pt.ppf(1.0)


def test_only_materials_with_factors_are_offered():
    from branch import webapp
    demo = demo_factors()
    ready, waiting = cat.split_by_factors(demo)
    assert "pet" in ready and "corrugated_board" in ready
    assert "pp" in waiting and "steel" in waiting           # the demo values do not cover them
    assert set(webapp.materials(demo)) == set(ready)
    assert "polypropylene" in webapp.materials_waiting(demo)
    assert set(webapp.materials()) == set(load_materials())


def test_every_plastic_uses_the_disposal_datasets_of_its_own_polymer():
    """A plastics mixture dataset is a stand-in. It is allowed only where the database has no
    current dataset of the polymer (list of BAFU:2026 read on 14 November 2026)."""
    from branch import catalogue as cat
    from branch.olca_extract import PROCESSES
    mats = {**cat.MATERIALS, **cat.load_materials()}
    polymer = {"pet": "polyethylene terephtalate", "hdpe": "polyethylene, 0.4%", "ldpe": "polyethylene, 0.4%",
               "pp": "polypropylene", "ps": "polystyrene, 0.2%", "eps": "expanded polystyrene", "pvc": "polyvinylchloride"}
    stand_in_allowed = {("pet", "landfill"), ("pp", "landfill"), ("pla", "incineration"), ("pla", "landfill")}
    same_polymer_allowed = {("eps", "landfill"): "polystyrene, 0.2%"}
    for mid in list(polymer) + ["pla"]:
        eol = mats[mid]["end_of_life"]
        for route in ("incineration", "landfill"):
            name = PROCESSES[eol[route]][0].lower()
            if (mid, route) in stand_in_allowed:
                assert "plastics, mixture" in name, (mid, route, name)
            elif (mid, route) in same_polymer_allowed:
                assert same_polymer_allowed[(mid, route)] in name, (mid, route, name)
            else:
                assert polymer[mid] in name and "mixture" not in name, (mid, route, name)
            assert not name.startswith("xx "), "obsolete datasets of the database are not used"


def test_the_materials_validation_reads_every_example_file():
    """Examples described only by processes have no component; the validation must skip them, not stop."""
    import importlib.util
    import os
    pytest.importorskip("olca_schema")
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments", "openlca", "validate_materials.py")
    spec = importlib.util.spec_from_file_location("validate_materials", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from branch import catalogue as cat
    added = {k: v for k, v in cat.load_materials().items() if k not in cat.MATERIALS}
    found = list(mod.variants(added))
    assert {mid for _, _, mid, _ in found} == set(added)

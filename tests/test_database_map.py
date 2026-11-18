"""The map of the database: which process stands for each thing BRANCH needs (data/databases/)."""
import importlib.util
import json
import os
from types import SimpleNamespace

import pytest

pytest.importorskip("olca_schema")
from branch import olca_extract as x  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _audit():
    path = os.path.join(ROOT, "experiments", "openlca", "audit_factors.py")
    spec = importlib.util.spec_from_file_location("audit_factors", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def default_map():
    yield
    x.use_database_map(x.DEFAULT_MAP)


def test_the_map_of_bafu_is_complete_and_holds_names_only():
    m = x.load_database_map("bafu2026")
    assert m["database"] == "bafu2026" and "BAFU:2026" in m["citation"]
    assert x.PROCESSES == {k: v["names"] for k, v in m["datasets"].items()}
    assert x.LOCATION_PREFERENCE == m["location_preference"]

    def leaves(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from leaves(v)
        elif isinstance(node, list):
            for v in node:
                yield from leaves(v)
        else:
            yield node
    assert all(isinstance(v, str) for v in leaves(m)), "the map carries names and units, never a value of the database"


def test_the_units_of_the_map_are_the_ones_the_audit_expects():
    audit = _audit()
    for key, entry in x.DATABASE_MAP["datasets"].items():
        assert entry["unit"] in audit.expected_units(key), (key, entry["unit"])


def test_every_material_and_region_finds_its_keys_in_the_map():
    import re

    from branch.builder import required_factor_keys
    from branch.regions import list_regions
    known = set(x.DATABASE_MAP["datasets"])
    bench = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
    for code in list_regions():
        if code == "GLO":
            continue
        missing = {k for k in set(required_factor_keys(bench, code)) - known
                   if not x.GRID_PATTERN.pattern or not re.fullmatch(r"electricity_mv_([A-Z]{2}|ENTSO-E)", k)}
        assert not missing, (code, missing)


def test_another_database_needs_only_another_map(tmp_path, default_map):
    """A second map with other names: the same code then finds the processes of that database."""
    other = {"database": "mydb", "citation": "My database, version 1",
             "location_preference": ["EU-27", "GLO"],
             "grid_name_pattern": r"^Electricity grid mix, (\w+)$",
             "datasets": {"pet_granulate_bottle_grade": {"names": ["PET granulate, bottle grade"], "unit": "kg"},
                          "lorry_16_32t": {"names": ["Lorry transport, 16 to 32 t"], "unit": "t*km"}}}
    path = tmp_path / "mydb.json"
    path.write_text(json.dumps(other))
    before = x.PROCESSES                       # other modules hold this very object
    x.use_database_map(str(path))
    assert before is x.PROCESSES and set(x.PROCESSES) == {"pet_granulate_bottle_grade", "lorry_16_32t"}
    assert x.citation_for("mydb") == "My database, version 1"
    assert x.GRID_PATTERN.match("Electricity grid mix, DE").group(1) == "DE"
    database = [SimpleNamespace(name="PET granulate, bottle grade", location="EU-27"),
                SimpleNamespace(name="PET granulate, bottle grade", location="GLO"),
                SimpleNamespace(name="Lorry transport, 16 to 32 t", location="GLO"),
                SimpleNamespace(name="Something else", location="GLO")]
    found, _ = x.resolve(database, "pet_granulate_bottle_grade")
    assert found.location == "EU-27", "same name twice: the preferred location wins"
    assert x.resolve(database, "lorry_16_32t")[0].name == "Lorry transport, 16 to 32 t"
    x.use_database_map(x.DEFAULT_MAP)
    assert "glass_packaging_white" in x.PROCESSES and x.citation_for("bafu2026").endswith("BAFU:2026")


def test_a_map_with_a_gap_is_refused_in_words(tmp_path):
    good = {"database": "d", "citation": "c", "location_preference": [], "grid_name_pattern": "^x$",
            "datasets": {"k": {"names": ["n"], "unit": "kg"}}}
    for broken, word in ((dict(good, datasets={"k": {"names": ["n"]}}), "unit"),
                         (dict(good, datasets={"k": {"names": [], "unit": "kg"}}), "names"),
                         ({k: v for k, v in good.items() if k != "citation"}, "citation")):
        path = tmp_path / "broken.json"
        path.write_text(json.dumps(broken))
        with pytest.raises(ValueError) as err:
            x.load_database_map(str(path))
        assert word in str(err.value)
    with pytest.raises(FileNotFoundError) as err:
        x.load_database_map("no_such_database")
    assert "BRING_YOUR_DATABASE" in str(err.value)


def test_the_map_is_among_the_data_every_delivery_carries():
    from branch.paths import RUNTIME_DATA
    assert "databases" in RUNTIME_DATA, "without data/databases the installed application cannot start"

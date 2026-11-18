"""The map of the database: which process stands for each thing BRANCH needs (data/databases/)."""
import importlib.util
import json
import os
import re
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


def test_the_map_of_bafu_is_complete_and_holds_names_only():
    m = x.load_database_map("bafu2026")
    assert m["database"] == "bafu2026" and "BAFU:2026" in m["citation"]
    assert x.PROCESSES == {k: v["names"] for k, v in m["datasets"].items()}
    assert list(x.LOCATION_PREFERENCE) == m["location_preference"]

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


def test_another_database_needs_only_another_map(tmp_path):
    """A second map with other names: the same code then finds the processes of that database, and the
    map of the default database is not touched."""
    other = {"database": "mydb", "citation": "My database, version 1",
             "location_preference": ["EU-27", "GLO"],
             "grid_name_pattern": r"^Electricity grid mix, (\w+)$",
             "datasets": {"pet_granulate_bottle_grade": {"names": ["PET granulate, bottle grade"], "unit": "kg"},
                          "lorry_16_32t": {"names": ["Lorry transport, 16 to 32 t"], "unit": "t*km"}}}
    path = tmp_path / "mydb.json"
    path.write_text(json.dumps(other))
    before = json.dumps(x.DATABASE_MAP, sort_keys=True)
    m = x.load_database_map(str(path))
    names, preference = x.names_of(m), m["location_preference"]
    assert set(names) == {"pet_granulate_bottle_grade", "lorry_16_32t"}
    assert x.citation_for("mydb", m) == "My database, version 1"
    database = [SimpleNamespace(name="PET granulate, bottle grade", location="EU-27"),
                SimpleNamespace(name="PET granulate, bottle grade", location="GLO"),
                SimpleNamespace(name="Lorry transport, 16 to 32 t", location="GLO"),
                SimpleNamespace(name="Electricity grid mix, DE", location="DE"),
                SimpleNamespace(name="Something else", location="GLO")]
    found, _ = x.resolve(database, "pet_granulate_bottle_grade", names, preference)
    assert found.location == "EU-27", "same name twice: the preferred location wins"
    assert x.resolve(database, "lorry_16_32t", names, preference)[0].name == "Lorry transport, 16 to 32 t"
    assert list(x.grid_processes(database, re.compile(m["grid_name_pattern"]))) == ["electricity_mv_DE"]
    assert json.dumps(x.DATABASE_MAP, sort_keys=True) == before and "glass_packaging_white" in x.PROCESSES


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

"""The scripts that check BRANCH against openLCA, run from start to end against the openLCA of the tests.

The fake recomputes each product from the exchanges that were actually sent (tests/fake_openlca.py), so
these tests follow the whole path of a real check: model, objects sent, calculation, comparison, table,
and the removal of everything that was written.
"""
import csv
import importlib.util
import json
import os
import sys

import pytest

pytest.importorskip("olca_schema")
pytest.importorskip("olca_ipc")
from branch import olca_bridge  # noqa: E402
from tests.fake_openlca import FakeOpenLCA  # noqa: E402
from tests.test_builder import fake_factors  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def script(name):
    path = os.path.join(ROOT, "experiments", "openlca", name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def openlca(monkeypatch, tmp_path):
    """A factor file on disk, and a fake openLCA that holds a process for each of its factors."""
    factors = fake_factors()
    client = FakeOpenLCA(factors, waste_keys={"disposal_glass_landfill"})
    path = tmp_path / "factors.json"
    path.write_text(json.dumps({k: v for k, v in factors.items() if k != "path"}))
    monkeypatch.setenv("BRANCH_FACTORS", str(path))
    monkeypatch.setattr(olca_bridge, "client", lambda port=8080: client)
    monkeypatch.chdir(tmp_path)
    return client


def test_the_check_of_whole_products_agrees_and_cleans_up(openlca, monkeypatch, tmp_path, capsys):
    out = tmp_path / "validation.csv"
    monkeypatch.setattr(sys, "argv", ["validate_openlca.py", "--regions", "PT", "DE", "--out", str(out)])
    script("validate_openlca.py").main()
    rows = list(csv.DictReader(open(out)))
    assert len(rows) == 24, "6 pairs, 2 products, 2 regions"
    assert all(float(r["relative_difference"]) < 1e-12 and not r["cause"] for r in rows)
    assert "24 products checked, largest relative difference" in capsys.readouterr().out
    assert openlca.left_behind() == [], "everything the check wrote is removed again"


def test_a_wrong_factor_is_found_and_named(openlca, monkeypatch, tmp_path, capsys):
    """openLCA and the factor file disagree on one dataset: the table names it."""
    openlca.factors = json.loads(json.dumps(openlca.factors))
    for category in openlca.factors["lorry_16_32t"]["impacts"]:
        openlca.factors["lorry_16_32t"]["impacts"][category] *= 2
    out = tmp_path / "validation.csv"
    monkeypatch.setattr(sys, "argv", ["validate_openlca.py", "--regions", "PT", "--pairs", "1", "--out", str(out)])
    script("validate_openlca.py").main()
    rows = list(csv.DictReader(open(out)))
    assert all(float(r["relative_difference"]) > 1e-4 and "lorry_16_32t x2" in r["cause"] for r in rows)
    assert not [k for k in openlca.left_behind() if "check" in str(getattr(openlca.store[k], "name", ""))]


def test_a_region_that_cannot_be_built_is_a_row_and_an_exit(openlca, monkeypatch, tmp_path):
    out = tmp_path / "validation.csv"
    monkeypatch.setattr(sys, "argv", ["validate_openlca.py", "--regions", "PT", "XX", "--pairs", "1", "--out", str(out)])
    with pytest.raises(SystemExit) as stop:
        script("validate_openlca.py").main()
    assert "could not be checked" in str(stop.value)
    rows = list(csv.DictReader(open(out)))
    assert [r["region"] for r in rows if r["cause"].startswith("error")] == ["XX"]


def test_the_check_of_the_added_materials_runs_and_cleans_up(openlca, monkeypatch, tmp_path, capsys):
    module = script("validate_materials.py")
    monkeypatch.setattr(module, "OUT", str(tmp_path / "materials.csv"))
    monkeypatch.setattr(sys, "argv", ["validate_materials.py", "--regions", "PT"])
    with pytest.raises(SystemExit) as stop:        # the synthetic factor file lacks the added materials
        module.main()
    assert "could not be checked" in str(stop.value)
    rows = list(csv.DictReader(open(tmp_path / "materials.csv")))
    assert rows and all(r["cause"].startswith(("skipped", "error")) or float(r["relative_difference"]) < 1e-12 for r in rows)
    assert openlca.left_behind() == []


def test_the_check_of_the_probability_world_by_world(openlca, monkeypatch, tmp_path, capsys):
    out = tmp_path / "probability.csv"
    monkeypatch.setattr(sys, "argv", ["validate_probability.py", "--worlds", "12", "--n", "4000", "--out", str(out)])
    script("validate_probability.py").main()
    rows = list(csv.DictReader(open(out)))
    summary = next(csv.DictReader(open(str(out).replace(".csv", "_summary.csv"))))
    assert len(rows) == 24 and all(float(r["relative_difference"]) < 1e-12 for r in rows)
    assert summary["worlds"] == "12" and summary["same_winner"] == "12"
    assert float(summary["largest_relative_difference"]) < 1e-12
    text = capsys.readouterr().out
    assert "12 worlds: largest relative difference" in text and "P(A lower) from openLCA on these worlds" in text
    assert openlca.left_behind() == [], "200 worlds must not leave 400 processes in the database"


def _demo(monkeypatch, *argv):
    from tests.test_builder import CAT
    path = os.path.join(ROOT, "examples", "demo_cli.py")
    spec = importlib.util.spec_from_file_location("demo_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["demo_cli.py", "--defaults", "--category", CAT, *argv])
    module.main()


def test_the_command_line_demo_sends_checks_and_explains(openlca, monkeypatch, tmp_path, capsys):
    _demo(monkeypatch, "--push", "--backup-confirmed", "--diagnose")
    text = capsys.readouterr().out
    assert "Sent to openLCA (category BRANCH)" in text and "Per exchange check in openLCA" in text
    assert "<-- differs" not in text
    assert (tmp_path / "outputs" / "report.md").exists()


def test_the_command_line_demo_writes_the_file_to_import(openlca, monkeypatch, tmp_path, capsys):
    target = tmp_path / "branch.zip"
    _demo(monkeypatch, "--jsonld", str(target))
    assert target.exists() and f"Saved {target}" in capsys.readouterr().out
    assert not [k for k in openlca.left_behind() if str(k).startswith("system-")], "writing a file sends nothing"

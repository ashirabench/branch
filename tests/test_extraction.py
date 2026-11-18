"""Reading the unit factors from openLCA, against an openLCA made for the test.

The fake database holds one process for every name of the map, a second process with the same name in
another location, and one process that openLCA cannot calculate. The function of the package
(olca_extract.extract) and the command (experiments/openlca/extract_factors.py) are both run on it.
"""
import importlib.util
import json
import os
import sys
from types import SimpleNamespace

import pytest

o = pytest.importorskip("olca_schema")
pytest.importorskip("olca_ipc")
from branch import olca_extract  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROKEN = "disposal_glass_landfill"          # openLCA fails on this one
TWICE = "pet_granulate_bottle_grade"        # two processes share this name


class FakeResult:
    def __init__(self, impacts):
        self.impacts, self.disposed = impacts, False

    def wait_until_ready(self):
        pass

    def get_total_impacts(self):
        return [SimpleNamespace(impact_category=SimpleNamespace(name=k), amount=v) for k, v in self.impacts.items()]

    def dispose(self):
        self.disposed = True


class FakeOpenLCA:
    """As much of olca_ipc.Client as the extraction uses."""

    def __init__(self):
        self.processes, self.systems, self.calculated = {}, set(), []
        for i, (key, names) in enumerate(olca_extract.PROCESSES.items()):
            self.add(names[0], "RER", 1.0 + i, key)
        self.add(olca_extract.PROCESSES[TWICE][0], "CH", 99.0, TWICE)
        self.add("Electricity, medium voltage, production FR, at grid", "FR", 0.07, "grid FR")
        self.add("Cotton fibres, at farm", "GLO", 3.0, "cotton")

    def add(self, name, location, value, key):
        pid = f"p{len(self.processes):04d}"
        ref = o.Exchange(flow=o.Ref(id=f"f-{pid}", name=name), unit=o.Ref(id="u", name="kg"),
                         flow_property=o.Ref(id="fp"), amount=1.0, is_quantitative_reference=True)
        self.processes[pid] = (o.Process(id=pid, name=name, exchanges=[ref], location=o.Ref(id=location, name=location)),
                               value, key)

    def get_descriptors(self, kind):
        if kind is o.ImpactMethod:
            return [o.Ref(id="m1", name="EF 3.1 Method (adapted)"), o.Ref(id="m2", name="Other method")]
        return [o.Ref(id=p.id, name=p.name, location=p.location.name) for p, _, _ in self.processes.values()]

    def get(self, kind, uid):
        return self.processes[uid][0]

    def create_product_system(self, ref, linking=None):
        self.systems.add(ref.id)
        return o.Ref(id=ref.id)

    def calculate(self, setup):
        _, value, key = self.processes[setup.target.id]
        if key == BROKEN:
            raise RuntimeError("openLCA could not solve this system")
        self.calculated.append(key)
        return FakeResult({"Climate change": value, "Acidification": value / 10})

    def delete(self, ref):
        self.systems.discard(ref.id)


def test_every_name_of_the_map_is_read_and_the_file_says_what_was_not(tmp_path):
    client, path = FakeOpenLCA(), tmp_path / "factors.json"
    out = olca_extract.extract(client, str(path), all_grids=True, progress=lambda *a: None)
    saved = json.loads(path.read_text())
    assert saved == out and saved["database"] == "bafu2026" and saved["method"] == "EF 3.1 Method (adapted)"
    assert set(saved["factors"]) == set(olca_extract.PROCESSES) - {BROKEN} | {"electricity_mv_FR"}
    assert saved["unresolved"] == {BROKEN: ["calculation failed: openLCA could not solve this system"]}
    one = saved["factors"]["glass_packaging_white"]
    assert one["unit"] == "kg" and set(one["impacts"]) == {"Climate change", "Acidification"}
    assert saved["factors"][TWICE]["location"] == "RER", "of two processes with one name, the preferred location"
    assert not client.systems, "every product system built for a calculation is deleted again"


def test_an_update_reads_only_what_is_missing_and_keeps_chosen_processes(tmp_path):
    client, path = FakeOpenLCA(), str(tmp_path / "factors.json")
    olca_extract.extract(client, path, all_grids=False, keys=["glass_packaging_white", "proc:cotton fibres, at farm"],
                         progress=lambda *a: None)
    client.calculated.clear()
    out = olca_extract.extract(client, path, all_grids=False, keys=["glass_packaging_white", "lorry_16_32t"],
                               update=True, progress=lambda *a: None)
    assert client.calculated == ["lorry_16_32t"]
    assert {"glass_packaging_white", "lorry_16_32t", "proc:cotton fibres, at farm"} <= set(out["factors"])
    client.calculated.clear()
    full = olca_extract.extract(client, path, all_grids=False, progress=lambda *a: None)      # from scratch
    assert "proc:cotton fibres, at farm" in full["factors"], "a full extraction keeps the processes chosen by name"


def _command(monkeypatch, tmp_path, *argv):
    """Run experiments/openlca/extract_factors.py with these arguments against the fake openLCA."""
    import olca_ipc
    monkeypatch.setattr(olca_ipc, "Client", lambda port=8080: FakeOpenLCA())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["extract_factors.py", *argv])
    spec = importlib.util.spec_from_file_location(
        "extract_factors", os.path.join(ROOT, "experiments", "openlca", "extract_factors.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_command_writes_the_file_the_guides_describe(monkeypatch, tmp_path, capsys):
    _command(monkeypatch, tmp_path, "--method", "EF 3.1").main()
    text = capsys.readouterr().out
    saved = json.loads((tmp_path / "data" / "factors" / "bafu2026_EF_3_1_Method_adapted_.json").read_text())
    n = len(olca_extract.PROCESSES) - 1
    assert f"saved data/factors/bafu2026_EF_3_1_Method_adapted_.json: {n} factors, 1 unresolved" in text
    assert len(saved["factors"]) == n and "electricity_mv_FR" not in saved["factors"]


def test_the_command_reads_what_two_products_need_and_stops_when_one_is_missing(monkeypatch, tmp_path, capsys):
    _command(monkeypatch, tmp_path, "--specs", "pet_bottle_1l", "aluminium_can_330ml", "--region", "PT").main()
    saved = json.loads((tmp_path / "data" / "factors" / "bafu2026_EF_3_1_Method_adapted_.json").read_text())
    assert "0 unresolved" in capsys.readouterr().out
    assert TWICE in saved["factors"] and "glass_packaging_white" not in saved["factors"]
    with pytest.raises(SystemExit):
        _command(monkeypatch, tmp_path, "--only", BROKEN).main()
    assert f"NOT READ: {BROKEN}: calculation failed" in capsys.readouterr().out


def test_the_command_lists_methods_and_finds_processes(monkeypatch, tmp_path, capsys):
    _command(monkeypatch, tmp_path, "--methods").main()
    assert "EF 3.1 Method (adapted)" in capsys.readouterr().out
    _command(monkeypatch, tmp_path, "--find", "cotton").main()
    assert "Cotton fibres, at farm   [GLO]" in capsys.readouterr().out

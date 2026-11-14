"""Inventory, what if analysis and the openLCA connector, without openLCA:
a fake IPC client stands in for the open database."""
import uuid

import numpy as np
import pytest

from branch.agent import run_agent
from branch.builder import build_model, factor
from branch.cases import draw_truth, toy_packaging
from branch.montecarlo import State, p_a_lower
from branch.report import markdown_report
from branch.whatif import point_world, reversals, stages
from tests.test_builder import BENCH, fake_factors

o = pytest.importorskip("olca_schema")
CAT = "Climate change"


@pytest.mark.parametrize("a,b", [(x, y) for x in BENCH for y in BENCH if x != y])
def test_inventory_times_factors_equals_engine(a, b):
    data = fake_factors()
    m = build_model(a, b, "PT", CAT, data)
    S = m.sample(40, seed=5)
    for r in range(S.shape[0]):
        w = {c.name: float(S[r, j]) for j, c in enumerate(m.choices)}
        inv = m.inventory(w)
        total = {k: sum(x * factor(data, key, CAT) for key, x in v.items()) for k, v in inv.items()}
        assert np.isclose(total[m.label_a] - total[m.label_b], m.delta_at(w), rtol=1e-10)


def test_reversals_really_reverse():
    hits = 0
    for seed in range(6):
        m = toy_packaging()
        t = draw_truth(m, seed)
        r = run_agent(m, lambda n: t[n], n_samples=4000, truth=t, seed=seed)
        st = State(m, m.sample(r["n_samples"], r["seed"]))
        for k, v in r["fixed"].items():
            if k in st.open:
                st.fix(k, v)
        before = float(p_a_lower(st.delta)) >= 0.5
        for rev in reversals(m, r):
            hits += 1
            c = m.by_name[rev["name"]]
            v = c.encode(rev["reverses_at"]) if c.kind == "categorical" else rev["reverses_at"]
            if rev["name"] in st.open:
                st2 = State(m, st.S)
                st2.fix(rev["name"], v)
            else:
                S2 = st.S.copy()
                S2[:, m.idx[rev["name"]]] = v
                st2 = State(m, S2)
            assert (float(p_a_lower(st2.delta)) >= 0.5) != before
    assert hits > 0


def test_stages_add_up_and_report_shows_end_of_life():
    m = build_model("aluminium_can_330ml", "beverage_carton_1l", "DE", CAT, fake_factors())
    t = draw_truth(m, 0)
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t)
    st = stages(m, r)
    for label, (mean, _, _) in r["impacts"].items():
        assert np.isclose(sum(st[label].values()), mean, rtol=1e-9)
    rep = markdown_report(r, m)
    assert "end of life (disposal)" in rep and "What would reverse the verdict" in rep


class FakeClient:
    """Just enough of olca_ipc.Client: one BAFU like process per factor key."""

    def __init__(self, factors, waste_keys=()):
        self.store, self.systems = {}, []
        self.items = o.Ref(ref_type=o.RefType.FlowProperty, id="fp-items", name="Number of items")
        self.group = o.UnitGroup(id="ug-items", units=[o.Unit(id="u-item", name="Item(s)", is_ref_unit=True)])
        for key, entry in factors["factors"].items():
            pid = entry.setdefault("id", str(uuid.uuid4()))
            ftype = o.FlowType.WASTE_FLOW if key in waste_keys else o.FlowType.PRODUCT_FLOW
            ref = o.Exchange(flow=o.Ref(ref_type=o.RefType.Flow, id=f"flow-{key}", name=key, flow_type=ftype),
                             flow_property=o.Ref(id="fp-mass"), unit=o.Ref(id="u-kg", name="kg"),
                             amount=1.0, is_quantitative_reference=True, is_input=key in waste_keys)
            self.store[pid] = o.Process(id=pid, name=f"BAFU {key}", exchanges=[ref])

    def find(self, t, name):
        return self.items if t is o.FlowProperty else None

    def get(self, t, uid=None, name=None):
        if t is o.FlowProperty:
            return o.FlowProperty(id="fp-items", unit_group=o.Ref(id="ug-items"))
        if t is o.UnitGroup:
            return self.group
        return self.store.get(uid)

    def put(self, obj):
        self.store[obj.id] = obj
        return o.Ref(id=obj.id, name=obj.name)

    def create_product_system(self, ref, config=None):
        self.systems.append(ref.id)
        return o.Ref(id=f"ps-{ref.id}")


def test_push_writes_linked_processes_with_choice_parameters(tmp_path):
    data = fake_factors()
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data)
    t = draw_truth(m, 0)
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t)
    c = FakeClient(data, waste_keys={"disposal_glass_landfill"})
    from branch.olca_bridge import push_comparison
    out = push_comparison(c, m, r, verify=False, jsonld_path=tmp_path / "branch.zip")
    assert len(out["processes"]) == 2 and len(c.systems) == 2
    inv = m.inventory(point_world(m, r))
    for ref, (label, exchanges) in zip(out["processes"], inv.items()):
        proc = c.store[ref.id]
        ref_ex = [e for e in proc.exchanges if e.is_quantitative_reference]
        assert len(ref_ex) == 1 and ref_ex[0].amount == 1.0
        linked = {e.description.split(": ")[1]: e for e in proc.exchanges if not e.is_quantitative_reference}
        assert {k for k, v in exchanges.items() if v} == set(linked)
        for key, e in linked.items():
            assert np.isclose(e.amount, exchanges[key])
            assert e.default_provider.id == data["factors"][key]["id"]
            assert e.is_input == (key != "disposal_glass_landfill")
        names = {p.name for p in proc.parameters}
        assert "distribution_km" in names
        assert all(re_ok(n) for n in names)
    assert (tmp_path / "branch.zip").stat().st_size > 0


def re_ok(name):
    import re
    return re.fullmatch(r"[A-Za-z_]\w*", name) is not None


def test_every_impact_category_is_reported_with_trade_offs():
    from branch.indicators import available, describe
    from branch.whatif import indicators
    data = fake_factors()
    for i, v in enumerate(data["factors"].values()):
        c = v["impacts"][CAT]
        v["impacts"]["Water use"] = c * (1 + (i % 5))
        v["impacts"]["Climate change (fossil)"] = c * 0.9
    assert available(data)[0] == CAT and available(data)[-1] == "Climate change (fossil)"
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data)
    t = draw_truth(m, 0)
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t)
    rows = indicators(m, r)
    assert [x["category"] for x in rows] == available(data)
    assert rows[0]["agrees"] and describe("Water use")[1] == "m3 world eq deprived"
    assert "All impact categories" in markdown_report(r, m)


class NoReferenceDataClient(FakeClient):
    """A database imported without the openLCA reference data (no 'Number of items')."""

    def find(self, t, name):
        return None

    def get_descriptors(self, t):
        return []


def test_push_adds_number_of_items_when_the_database_has_none(tmp_path):
    data = fake_factors()
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data)
    t = draw_truth(m, 0)
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t)
    c = NoReferenceDataClient(data, waste_keys={"disposal_glass_landfill"})
    from branch.olca_bridge import push_comparison
    out = push_comparison(c, m, r, verify=False, jsonld_path=tmp_path / "branch.zip")
    added = [x for x in c.store.values() if isinstance(x, (o.UnitGroup, o.FlowProperty))]
    assert {x.name for x in added} == {"Units of items", "Number of items"}
    assert len(out["processes"]) == 2 and (tmp_path / "branch.zip").exists()

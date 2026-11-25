"""Inventory, what if analysis and the openLCA connector, without openLCA:
a fake IPC client stands in for the open database."""
import uuid

import numpy as np
import pytest

from branch.agent import run_agent
from branch.builder import build_model, factor
from branch.cases import draw_truth, toy_packaging
from branch.formulas import evaluate
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
        self.linking = config
        ps = o.ProductSystem(id=f"ps-{ref.id}-{len(self.systems)}", name=ref.name,
                             ref_process=o.Ref(id=ref.id, name=ref.name))
        self.store[ps.id] = ps
        return o.Ref(id=ps.id, name=ps.name)

    def get_descriptors(self, t):
        return [o.Ref(id=x.id, name=x.name) for x in self.store.values() if isinstance(x, t)]

    def delete(self, ref):
        self.store.pop(ref.id, None)


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


def _session(pair=("pet_bottle_1l", "glass_refillable_1l"), questions=1, **kw):
    data = fake_factors()
    m = build_model(*pair, "PT", CAT, data, **kw)
    t = draw_truth(m, 0)
    r = run_agent(m, lambda n: t[n], n_samples=3000, truth=t, max_questions=questions)
    return data, m, r


def test_amounts_in_openlca_are_formulas_of_the_choices():
    """Editing a parameter in openLCA has to move the exchanges exactly as BRANCH would."""
    from branch.olca_bridge import push_comparison
    for kw in ({}, {"system_model": "cff"}):
        data, m, r = _session(**kw)
        c = FakeClient(data, waste_keys={"disposal_glass_landfill"})
        out = push_comparison(c, m, r, verify=False)
        world = point_world(m, r)
        other = dict(world)
        for ch in m.choices:                       # another value for every continuous choice, same options
            if ch.kind == "continuous" and ch.askable:
                other[ch.name] = float(ch.ppf(np.array([0.31]))[0]) if ch.is_open() else world[ch.name] * 1.1
        inv = m.inventory(other)
        seen = 0
        for ref, label in zip(out["processes"], inv):
            proc = c.store[ref.id]
            env = {p.name: other[n] for p in proc.parameters for n in other if _name(n) == p.name}
            assert len(env) == len(proc.parameters) > 0
            for e in proc.exchanges:
                if e.is_quantitative_reference:
                    continue
                key = e.description.split(": ")[1]
                assert e.amount_formula, key        # every amount of these products depends on a choice
                assert np.isclose(evaluate(e.amount_formula, env), inv[label][key], rtol=1e-9)
                seen += 1
        assert seen >= 8


def _name(n):
    import re
    return re.sub(r"\W", "_", n)


def test_formula_numbers_have_no_exponent():
    from branch.formulas import number
    assert number(1e-7) == "0.0000001" and number(2.5e-5) == "0.000025" and number(3.0) == "3"
    assert "e" not in number(1.2345678e-11).lower() and float(number(1.2345678e-11)) == 1.2345678e-11


def test_open_choices_carry_their_prior_and_answered_ones_do_not():
    from branch.olca_bridge import push_comparison, uncertainty_of
    data, m, r = _session(questions=3)
    c = FakeClient(data)
    out = push_comparison(c, m, r, verify=False)
    by_name = {ch.name: ch for ch in m.choices}
    kinds = set()
    for ref in out["processes"]:
        for p in c.store[ref.id].parameters:
            ch = next(x for n, x in by_name.items() if _name(n) == p.name)
            assert ch.kind == "continuous"                         # options are not parameters
            if not ch.is_open():
                assert p.uncertainty is None and "human" in p.description
            elif ch.prior[0] == "beta":
                assert p.uncertainty is None and "openLCA does not have" in p.description
            else:
                assert p.uncertainty is not None
                kinds.add(p.uncertainty.distribution_type)
        assert "Options fixed in this model" in c.store[ref.id].description
    assert o.UncertaintyType.UNIFORM_DISTRIBUTION in kinds
    from branch.beliefs import Choice
    u, why = uncertainty_of(Choice("x", "continuous", ("lognormal", {"median": 2.0, "sigma": 0.5}), "s", question="?"))
    assert why is None and np.isclose(u.geom_mean, 2.0 * np.exp(0.125)) and np.isclose(u.geom_sd, np.exp(0.5))
    u, _ = uncertainty_of(Choice("x", "continuous", ("triangular", {"low": 1, "mode": 2, "high": 4}), "s", question="?"))
    assert (u.minimum, u.mode, u.maximum) == (1.0, 2.0, 4.0)


def test_sending_twice_updates_and_does_not_pile_up():
    from branch.olca_bridge import push_comparison
    data, m, r = _session()
    c = FakeClient(data)
    first = push_comparison(c, m, r, verify=False)
    n_objects = len(c.store)
    second = push_comparison(c, m, r, verify=False)
    assert [p.id for p in first["processes"]] == [p.id for p in second["processes"]]
    assert first["replaced"] == 0 and second["replaced"] == 2
    assert len(c.store) == n_objects                       # same flows, processes and two product systems
    assert len([x for x in c.store.values() if isinstance(x, o.ProductSystem)]) == 2
    data2, m2, r2 = _session(pair=("pet_bottle_1l", "aluminium_can_330ml"))
    c.store.update(FakeClient(data2).store)
    third = push_comparison(c, m2, r2, verify=False)       # another comparison keeps the first one
    assert not set(p.id for p in third["processes"]) & set(p.id for p in first["processes"])
    assert len([x for x in c.store.values() if isinstance(x, o.ProductSystem)]) == 4


def test_linking_follows_the_kind_of_the_providers():
    from branch.olca_bridge import push_comparison
    data, m, r = _session()
    c = FakeClient(data)
    push_comparison(c, m, r, verify=False)
    assert c.linking.provider_linking == o.ProviderLinking.PREFER_DEFAULTS       # unit processes
    for p in c.store.values():
        if isinstance(p, o.Process) and p.name.startswith("BAFU "):
            p.process_type = o.ProcessType.LCI_RESULT
    push_comparison(c, m, r, verify=False)
    assert c.linking.provider_linking == o.ProviderLinking.ONLY_DEFAULTS         # aggregated, as in ELCD


def test_nothing_is_sent_before_the_backup_is_confirmed(monkeypatch):
    from branch import connector
    called = []
    monkeypatch.setattr(connector, "client", lambda port=8080: called.append(port))
    msg = connector.send(None, None)
    assert "backup" in msg.lower() and not called


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
        return [] if t is o.FlowProperty else super().get_descriptors(t)


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


def test_a_formula_is_read_without_running_code():
    assert evaluate("(a * 2.5) / b - -1", {"a": 2.0, "b": 5.0}) == pytest.approx(2.0)
    for text in ("__import__('os').system('true')", "a ** 2", "a.real", "[a]"):
        with pytest.raises(ValueError):
            evaluate(text, {"a": 1.0})

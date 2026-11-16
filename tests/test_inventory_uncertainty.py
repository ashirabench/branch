"""Uncertainty of the database: every unit factor may vary in the Monte Carlo draws, and nobody is asked."""
import copy

import numpy as np
import pytest

from branch.agent import run_agent
from branch.builder import build_model as _build_model
from branch.builder import factor, required_factor_keys
from branch.cases import draw_truth, draw_truth_tails
from branch.montecarlo import State

CAT = "Climate change"


def build_model(*args, **kw):
    """The builder with the uncertainty of the datasets switched on (it is off by default)."""
    kw.setdefault("inventory_uncertainty", True)
    return _build_model(*args, **kw)

BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]


def factors(gsd=None, only=None):
    """Synthetic factors; gsd adds the same uncertainty to every factor (or to the keys in only)."""
    keys = sorted(set(required_factor_keys(BENCH, "PT")) | set(required_factor_keys(BENCH, "DE"))
                  | set(required_factor_keys(BENCH, "BR-AM")))
    rng = np.random.default_rng(0)
    data = {"method": "synthetic", "path": "synthetic.json", "citation": "synthetic",
            "factors": {k: {"impacts": {CAT: float(rng.uniform(0.01, 5)), "Acidification": 1.0}} for k in keys}}
    if gsd:
        for k in (only or keys):
            data["factors"][k]["uncertainty"] = {CAT: {"gsd": gsd, "n": 300}}
    return data


def world(model, **given):
    w = {c.name: (1.0 if not c.askable else c.answers()[0][len(c.answers()[0]) // 2]) for c in model.choices}
    w.update(given)
    return w


def test_it_is_off_unless_asked_for():
    m = _build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, factors(1.2))
    assert all(c.askable for c in m.choices)


def test_without_uncertainty_in_the_file_nothing_changes():
    plain = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, factors())
    off = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, factors(1.2), inventory_uncertainty=False)
    assert all(c.askable for c in plain.choices) and [c.name for c in plain.choices] == [c.name for c in off.choices]
    S = plain.sample(200, seed=1)
    assert np.array_equal(sum(plain.term_value(i, S) for i in range(len(plain.terms))),
                          sum(off.term_value(i, S) for i in range(len(off.terms))))
    other = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", "Acidification", factors(1.2))
    assert all(c.askable for c in other.choices)          # the uncertainty belongs to one category


def test_each_dataset_gets_one_draw_shared_by_both_products():
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, factors(1.2))
    noise = [c for c in m.choices if not c.askable]
    names = [c.name for c in noise]
    assert len(names) == len(set(names)) and "factor.lorry_16_32t" in names
    assert all(c.source.startswith("SOURCE: ") and c.prior == ("lognormal", {"median": 1.0, "sigma": float(np.log(1.2))})
               for c in noise)
    lorry = [t.name for t in m.terms if "factor.lorry_16_32t" in t.deps]
    assert lorry == ["pet.transport", "glass.transport"]   # one draw moves the transport of both
    used = set(required_factor_keys(["pet_bottle_1l", "glass_refillable_1l"], "PT"))
    assert {n[len("factor."):] for n in names} == used


@pytest.mark.parametrize("pair,region,system", [
    (("pet_bottle_1l", "glass_refillable_1l"), "PT", "cut-off"),
    (("aluminium_can_330ml", "beverage_carton_1l"), "BR-AM", "cut-off"),
    (("pet_bottle_1l", "glass_refillable_1l"), "DE", "cff"),
    (("aluminium_can_330ml", "beverage_carton_1l"), "PT", "cff"),
])
def test_the_model_is_the_inventory_times_the_factor_times_its_draw(pair, region, system):
    data = factors(1.3)
    m = build_model(*pair, region, CAT, data, system_model=system)
    still = build_model(*pair, region, CAT, data, system_model=system, inventory_uncertainty=False)
    S = m.sample(25, seed=4)
    for r in range(S.shape[0]):
        w = {c.name: float(S[r, j]) for j, c in enumerate(m.choices)}
        inv = m.inventory(w)
        tot = {k: sum(x * factor(data, key, CAT) * w[f"factor.{key}"] for key, x in v.items()) for k, v in inv.items()}
        assert np.isclose(tot[m.label_a] - tot[m.label_b], m.delta_at(w), rtol=1e-9, atol=1e-13)
        calm = dict(w, **{c.name: 1.0 for c in m.choices if not c.askable})
        assert np.isclose(m.delta_at(calm), still.delta_at({k: v for k, v in calm.items() if k in still.idx}),
                          rtol=1e-12, atol=1e-15)


def test_only_the_factors_with_a_stated_uncertainty_vary():
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT,
                    factors(1.5, only=["pet_granulate_bottle_grade", "electricity_mv_PT"]))
    assert sorted(c.name for c in m.choices if not c.askable) == ["factor.electricity_mv_PT",
                                                                    "factor.pet_granulate_bottle_grade"]
    data = factors(1.0)                                    # a geometric standard deviation of 1 is no uncertainty
    assert all(c.askable for c in build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data).choices)


def test_the_agent_never_asks_about_the_database_and_counts_it_in_the_risk():
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, factors(1.3))
    noise = {c.name for c in m.choices if not c.askable}
    st = State(m, m.sample(2000, 0))
    assert not noise & set(st.open) and len(st.open) == len(m.choices) - len(noise)
    truth = draw_truth(m, 3)
    r = run_agent(m, lambda n: truth[n], n_samples=3000, tau=0.0, truth=truth)     # tau 0: it asks everything it can
    assert not noise & set(r["asked"]) and r["questions"] == len(m.choices) - len(noise)
    assert all(r["decided_by"][n].startswith("nobody: uncertainty of the database") for n in noise)
    for n in list(st.open):                                # every question answered:
        st.fix(n, truth[n])
    assert float(np.std(np.asarray(st.delta))) > 0         # the database still leaves a spread in the result
    calm = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, factors())
    st2 = State(calm, calm.sample(2000, 0))
    for n in list(st2.open):
        st2.fix(n, truth[n])
    assert float(np.ptp(np.asarray(st2.delta))) < 1e-12    # without it, nothing is left


def test_experts_from_the_tails_do_not_put_the_database_in_the_tails():
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, factors(1.3))
    draws = np.array([[draw_truth_tails(m, s)[c.name] for c in m.choices if not c.askable] for s in range(200)])
    q = np.quantile(draws, [0.25, 0.5, 0.75])
    assert abs(q[1] - 1.0) < 0.05 and q[0] > 1.3 ** -1 and q[2] < 1.3      # centred on 1, not on the tails


def test_the_report_names_the_uncertainty_of_the_database_apart_from_the_choices():
    from branch.report import markdown_report
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, factors(1.3))
    truth = draw_truth(m, 1)
    r = run_agent(m, lambda n: truth[n], n_samples=2000, truth=truth)
    text = markdown_report(r, m, analysis=False)
    assert "## Uncertainty of the database (in every result, never asked)" in text
    assert "| factor." not in text                         # not in the table of choices


# ------------------------------------------------ the simulation, with a stand in for openLCA

class _Fake:
    """The calls of olca-ipc that the simulation uses, in the order the library documents them."""
    class _Result:
        def __init__(self, draws):
            self.draws, self.i, self.error, self.disposed = draws, -1, None, False

        def wait_until_ready(self):
            return None

        def simulate_next(self):
            self.i += 1
            return type("S", (), {"error": None})()

        def get_total_impacts(self):
            import olca_schema as o
            return [o.ImpactValue(impact_category=o.Ref(name=c), amount=v[self.i]) for c, v in self.draws.items()]

        def dispose(self):
            self.disposed = True

    def __init__(self, kind, draws):
        import olca_schema as o
        self.o, self.kind, self.draws, self.linked, self.deleted = o, kind, draws, None, False

    def get(self, _type, _id):
        o = self.o
        return o.Process(id="p", name="x", process_type=self.kind, exchanges=[
            o.Exchange(is_quantitative_reference=True, unit=o.Ref(name="kg"), flow_property=o.Ref(name="Mass"),
                       flow=o.Ref(name="x"))])

    def create_product_system(self, ref, config):
        self.linked = config.provider_linking
        return self.o.Ref(id="s")

    def simulate(self, setup):
        self.result = self._Result(self.draws)
        return self.result

    def delete(self, ref):
        self.deleted = True


def test_simulation_collects_every_run_and_cleans_up():
    import olca_schema as o

    from branch.olca_extract import simulate_impacts, spread
    rng = np.random.default_rng(1)
    draws = {"Climate change": list(2.0 * rng.lognormal(0, np.log(1.2), 400)), "Water use": [1.0, -1.0] * 200}
    fake = _Fake(o.ProcessType.UNIT_PROCESS, draws)
    seen = []
    runs = simulate_impacts(fake, o.Ref(id="p"), o.Ref(id="m"), 400, tick=lambda i, n: seen.append(i))
    assert runs == draws and seen[-1] == 400 and fake.result.disposed and fake.deleted
    assert fake.linked == o.ProviderLinking.PREFER_DEFAULTS            # a unit process is linked to its providers
    s = spread(runs["Climate change"], 2.0)
    assert abs(s["gsd"] - 1.2) < 0.03 and abs(s["median_ratio"] - 1.0) < 0.05 and s["n"] == 400
    assert spread(runs["Water use"], 1.0)["gsd"] is None               # half the runs have the other sign
    assert spread([1.0], 1.0)["gsd"] is None and spread([1.0, 2.0], 0.0)["gsd"] is None


def test_an_aggregated_process_is_not_linked_to_unrelated_datasets():
    import olca_schema as o

    from branch.olca_extract import linking, simulate_impacts
    fake = _Fake(o.ProcessType.LCI_RESULT, {"Climate change": [1.0, 1.1]})
    simulate_impacts(fake, o.Ref(id="p"), o.Ref(id="m"), 2)
    assert fake.linked == o.ProviderLinking.ONLY_DEFAULTS
    assert linking(o.Process(process_type=o.ProcessType.UNIT_PROCESS)).provider_linking == o.ProviderLinking.PREFER_DEFAULTS


def test_correlated_run_moves_every_factor_with_one_draw():
    """The bound opposite to independence: one draw nobody is asked, each factor scaled by its own spread."""
    data = factors(1.2)
    data["factors"]["electricity_mv_PT"]["uncertainty"][CAT]["gsd"] = 1.5
    m = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, inventory_uncertainty="correlated")
    hidden = [c for c in m.choices if not c.askable]
    assert [c.name for c in hidden] == ["factor.all"] and hidden[0].prior[0] == "normal"
    plain = _build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data)
    w = {c.name: c.answers()[0][len(c.answers()[0]) // 2] for c in plain.choices}
    assert np.isclose(m.delta_at(dict(w, **{"factor.all": 0.0})), plain.delta_at(w), rtol=1e-12)   # z = 0: central values
    scaled = copy.deepcopy(data)                    # z = 1: every factor times its own gsd
    for k, f in scaled["factors"].items():
        f["impacts"][CAT] *= f["uncertainty"][CAT]["gsd"]
    up = _build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, scaled)
    assert np.isclose(m.delta_at(dict(w, **{"factor.all": 1.0})), up.delta_at(w), rtol=1e-9)
    S = m.sample(500, seed=3)                       # the engine agrees with the scalar path
    total = np.asarray(sum(m.term_value(i, S) for i in range(len(m.terms))))
    row = {c.name: float(S[7, j]) for j, c in enumerate(m.choices)}
    assert np.isclose(total[7], m.delta_at(row), rtol=1e-9)
    r = run_agent(m, lambda n: draw_truth(m, 1)[n], strategy="decision_flip", batch_size=3, n_samples=2000,
                  tau=0.025, seed=1, truth=draw_truth(m, 1))
    assert "factor.all" not in r["asked"]
    with pytest.raises(ValueError, match="inventory_uncertainty"):
        _build_model("pet_bottle_1l", "glass_refillable_1l", "PT", CAT, data, inventory_uncertainty="half")

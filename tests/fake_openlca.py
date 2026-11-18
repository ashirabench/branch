"""An openLCA made for the tests: enough of olca_ipc.Client to send a comparison and have it calculated.

It holds one process per key of a factor file. A process that BRANCH sends is stored as it arrives.
calculate() adds, over the exchanges of the process behind a product system, amount x unit factor of
the provider, with the factors of the file. So "openLCA" here recomputes from what was actually sent,
exchange by exchange, and a wrong amount, a wrong provider or a lost exchange shows as a difference.
It does not evaluate formulas: it reads the amounts, which BRANCH sends beside the formulas.
"""
from types import SimpleNamespace

import olca_schema as o

METHOD = o.Ref(ref_type=o.RefType.ImpactMethod, id="method-1", name="synthetic method")


class Result:
    def __init__(self, impacts):
        self.impacts = impacts

    def wait_until_ready(self):
        pass

    def get_total_impacts(self):
        return [SimpleNamespace(impact_category=SimpleNamespace(name=k), amount=v) for k, v in self.impacts.items()]

    def dispose(self):
        pass


class FakeOpenLCA:
    def __init__(self, factors, waste_keys=()):
        self.factors = factors["factors"]
        self.store, self.key_of, self.calculations = {}, {}, 0
        self.group = o.UnitGroup(id="ug-items", name="Units of items",
                                 units=[o.Unit(id="u-item", name="Item(s)", is_ref_unit=True)])
        for i, (key, entry) in enumerate(sorted(self.factors.items())):
            pid = entry.setdefault("id", f"db-{i:04d}")
            waste = key in waste_keys
            ref = o.Exchange(flow=o.Ref(ref_type=o.RefType.Flow, id=f"flow-{key}", name=key,
                                        flow_type=o.FlowType.WASTE_FLOW if waste else o.FlowType.PRODUCT_FLOW),
                             flow_property=o.Ref(id="fp-mass"), unit=o.Ref(id="u-kg", name="kg"),
                             amount=1.0, is_quantitative_reference=True, is_input=waste)
            self.store[pid] = o.Process(id=pid, name=f"database | {key}", exchanges=[ref])
            self.key_of[pid] = key
        self.database = set(self.store)

    # ---- what BRANCH wrote and has not removed
    def left_behind(self):
        return sorted(k for k in self.store if k not in self.database)

    # ---- the calls of olca_ipc.Client that BRANCH makes
    def find(self, kind, name):
        if kind is o.FlowProperty:
            return o.Ref(ref_type=o.RefType.FlowProperty, id="fp-items", name="Number of items")
        return METHOD if kind is o.ImpactMethod else None

    def get(self, kind, uid=None, name=None):
        if kind is o.FlowProperty:
            return o.FlowProperty(id="fp-items", unit_group=o.Ref(id="ug-items"))
        if kind is o.UnitGroup:
            return self.group
        if kind is o.ImpactMethod:
            return METHOD
        return self.store.get(uid)

    def get_descriptors(self, kind):
        if kind is o.UnitGroup:
            return [o.Ref(id=self.group.id, name=self.group.name)]
        return [o.Ref(id=x.id, name=x.name) for x in self.store.values() if isinstance(x, kind)]

    def put(self, obj):
        self.store[obj.id] = obj
        return o.Ref(id=obj.id, name=obj.name)

    def delete(self, ref):
        self.store.pop(ref.id, None)

    def create_product_system(self, ref, config=None):
        system = o.ProductSystem(id=f"system-{ref.id}", name=ref.name, ref_process=o.Ref(id=ref.id, name=ref.name))
        self.store[system.id] = system
        return o.Ref(id=system.id, name=system.name)

    def calculate(self, setup):
        self.calculations += 1
        process = self.store[self.store[setup.target.id].ref_process.id]
        totals = {}
        for e in process.exchanges:
            if e.is_quantitative_reference:
                continue
            for category, value in self.factors[self.key_of[e.default_provider.id]]["impacts"].items():
                totals[category] = totals.get(category, 0.0) + e.amount * value
        return Result(totals)

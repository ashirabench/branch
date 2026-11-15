"""Hand written PET vs refillable glass model, as it was before builder.py.

Kept only as the reference for the regression test: the builder, fed the
two benchmark product files, must give the same delta for every world.
"""
import numpy as np

from branch.beliefs import Choice
from branch.lca_model import Model, Term
from branch.builder import factor as _factor

CITATION = "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:20XY"
DEFAULT_CATEGORY = "Climate change"


def _f(data, key, category):
    return _factor(data, key, category)


def legacy_pet_vs_refillable_glass(factors, country="PT", category=DEFAULT_CATEGORY, xp=np):
    """1 L of beverage delivered: single use PET bottle (A) vs refillable glass bottle (B).

    Cut-off approach for recycling (ILCD Situation A, attributional): recycled
    material leaving the system carries no credit; recycled input carries
    only its own production burden.
    """
    data = factors
    f = lambda k: _f(data, k, category)  # noqa: E731
    elec = f(f"electricity_mv_{country}")
    T = lambda vals: xp.asarray(vals, dtype=xp.float64)  # noqa: E731
    idx = lambda v: xp.asarray(v).astype(int)  # noqa: E731

    pet_virgin = T([f("pet_granulate_bottle_grade"), f("pet_granulate_amorphous")])
    blow = f("stretch_blow_moulding")
    glass = T([f("glass_packaging_white"), f("glass_packaging_green"), f("glass_packaging_brown")])
    lorry = f("lorry_16_32t")                      # per t*km
    heat = f("heat_natural_gas_furnace")           # per MJ
    water = f("tap_water_RER")                     # per kg
    pet_inc, pet_land = f("disposal_polyethylene_terephthalate_incineration"), f("disposal_plastics_mixture_landfill")
    glass_eol = T([0.0, f("disposal_glass_landfill"), f("disposal_glass_incineration")])

    choices = [
        # ---- PET, single use -------------------------------------------------
        Choice("pet_mass_g", "continuous", ("triangular", {"low": 25, "mode": 32, "high": 42}),
               "ASSUMPTION: typical 1 L PET bottle with cap and label",
               question="How many grams does the empty 1 L PET bottle weigh (with cap and label)?"),
        Choice("pet_dataset", "categorical", {"bottle grade": 0.8, "amorphous": 0.2},
               "SOURCE: BAFU:2026 PET datasets; ASSUMPTION on the weights",
               question="Which PET resin is used: bottle grade or amorphous?"),
        Choice("pet_recycled_share", "continuous", ("uniform", {"low": 0.0, "high": 0.5}),
               "ASSUMPTION: 0 to 50% recycled content (PPWR targets 30% by 2030)",
               question="What share of the PET bottle is recycled material (0 to 1)?"),
        Choice("rpet_burden_ratio", "continuous", ("uniform", {"low": 0.2, "high": 0.5}),
               "ASSUMPTION: no recycled PET dataset in BAFU:2026; burden of rPET as a share of virgin PET",
               question="Impact of recycled PET relative to virgin PET (0 to 1)?"),
        Choice("pet_recycling_rate", "continuous", ("beta", {"a": 4, "b": 6}),
               "ASSUMPTION: about 40% collected for recycling; replace with Eurostat env_waspac",
               question="What share of used PET bottles is collected for recycling (0 to 1)?"),
        Choice("pet_incineration_share", "continuous", ("uniform", {"low": 0.2, "high": 0.8}),
               "ASSUMPTION: share of non recycled PET incinerated, rest landfilled",
               question="Of the PET not recycled, what share is incinerated (0 to 1)?"),
        # ---- refillable glass ------------------------------------------------
        Choice("glass_mass_g", "continuous", ("triangular", {"low": 400, "mode": 550, "high": 750}),
               "ASSUMPTION: typical 1 L refillable glass bottle",
               question="How many grams does the empty 1 L glass bottle weigh?"),
        Choice("glass_colour", "categorical", {"white": 1 / 3, "green": 1 / 3, "brown": 1 / 3},
               "SOURCE: BAFU:2026 packaging glass datasets; uniform weights",
               question="What colour is the glass bottle?"),
        Choice("glass_trips", "continuous", ("triangular", {"low": 5, "mode": 15, "high": 40}),
               "ASSUMPTION: refill cycles per bottle; replace with sector data",
               question="How many times is each glass bottle filled over its life?"),
        Choice("wash_kwh", "continuous", ("uniform", {"low": 0.005, "high": 0.03}),
               "ASSUMPTION: electricity for washing and refilling per bottle",
               question="Electricity used to wash and refill one bottle (kWh)?"),
        Choice("wash_heat_mj", "continuous", ("uniform", {"low": 0.05, "high": 0.5}),
               "ASSUMPTION: natural gas heat for washing per bottle",
               question="Heat used to wash one bottle (MJ of natural gas)?"),
        Choice("wash_water_kg", "continuous", ("uniform", {"low": 0.2, "high": 1.5}),
               "ASSUMPTION: water for washing per bottle",
               question="Water used to wash one bottle (litres)?"),
        Choice("glass_eol", "categorical", {"recycling (cut-off)": 0.6, "landfill": 0.3, "incineration": 0.1},
               "ASSUMPTION: end of life of a glass bottle after its last trip",
               question="What happens to a glass bottle at the end of its life?"),
        # ---- shared ----------------------------------------------------------
        Choice("distribution_km", "continuous", ("uniform", {"low": 50, "high": 400}),
               "ASSUMPTION: one way distance bottler to retailer, same for both",
               question="One way distance from the bottler to the shops (km)?"),
    ]

    def pet_material(xp_, v):
        kg = v["pet_mass_g"] / 1000
        r = v["pet_recycled_share"]
        virgin = pet_virgin[idx(v["pet_dataset"])]
        return kg * ((1 - r) * virgin + r * v["rpet_burden_ratio"] * virgin + blow)

    def pet_end_of_life(xp_, v):
        kg = v["pet_mass_g"] / 1000
        not_rec = 1 - v["pet_recycling_rate"]
        s = v["pet_incineration_share"]
        return kg * not_rec * (s * pet_inc + (1 - s) * pet_land)

    terms = [
        Term("pet_material", ["pet_mass_g", "pet_dataset", "pet_recycled_share", "rpet_burden_ratio"],
             pet_material),
        Term("pet_end_of_life", ["pet_mass_g", "pet_recycling_rate", "pet_incineration_share"], pet_end_of_life),
        Term("pet_transport", ["pet_mass_g", "distribution_km"],
             lambda xp_, v: v["pet_mass_g"] / 1e6 * v["distribution_km"] * lorry),
        Term("glass_material", ["glass_mass_g", "glass_colour", "glass_trips"],
             lambda xp_, v: v["glass_mass_g"] / 1000 * glass[idx(v["glass_colour"])] / v["glass_trips"],
             sign=-1),
        Term("glass_transport", ["glass_mass_g", "distribution_km"],
             lambda xp_, v: v["glass_mass_g"] / 1e6 * 2 * v["distribution_km"] * lorry, sign=-1),
        Term("glass_washing", ["wash_kwh", "wash_heat_mj", "wash_water_kg"],
             lambda xp_, v: v["wash_kwh"] * elec + v["wash_heat_mj"] * heat + v["wash_water_kg"] * water,
             sign=-1),
        Term("glass_end_of_life", ["glass_mass_g", "glass_eol", "glass_trips"],
             lambda xp_, v: v["glass_mass_g"] / 1000 * glass_eol[idx(v["glass_eol"])] / v["glass_trips"],
             sign=-1),
    ]
    model = Model(choices, terms, xp, label_a="PET single use", label_b="Refillable glass")
    return model

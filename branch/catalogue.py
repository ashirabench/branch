"""Codified rules: what BRANCH assumes when the bill of materials is silent (Step 3).

The proposal (Goal 2) asks the agent to complete every modelling choice that
the bill of materials and the location do not fix "from data and codified
rules". This module holds those rules. The builder (builder.py) reads them
and turns every unstated item into an explicit Choice; nothing here is a
hidden default.

Every prior carries a source string that starts with
    SOURCE:      it comes from a cited dataset or provision, or
    ASSUMPTION:  it is a placeholder I chose, to be replaced before results
                 are reported (real_cases.assumptions lists them).

Priors may depend on the location: write {"default": prior, "PT": prior, ...}.
The builder picks the country entry when it exists, else "default". This is
where Eurostat, ENTSO-E and Brazilian National Energy Balance statistics go
(data/priors/, Step 4).

Factor keys are the names used by experiments/extract_factors.py (PROCESSES).
Every factor is an impact per unit of the dataset's reference flow: per kg
for materials, conversion and disposal; per kWh, MJ, kg of water, t*km.

System model: attributional, ILCD Situation A, cut-off for recycling. Recycled
material leaving the system carries no credit and no burden; recycled input
carries only its own production burden.
"""

# --------------------------------------------------------------------------
# Materials
#
# datasets    candidate datasets for the virgin material, {option: (factor key,
#             prior weight)}. More than one option -> a categorical Choice.
# dataset_question  question asked when the candidates differ ({c} = component)
# conversion  factor key of the default conversion process per kg (blow
#             moulding, rolling, ...); a component may override it, None = none
# recycled    how recycled content enters, or None when the datasets already
#             include it:
#               {"model": "burden_ratio", "content": prior, "ratio": prior}
#                   recycled kg costs ratio x the virgin dataset
#               {"model": "dataset", "key": factor key, "content": prior}
#                   recycled kg costs its own dataset
# end_of_life one of
#               {"model": "split", "recycling_rate": prior,
#                "incineration_share": prior, "incineration": key, "landfill": key}
#                   a share is recycled (cut-off), the rest is split between
#                   incineration and landfill
#               {"model": "categorical", "options": {label: (key or None, weight)}}
#                   one fate for the whole item; None = recycling (cut-off)
# --------------------------------------------------------------------------

def _plastics_eol(incineration, landfill):
    """Split end of life of a plastic, with the disposal datasets of its polymer."""
    return {
        "model": "split",
        "recycling_rate": ("beta", {"a": 4, "b": 6},
                           "ASSUMPTION: about 40% collected for recycling; replace with Eurostat env_waspac"),
        "incineration_share": ("uniform", {"low": 0.2, "high": 0.8},
                               "ASSUMPTION: share of non recycled plastic incinerated, rest landfilled"),
        "incineration": incineration,
        "landfill": landfill,
    }


# PET: its own incineration dataset. Its landfill dataset in BAFU:2026 is marked obsolete,
# so the landfill uses the plastics mixture, a PROXY. Polyethylene: its own datasets for both.
_PET_EOL = _plastics_eol("disposal_polyethylene_terephthalate_incineration", "disposal_plastics_mixture_landfill")
_PE_EOL = _plastics_eol("disposal_polyethylene_incineration", "disposal_polyethylene_landfill")

MATERIALS = {
    "pet": {
        "label": "PET",
        "datasets": {"bottle grade": ("pet_granulate_bottle_grade", 0.8),
                     "amorphous": ("pet_granulate_amorphous", 0.2)},
        "datasets_source": "SOURCE: BAFU:2026 PET datasets; ASSUMPTION on the weights",
        "dataset_question": "Which resin is the {c} made of: bottle grade or amorphous PET?",
        "conversion": "stretch_blow_moulding",
        "recycled": {
            "model": "burden_ratio",
            "content": ("uniform", {"low": 0.0, "high": 0.5},
                        "ASSUMPTION: 0 to 50% recycled content (PPWR targets 30% by 2030)"),
            "ratio": ("uniform", {"low": 0.2, "high": 0.5},
                      "ASSUMPTION: no recycled PET dataset in BAFU:2026; burden of rPET as a share of virgin PET"),
        },
        "end_of_life": _PET_EOL,
    },
    "hdpe": {
        "label": "HDPE",
        "datasets": {"HDPE granulate": ("hdpe_granulate", 1.0)},
        "conversion": "injection_moulding",
        "recycled": None,
        "end_of_life": _PE_EOL,
    },
    "ldpe": {
        "label": "LDPE",
        "datasets": {"LDPE granulate": ("ldpe_granulate", 1.0)},
        "conversion": "film_extrusion",
        "recycled": None,
        "end_of_life": _PE_EOL,
    },
    "glass": {
        "label": "glass",
        "datasets": {"white": ("glass_packaging_white", 1 / 3),
                     "green": ("glass_packaging_green", 1 / 3),
                     "brown": ("glass_packaging_brown", 1 / 3)},
        "datasets_source": "SOURCE: BAFU:2026 packaging glass datasets; uniform weights",
        "dataset_question": "What colour is the {c}?",
        "conversion": None,          # the BAFU packaging glass datasets are formed containers
        "recycled": None,            # cullet is inside the BAFU packaging glass datasets
        "end_of_life": {
            "model": "categorical",
            "options": {"recycling (cut-off)": (None, 0.6),
                        "landfill": ("disposal_glass_landfill", 0.3),
                        "incineration": ("disposal_glass_incineration", 0.1)},
            "source": "ASSUMPTION: end of life of a glass bottle after its last trip",
            "question": "What happens to the {c} at the end of its life?",
        },
    },
    "aluminium": {
        "label": "aluminium",
        "datasets": {"wrought alloy mix": ("aluminium_wrought_mix", 1.0)},
        "conversion": "sheet_rolling_aluminium",
        "recycled": {
            "model": "dataset",
            "key": "aluminium_secondary_old_scrap",
            "content": ("uniform", {"low": 0.2, "high": 0.7},
                        "ASSUMPTION: recycled content of can sheet; one can maker declares 70% in Europe for 2021 "
                        "(Ardagh Metal Packaging 2022), inside this range"),
        },
        "end_of_life": {
            "model": "split",
            "recycling_rate": ("beta", {"a": 6, "b": 4},
                               "ASSUMPTION: about 60% of cans collected for recycling; replace with Eurostat env_waspac"),
            "incineration_share": ("uniform", {"low": 0.2, "high": 0.8},
                                   "ASSUMPTION: share of non recycled aluminium incinerated, rest landfilled"),
            "incineration": "disposal_aluminium_incineration",
            "landfill": "disposal_aluminium_landfill",
        },
    },
    "liquid_packaging_board": {
        "label": "liquid packaging board",
        "datasets": {"liquid packaging board": ("liquid_packaging_board", 1.0)},
        "conversion": None,
        "recycled": None,
        "end_of_life": {
            "model": "split",
            "recycling_rate": ("beta", {"a": 3, "b": 7},
                               "ASSUMPTION: about 30% of beverage cartons recycled; replace with Eurostat env_waspac"),
            "incineration_share": ("uniform", {"low": 0.2, "high": 0.8},
                                   "ASSUMPTION: share of non recycled board incinerated, rest landfilled"),
            "incineration": "disposal_board_incineration",
            "landfill": "disposal_board_landfill",
        },
    },
}

# --------------------------------------------------------------------------
# Packaging system rules (refillable containers)
# --------------------------------------------------------------------------

REFILLABLE = {
    "trips": ("triangular", {"low": 5, "mode": 15, "high": 40},
              "ASSUMPTION: refill cycles per container; replace with sector data",
              "How many times is each {p} filled over its life?"),
    "wash_kwh": ("uniform", {"low": 0.005, "high": 0.03},
                 "ASSUMPTION: electricity for washing and refilling per container",
                 "Electricity used to wash and refill one {p} (kWh)?"),
    "wash_heat_mj": ("uniform", {"low": 0.05, "high": 0.5},
                     "ASSUMPTION: natural gas heat for washing per container; the upper bound was widened "
                     "from 0.4 on 13 Nov 2026 to include the 0.459 MJ measured in an Italian bottling plant "
                     "(Tua, Grosso and Rigamonti 2020)",
                     "Heat used to wash one {p} (MJ of natural gas)?"),
    "wash_water_kg": ("uniform", {"low": 0.2, "high": 1.5},
                      "ASSUMPTION: water for washing per container; 0.67 l measured in an Italian bottling "
                      "plant (Tua, Grosso and Rigamonti 2020) lies inside this range",
                      "Water used to wash one {p} (litres)?"),
}
# Refillables travel back empty to the bottler: two legs per trip.
REFILLABLE_TRANSPORT_LEGS = 2

# --------------------------------------------------------------------------
# Transport modes (regions/*.json name legs by mode) and utilities
# --------------------------------------------------------------------------

TRANSPORT = {
    "lorry": "lorry_16_32t",
    "barge": "transport_barge",
    "rail": "transport_freight_rail",
}
# Plain words shown to people (the data keeps "lorry", the BAFU dataset name).
MODE_WORDS = {"lorry": "truck", "barge": "boat", "rail": "train"}
TRANSPORT_QUESTIONS = {
    "distribution": "How far does the {mode} travel from the bottling plant to the shops, one way (km)?",
    "supply": "How far does the {mode} travel from the packaging maker to the bottling plant (km)?",
}

UTILITIES = {
    "heat": "heat_natural_gas_furnace",
    "water": "tap_water_RER",
}


# --------------------------------------------------------------------------
# More materials without code: data/materials/*.json
# --------------------------------------------------------------------------

def load_materials(root=None):
    """Built in MATERIALS plus every data/materials/<id>.json (same fields as
    above; priors as [dist, params, source], options as [key, weight]). A file
    with the id of a built in material replaces it."""
    import json
    import os
    root = root or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "data", "materials")
    out = dict(MATERIALS)
    if os.path.isdir(root):
        for f in sorted(os.listdir(root)):
            if f.endswith(".json"):
                with open(os.path.join(root, f)) as fh:
                    m = json.load(fh)
                mid = m.pop("id", f[:-5])
                missing = {"label", "datasets", "end_of_life"} - set(m)
                if missing:
                    raise ValueError(f"data/materials/{f}: missing {sorted(missing)}")
                m.setdefault("conversion", None)
                m.setdefault("recycled", None)
                out[mid] = m
    return out


def material_keys(m):
    """Every factor key a material needs: datasets, conversion, recycled dataset, end of life."""
    keys = {k for k, _ in m["datasets"].values()}
    if m.get("conversion"):
        keys.add(m["conversion"])
    rec = m.get("recycled")
    if rec and rec["model"] == "dataset":
        keys.add(rec["key"])
    eol = m["end_of_life"]
    if eol["model"] == "split":
        keys |= {eol["incineration"], eol["landfill"]}
    else:
        keys |= {k for k, _ in eol["options"].values() if k}
    return keys


def split_by_factors(factors, root=None):
    """(ready, waiting): materials whose factors are all in the file, and those that need a new extraction."""
    have = set((factors or {}).get("factors") or {})
    ready, waiting = {}, {}
    for mid, m in load_materials(root).items():
        (ready if material_keys(m) <= have else waiting)[mid] = m
    return ready, waiting


# --------------------------------------------------------------------------
# Circular Footprint Formula parameters (EU Product Environmental Footprint)
# --------------------------------------------------------------------------

def load_cff(root=None):
    """CFF parameters per material from data/cff/<material>.json:

        {"A": 0.2, "Qsin_Qp": 1.0, "Qsout_Qp": 1.0,
         "recycling_eol_key": "<factor key>"   optional: recycling process at end of life
         "source": "SOURCE: PEF Annex C, version ..., row ..."}

    Only values copied from the official Annex C are allowed here; materials
    without a file cannot be assessed with the CFF (builder raises).
    """
    import json
    import os
    root = root or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cff")
    out = {}
    if os.path.isdir(root):
        for f in sorted(os.listdir(root)):
            if f.endswith(".json"):
                with open(os.path.join(root, f)) as fh:
                    p = json.load(fh)
                missing = {"A", "Qsin_Qp", "Qsout_Qp", "source"} - set(p)
                if missing:
                    raise ValueError(f"data/cff/{f}: missing {sorted(missing)}")
                out[f[:-5]] = p
    return out

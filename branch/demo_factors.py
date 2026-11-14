"""ILLUSTRATIVE unit impact factors for demos and tests. NOT BAFU DATA.

Rough orders of magnitude for climate change (kg CO2 eq per unit) so the web
app and the reports can be shown before the real factors are extracted from
openLCA. Every screen and report built on them says so. Never use them for a
result.
"""

CATEGORY = "Climate change"
_VALUES = {
    "pet_granulate_bottle_grade": 2.2, "pet_granulate_amorphous": 2.0, "stretch_blow_moulding": 0.8,
    "hdpe_granulate": 1.9, "ldpe_granulate": 2.0, "injection_moulding": 1.3, "film_extrusion": 0.6,
    "glass_packaging_white": 0.95, "glass_packaging_green": 0.85, "glass_packaging_brown": 0.9,
    "aluminium_wrought_mix": 9.0, "aluminium_secondary_old_scrap": 0.6, "sheet_rolling_aluminium": 0.5,
    "liquid_packaging_board": 1.0, "corrugated_board_box": 1.0,
    "electricity_mv_PT": 0.30, "electricity_mv_DE": 0.50, "electricity_mv_BR": 0.15,
    "electricity_oil_power_plant": 0.85,
    "lorry_16_32t": 0.15, "transport_barge": 0.03, "transport_freight_rail": 0.03,
    "heat_natural_gas_furnace": 0.07, "tap_water_RER": 0.0003,
    "disposal_pet_incineration": 2.3, "disposal_pet_landfill": 0.1,
    "disposal_glass_incineration": 0.02, "disposal_glass_landfill": 0.01,
    "disposal_aluminium_incineration": 0.05, "disposal_aluminium_landfill": 0.03,
    "disposal_board_incineration": 0.05, "disposal_board_landfill": 0.9,
}


def demo_factors():
    return {"method": "ILLUSTRATIVE demo values, not BAFU", "path": "demo_factors.py",
            "citation": "ILLUSTRATIVE demo values, not real data", "demo": True,
            "factors": {k: {"impacts": {CATEGORY: v}} for k, v in _VALUES.items()}}

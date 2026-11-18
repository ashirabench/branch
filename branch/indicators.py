"""Impact categories: every indicator the LCIA method gives, not only climate.

ISO 14044 asks for the impact categories relevant to the goal, and the
Environmental Footprint method has sixteen. The factors file from
extract_factors.py already holds every category of the method for every
dataset, so BRANCH can report all of them with the same answers.

Units and plain names follow the Environmental Footprint 3.1 method
(European Commission, Joint Research Centre 2022). Names are matched by
keywords because openLCA packs label them slightly differently.
"""

# (keywords that must all appear, lower case) -> (plain name, unit). Order matters.
EF31 = [
    (("climate", "fossil"), ("Climate change, fossil", "kg CO2 eq")),
    (("climate", "biogenic"), ("Climate change, biogenic", "kg CO2 eq")),
    (("climate", "land use"), ("Climate change, land use", "kg CO2 eq")),
    (("climate",), ("Climate change", "kg CO2 eq")),
    (("ozone depletion",), ("Ozone layer depletion", "kg CFC-11 eq")),
    (("photochemical",), ("Smog (photochemical ozone)", "kg NMVOC eq")),
    (("particulate",), ("Fine particles (health)", "disease incidence")),
    (("ionising",), ("Ionising radiation", "kBq U-235 eq")),
    (("acidification",), ("Acidification", "mol H+ eq")),
    (("eutrophication", "freshwater"), ("Eutrophication, freshwater", "kg P eq")),
    (("eutrophication", "marine"), ("Eutrophication, marine", "kg N eq")),
    (("eutrophication", "terrestrial"), ("Eutrophication, terrestrial", "mol N eq")),
    (("ecotoxicity",), ("Ecotoxicity, freshwater", "CTUe")),
    (("toxicity", "non-cancer"), ("Human toxicity, non-cancer", "CTUh")),
    (("toxicity", "non cancer"), ("Human toxicity, non-cancer", "CTUh")),
    (("toxicity", "cancer"), ("Human toxicity, cancer", "CTUh")),
    (("land use",), ("Land use", "dimensionless (points)")),
    (("water",), ("Water use", "m3 world eq deprived")),
    (("resource", "fossil"), ("Fossil resource use", "MJ")),
    (("resource", "mineral"), ("Mineral and metal resource use", "kg Sb eq")),
]


def describe(category):
    """(plain name, unit) for a category name of the method."""
    c = (category or "").lower()
    for words, out in EF31:
        if all(w in c for w in words):
            name, unit_ = out
            for part in ("inorganics", "organics"):          # the method splits the toxicity indicators
                if f"({part})" in c:
                    name += f", {part}"
                    break
            return name, unit_
    return category, "units"


def unit(category):
    return describe(category)[1]


def is_subcategory(category):
    c = (category or "").lower()
    if "(organics)" in c or "(inorganics)" in c:             # parts of a toxicity indicator
        return True
    return c.startswith("climate") and c != "climate change" and any(w in c for w in ("fossil", "biogenic", "land use"))


def available(factors):
    """Categories present for every dataset in a factors file, main ones first."""
    sets = [set(f.get("impacts", {})) for f in factors.get("factors", {}).values()]
    if not sets:
        return []
    common = set.intersection(*sets)
    return sorted(common, key=lambda c: (is_subcategory(c), c.lower() != "climate change", c.lower()))

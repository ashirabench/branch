"""Plain language help for every question the agent can ask (Meta 3).

For a manager who is not an LCA expert, each question says why it can change the
verdict and where in the company the real number is usually found. Shares are asked
in percent (40 means 40%), which is how people read them on invoices and reports.
"""

# choice name suffix -> (why it matters, where to find it)
HELP = {
    "mass_g": (
        "Heavier packaging needs more material to make, carry and dispose of.",
        "Weigh one empty unit on a kitchen or lab scale, or read the weight on the supplier's "
        "technical data sheet."),
    "dataset": (
        "Different grades of the same material are made differently and have different impacts.",
        "Ask your packaging supplier which grade or colour they deliver; it is on the order or the "
        "data sheet."),
    "recycled_content": (
        "Recycled material usually has a lower impact than new material.",
        "The supplier's data sheet or certificate (for example a recycled content declaration) gives "
        "this share."),
    "recycled_ratio": (
        "It says how much lighter recycled material is than new material, for materials where the "
        "database has no recycled dataset.",
        "Leave the default unless an LCA consultant or a published study gives you a value."),
    "recycling_rate": (
        "Material that is collected and recycled avoids landfill or incineration at the end of life.",
        "Your packaging compliance scheme (the organisation you pay for packaging take back) or the "
        "national waste statistics publish collection rates per material."),
    "incineration_share": (
        "Burning waste releases carbon dioxide; landfill releases methane later. The split changes the "
        "end of life impact.",
        "National waste statistics (for example Eurostat for Europe) report how much municipal waste "
        "is incinerated and how much is landfilled."),
    "end_of_life": (
        "What happens to a container after its last use changes the impact of disposal.",
        "Ask whoever collects your empty containers, or check your take back contract."),
    "trips": (
        "A refillable container spreads its production impact over every filling; more trips means "
        "less impact per use.",
        "Count how many containers you buy per year against how many fillings you sell, or ask the "
        "bottle pool operator for the return rate."),
    "wash_kwh": (
        "Washing refillable containers uses electricity every time they come back.",
        "Divide the washing line's yearly electricity (from the meter or the energy bill) by the "
        "containers washed in a year."),
    "wash_heat_mj": (
        "Hot water for washing usually comes from a gas boiler.",
        "Divide the yearly gas used for washing (gas bill, in kWh; 1 kWh = 3.6 MJ) by the containers "
        "washed in a year."),
    "wash_water_kg": (
        "Washing uses water every time a container comes back.",
        "Divide the yearly water used by the washing line (water bill or meter) by the containers "
        "washed in a year."),
    "distribution_km": (
        "Every kilometre the truck drives adds fuel use, and heavier packaging makes it count more.",
        "Your logistics provider or delivery notes give the distance from your plant to the main "
        "customers; use a typical one way distance."),
    "_km": (
        "Transport from the packaging producer to your plant adds fuel use.",
        "The supplier's address and the transport mode on the delivery note; a route planner gives "
        "the distance."),
    "electricity": (
        "Electricity from coal or oil has a much larger impact than from hydro, wind or solar.",
        "Your electricity bill says which supplier and, often, which energy mix you buy."),
}

PERCENT = ("recycled_content", "recycled_ratio", "recycling_rate", "incineration_share")


def key(name):
    """HELP key for a choice name such as 'pet.pet.recycling_rate' or 'supply.barge_km'."""
    last = name.split(".")[-1]
    if last in HELP:
        return last
    if last.endswith("_km"):
        return "_km"
    return None


def help_for(name):
    """(why it matters, where to find it), or None for a choice with no help yet."""
    k = key(name)
    return HELP.get(k) if k else None


def is_percent(name):
    return name.split(".")[-1] in PERCENT


def percent_question(text):
    """'What share ... (0 to 1)?' -> 'What share ... (%)?'"""
    return text.replace("(0 to 1)", "(%)")


def fmt_pct(x, digits=4):
    """A probability as people read it: 0.975 -> '97.5%', 0.95 -> '95%', 0.025 -> '2.5%'."""
    return f"{x * 100:.{digits}g}%"


def plural(n, noun):
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"

"""Region files of the European countries from two Eurostat tables.

    python experiments/data/make_eu_regions.py            # writes data/regions/EU.json and one file per country
    python experiments/data/make_eu_regions.py --check    # fails if the files on disk differ from what the tables give

Input (kept in the repository, read on 15 November 2026 from the Eurostat data interface):

    data/eurostat/env_waspacr_2022_2024.csv   recycling rates of packaging waste by material
    data/eurostat/env_wasmun_2022_2024.csv    municipal waste incinerated and landfilled, thousand tonnes

Rules, fixed on 15 November 2026 before this script existed:

1. Centre of each prior: the mean of the last two years with a value (rates for the 2025 target).
2. Width: a beta distribution with weight 20, the weight already used for one official national
   figure. Weight 12 when there is only one year, when the two years differ by more than
   10 points, or when rule 4 applies. The weight is raised when needed so that neither
   parameter of the beta distribution falls below 1 (a mean of 93% needs a weight of 15).
3. A rate above 95% is cut at 95%: the model needs the share of a package that is recycled, and a
   rate above 100% does not describe that. A rate or a share below 5% is centred at 5%, and a share
   above 95% at 95%, both with weight 20, so that neither parameter of the beta distribution falls
   below 1. The source text says so each time.
4. Aluminium and steel reported as exactly zero while the two metals together are not: the rate of
   metallic packaging together is used.
5. The share incinerated of what is not recycled is municipal waste incinerated (with and without
   energy recovery) over incinerated plus landfilled, latest year with both values.
6. Plastic packaging is one figure for all polymers. It is used for PET, HDPE, LDPE and PP, as in the
   files of Portugal and Germany. PS, EPS, PVC and PLA keep the catalogue range.
7. Eurostat has no beverage carton category: that recycling rate stays the catalogue assumption.

Portugal, Germany and Brazil keep their own files with national sources; this script never writes them.
"""
import argparse
import csv
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "data", "eurostat")
OUT = os.path.join(ROOT, "data", "regions")
YEARS = ("2022", "2023", "2024")
TABLE = "Eurostat env_waspacr, rates for the 2025 target, table updated 10 November 2026"
MUNI = "Eurostat env_wasmun, table updated 15 October 2026"

# Eurostat code -> (region code, name, electricity factor key or None for the European grid)
COUNTRIES = {
    "AT": ("AT", "Austria"), "BE": ("BE", "Belgium"), "BG": ("BG", "Bulgaria"), "CY": ("CY", "Cyprus"),
    "CZ": ("CZ", "Czechia"), "DK": ("DK", "Denmark"), "EE": ("EE", "Estonia"), "EL": ("GR", "Greece"),
    "ES": ("ES", "Spain"), "FI": ("FI", "Finland"), "FR": ("FR", "France"), "HR": ("HR", "Croatia"),
    "HU": ("HU", "Hungary"), "IE": ("IE", "Ireland"), "IT": ("IT", "Italy"), "LT": ("LT", "Lithuania"),
    "LU": ("LU", "Luxembourg"), "LV": ("LV", "Latvia"), "MT": ("MT", "Malta"), "NL": ("NL", "Netherlands"),
    "PL": ("PL", "Poland"), "RO": ("RO", "Romania"), "SE": ("SE", "Sweden"), "SI": ("SI", "Slovenia"),
    "SK": ("SK", "Slovakia"), "IS": ("IS", "Iceland"), "NO": ("NO", "Norway"),
}
NO_OWN_MIX = {"CY", "MT"}          # no national electricity mix in BAFU:2026
EUROPEAN_GRID = "electricity_mv_ENTSO-E"
NEVER = {"PT", "DE", "BR", "BR-N", "BR-AM", "GLO"}

PLASTIC, ALU, STEEL, METAL, PAPER, GLASS = "W150102", "W15010401", "W15010402", "W150104", "W150101", "W150107"
LABEL = {PLASTIC: "plastic packaging", ALU: "aluminium packaging", STEEL: "steel packaging",
         METAL: "metallic packaging (aluminium and steel together)", PAPER: "paper and cardboard packaging",
         GLASS: "glass packaging"}
RECYCLING = {  # prior key -> (waste category, note)
    "pet.recycling_rate": (PLASTIC, "all plastics together, no separate figure for PET bottles"),
    "hdpe.recycling_rate": (PLASTIC, "all plastics together"),
    "ldpe.recycling_rate": (PLASTIC, "all plastics together"),
    "pp.recycling_rate": (PLASTIC, "all plastics together"),
    "aluminium.recycling_rate": (ALU, "all aluminium packaging, not only beverage cans"),
    "steel.recycling_rate": (STEEL, ""),
    "corrugated_board.recycling_rate": (PAPER, "all paper and cardboard packaging together"),
    "cartonboard.recycling_rate": (PAPER, "all paper and cardboard packaging together"),
    "kraft_paper.recycling_rate": (PAPER, "all paper and cardboard packaging together"),
}
INCINERATION = ["pet", "hdpe", "ldpe", "pp", "ps", "eps", "pvc", "pla", "aluminium", "steel",
                "liquid_packaging_board", "corrugated_board", "cartonboard", "kraft_paper"]


def read_tables():
    rates, muni = {}, {}
    with open(os.path.join(SRC, "env_waspacr_2022_2024.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["rule"] == "new":
                rates[(r["geo"], r["waste"])] = [(y, float(r[y])) for y in YEARS if r[y] != ""]
    with open(os.path.join(SRC, "env_wasmun_2022_2024.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            muni[(r["geo"], r["operation"])] = {y: float(r[y]) for y in YEARS if r[y] != ""}
    return rates, muni


def rate(rates, geo, waste):
    """(mean as a fraction, weight, text of the source) by rules 1 to 4, or None without data."""
    cat, notes = waste, []
    values = rates.get((geo, cat), [])[-2:]
    if waste in (ALU, STEEL) and values and all(v == 0 for _, v in values) and \
            any(v > 0 for _, v in rates.get((geo, METAL), [])):
        cat, values = METAL, rates[(geo, METAL)][-2:]
        notes.append(f"{LABEL[waste]} is reported as zero, so the figure is {LABEL[METAL]}")
    if not values:
        return None
    mean = sum(v for _, v in values) / len(values) / 100.0
    weight = 20
    if len(values) == 1:
        weight = 12
        notes.append("only one year reported")
    elif abs(values[0][1] - values[1][1]) > 10:
        weight = 12
        notes.append("the two years differ by more than 10 points")
    if cat != waste:
        weight = 12
    if mean > 0.95:
        notes.append(f"reported mean {mean * 100:.1f}%, cut at 95%")
        mean, weight = 0.95, 20
    if mean < 0.05:
        notes.append(f"reported mean {mean * 100:.1f}%, prior centred at 5%")
        mean, weight = 0.05, 20
    text = " and ".join(f"{v:g}% in {y}" for y, v in values)
    return mean, weight, f"{LABEL[cat]} recycled in {{place}}: {text}", notes


def beta(mean, weight):
    """Beta with this mean; the weight grows when needed so that neither parameter is below 1."""
    weight = max(weight, math.ceil(1 / min(mean, 1 - mean)))
    a = round(mean * weight, 1)
    return {"a": a, "b": round(weight - a, 1)}


def incinerated_share(muni, geo):
    inc, land = muni.get((geo, "DSP_I_RCV_E"), {}), muni.get((geo, "DSP_L_OTH"), {})
    for y in reversed(YEARS):
        if y in inc and y in land and inc[y] + land[y] > 0:
            return inc[y] / (inc[y] + land[y]), y, inc[y], land[y]
    return None


def region(geo, code, name, rates, muni, parent, electricity, needed):
    priors = {}
    place = {"EU": "the European Union", "NL": "the Netherlands"}.get(code, name)
    for key, (waste, note) in RECYCLING.items():
        got = rate(rates, geo, waste)
        if got is None:
            continue
        mean, weight, text, notes = got
        tail = "; ".join([n for n in [note] + notes if n])
        source = f"SOURCE: {text.format(place=place)} ({TABLE})" + (f"; {tail}" if tail else "")
        priors[key] = ["beta", beta(mean, weight), source]
    share = incinerated_share(muni, geo)
    if share is not None:
        s, year, inc, land = share
        src = (f"SOURCE: municipal waste in {place} in {year}: {inc:g} kt incinerated with or without energy "
               f"recovery and {land:g} kt landfilled, so {s * 100:.0f}% of what is not recycled is incinerated ({MUNI})")
        clipped = min(max(s, 0.05), 0.95)
        if clipped != s:
            src += f"; prior centred at {clipped * 100:.0f}%"
        for m in INCINERATION:
            priors[f"{m}.incineration_share"] = ["beta", beta(clipped, 20), src]
        glass = rate(rates, geo, GLASS)
        if glass is not None:
            mean, _, text, notes = glass
            rec = round(mean, 2)
            inc_w = round((1 - rec) * s, 2)
            tail = "; ".join(notes)
            priors["glass.end_of_life"] = {
                "weights": {"recycling (cut-off)": rec, "landfill": round(1 - rec - inc_w, 2), "incineration": inc_w},
                "source": f"SOURCE: {text.format(place=place)} ({TABLE}); the rest follows municipal waste, "
                          f"{s * 100:.0f}% incinerated in {year} ({MUNI})" + (f"; {tail}" if tail else "")}
    out = {"code": code, "name": name, "parent": parent}
    if code == "EU":
        out["group"] = True
    if electricity:
        out["electricity"] = electricity
    out["priors"] = priors
    out["sources_needed"] = needed
    return out


def build():
    rates, muni = read_tables()
    files = {"EU": region("EU27_2020", "EU", "European Union", rates, muni, "GLO", EUROPEAN_GRID,
                          ["A recycling rate of beverage cartons (Eurostat has no such category)"])}
    for geo, (code, name) in COUNTRIES.items():
        needed = ["A recycling rate of PET bottles alone (the figure used covers all plastic packaging)"]
        mix = f"electricity_mv_{code}"
        if code in NO_OWN_MIX:
            mix = None                                  # inherits the European grid from EU
            needed.append(f"A national electricity mix for {name} (BAFU:2026 has none; the European grid is used)")
        files[code] = region(geo, code, name, rates, muni, "EU", mix, needed)
    assert not set(files) & NEVER
    return files


def dump(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    return ap.parse_args()


def main():
    args = parse_args()
    bad = []
    for code, data in sorted(build().items()):
        path, text = os.path.join(OUT, f"{code}.json"), dump(data)
        if args.check:
            if not os.path.exists(path) or open(path, encoding="utf-8").read() != text:
                bad.append(code)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
    if bad:
        sys.exit(f"region files differ from the Eurostat tables: {bad}")
    print(f"{'checked' if args.check else 'wrote'} {len(build())} region files")


if __name__ == "__main__":
    main()

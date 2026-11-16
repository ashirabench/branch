"""How much of each prior comes from a source: a count for the paper, so that the label SOURCE
does not say more than it should.

    python experiments/prior_sources.py

Three groups, decided by the text that every prior carries (Choice.source):
  assumption    the text starts with ASSUMPTION: neither the centre nor the spread has a source
  centre only   the text starts with SOURCE, and the source gives the centre, one bound or the list
                of options; the spread, the other bound or the weights are my choice or my rule
                (for the national rates, a beta whose weight is the rule of make_eu_regions.py)
  whole         the text starts with SOURCE and the whole distribution comes from sources: the
                shares of a categorical choice, or both bounds of a range (the text then says
                "both bounds come from the source" or "the range covers")
No prior of BRANCH has an uncertainty that a source measured as such.
"""
import itertools
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BENCH = ["pet_bottle_1l", "glass_refillable_1l", "aluminium_can_330ml", "beverage_carton_1l"]
WHOLE_MARKERS = ("both bounds come from the source", "the range covers")
GROUPS = ("assumption", "centre only", "whole")


def group(choice):
    text = choice.source
    if not text.startswith("SOURCE"):
        return "assumption"
    if choice.kind == "categorical":
        return "centre only" if ("ASSUMPTION" in text or "uniform weights" in text) else "whole"
    return "whole" if any(m in text for m in WHOLE_MARKERS) else "centre only"


def count(models):
    """{region: {group: number of distinct askable priors}} over the models of each region."""
    out = {}
    for region, ms in models.items():
        seen = {}
        for m in ms:
            for c in m.choices:
                if c.askable:
                    seen[(c.name, c.source)] = group(c)
        out[region] = {g: sum(1 for v in seen.values() if v == g) for g in GROUPS}
    return out


def benchmark_counts(regions=("PT", "DE", "BR")):
    from branch.real_cases import compare
    return count({r: [compare(a, b, region=r) for a, b in itertools.combinations(BENCH, 2)] for r in regions})


def lines(counts):
    out = ["| Region | Priors | Assumption | Source for the centre only | Source for the whole distribution |",
           "|---|---|---|---|---|"]
    for region, c in counts.items():
        out.append(f"| {region} | {sum(c.values())} | {c['assumption']} | {c['centre only']} | {c['whole']} |")
    return out


if __name__ == "__main__":
    print("\n".join(lines(benchmark_counts())))

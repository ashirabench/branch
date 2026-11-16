"""Intervals by pair of products, the reading by size of effect and the count of sourced priors."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "experiments"))

import prior_sources  # noqa: E402
import summarize_benchmark as sb  # noqa: E402
import v02_summary  # noqa: E402
from branch.beliefs import Choice  # noqa: E402


def test_a_case_belongs_to_the_pair_of_its_products():
    assert sb.pair_of("PT_pet_bottle_1l_vs_glass_refillable_1l") == "pet_bottle_1l_vs_glass_refillable_1l"
    assert sb.pair_of("BR-AM_ps_cup_05l_vs_pla_cup_05l") == "ps_cup_05l_vs_pla_cup_05l"
    assert sb.pair_of("real_pet_vs_glass_PT") == "real_pet_vs_glass_PT"       # another shape: its own pair


def test_pairs_are_resampled_with_all_their_regions():
    cases = [f"{r}_{p}" for p in ("a_vs_b", "c_vs_d") for r in ("PT", "DE", "BR")]
    idx, members = sb.pair_index(cases, n=2000)
    assert idx.shape == (2000, 2) and [list(m) for m in members] == [[0, 1, 2], [3, 4, 5]]
    diff = np.array([1.0, 1.0, 1.0, 3.0, 3.0, 3.0])       # the regions of a pair agree: all the spread is between pairs
    by_pair = sb.boot_ratio(diff, np.ones(6), idx, members)
    assert set(np.round(by_pair, 9)) == {1.0, 2.0, 3.0}   # whole pairs only
    by_case = sb.boot_ratio(diff, np.ones(6), np.random.default_rng(0).integers(0, 6, size=(2000, 6)))
    assert by_pair.std() > by_case.std()                  # treating the six cases as independent is too narrow


def test_summary_gives_both_intervals(tmp_path):
    rng = np.random.default_rng(0)
    for region in ("PT", "DE"):
        for pair, extra in (("a_vs_b", 1), ("c_vs_d", 3)):
            rows = [dict(strategy=s, batch_size=3, seed=sd, questions=3 + (extra if s == "entropy" else 0) + int(rng.integers(0, 2)),
                         certified=True, correct=sd != 0)
                    for s in ("decision_flip", "entropy") for sd in range(6)]
            pd.DataFrame(rows).to_csv(tmp_path / f"{region}_{pair}_runs.csv", index=False)
    sb.main(str(tmp_path))
    out = pd.read_csv(tmp_path / "ALL_summary.csv").set_index("strategy")
    assert out.loc["entropy", "pairs"] == 2 and out.loc["entropy", "cases"] == 4
    for col in ("dq_ci95", "dq_ci95_pair"):
        lo, hi = v02_summary.interval(out.loc["entropy", col])
        assert lo <= out.loc["entropy", "dq_vs_decision_flip"] <= hi
    assert " to " in out.loc["decision_flip", "wrong_ci95_pair"]
    assert out.loc["entropy", "p_pair"] == 0.5            # two pairs, both above zero: 2 / 2^2, the smallest possible


def test_effect_against_a_base_is_read_by_size_and_sign():
    cases = [f"{r}_{p}" for p in ("a_vs_b", "c_vs_d", "e_vs_f") for r in ("PT", "DE")]
    base = [1.0, 1.2, 0.8, 1.1, 0.9, 1.0]
    same = v02_summary.effect_against([1.1, 1.0, 0.9, 1.2, 0.8, 1.1], base, cases)
    assert same[5].startswith("compatible") and same[3] <= 0 <= same[4]
    flipped = v02_summary.effect_against([-x for x in base], base, cases)
    assert flipped[5].startswith("NOT compatible") and "sign" in flipped[5]
    shifted = v02_summary.effect_against([x + 5 for x in base], base, cases)
    assert shifted[5].startswith("NOT compatible") and "excludes zero" in shifted[5]


def test_a_source_for_the_centre_is_not_a_source_for_the_spread():
    c = lambda kind, prior, text: Choice("x", kind, prior, text, question="?")  # noqa: E731
    u = ("uniform", {"low": 1, "high": 2})
    assert prior_sources.group(c("continuous", u, "ASSUMPTION: a guess")) == "assumption"
    assert prior_sources.group(c("continuous", u, "SOURCE: 1.4 g (X 2020); the bounds are my choice")) == "centre only"
    assert prior_sources.group(c("continuous", u, "SOURCE: 39.5% recycled (Eurostat)")) == "centre only"
    assert prior_sources.group(c("continuous", u, "SOURCE: 4.9 g and 5.8 g (X); both bounds come from the source")) == "whole"
    assert prior_sources.group(c("categorical", {"a": 1, "b": 2}, "SOURCE: shares of 2023 (Eurostat)")) == "whole"
    assert prior_sources.group(c("categorical", {"a": 1, "b": 1}, "SOURCE: BAFU datasets; ASSUMPTION on the weights")) == "centre only"

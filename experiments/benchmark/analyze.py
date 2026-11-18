"""Figures and statistics from run_grid.py output.

    python experiments/benchmark/analyze.py results/lca_J40

Produces (in results/):
  <tag>_boxplot_questions.png   questions to certify per strategy and batch size
                                (cf. Fig. 4 in Faria et al. 2022)
  <tag>_curve_pflip.png         mean P(verdict wrong) vs questions asked
                                (cf. Fig. 3 in Faria et al. 2022)
  <tag>_summary.csv             mean, median, certified %, accuracy %, latency,
                                paired Wilcoxon vs decision_flip
"""
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))

import json
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import wilcoxon  # noqa: E402

ORDER = ["random", "least_confident", "margin", "entropy", "sobol",
         "decision_entropy", "decision_flip_min", "decision_flip_min_tp", "decision_flip_tp",
         "decision_flip"]


KEY = ["case_seed", "seed", "batch_size", "n_samples"]      # what makes two runs the same world


def summary_table(df):
    """One line per strategy and batch size, with the paired Wilcoxon test against decision flip."""
    rows = []
    ref = df[df.strategy == "decision_flip"].set_index(KEY)["questions"]
    for (s, b), g in df.groupby(["strategy", "batch_size"]):
        row = dict(strategy=s, batch_size=b, runs=len(g),
                   q_mean=g.questions.mean(), q_median=g.questions.median(),
                   certified_pct=100 * g.certified.mean(),
                   correct_pct=100 * g.correct.mean(),
                   latency_mean_ms=1000 * g.latency_mean_s.mean())
        if s != "decision_flip" and len(ref):
            paired = g.set_index(KEY)["questions"].align(ref, join="inner")
            diff = paired[0] - paired[1]
            row["wilcoxon_p_vs_decision_flip"] = (
                wilcoxon(paired[0], paired[1]).pvalue if (diff != 0).any() else 1.0)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["batch_size", "q_mean"])


def boxplots(df, strategies, batches, path):
    fig, axes = plt.subplots(1, len(batches), figsize=(4.5 * len(batches), 4), squeeze=False)
    for ax, b in zip(axes[0], batches):
        data = [df[(df.strategy == s) & (df.batch_size == b)].questions for s in strategies]
        try:                                   # matplotlib >= 3.9
            ax.boxplot(data, tick_labels=strategies)
        except TypeError:                      # older matplotlib
            ax.boxplot(data, labels=strategies)
        ax.set_title(f"batch size {b}")
        ax.set_ylabel("questions to certify")
        ax.tick_params(axis="x", rotation=60)
    fig.tight_layout()
    fig.savefig(path, dpi=200)


def traces_by_strategy(path, batch):
    curves = defaultdict(list)
    with open(path) as fh:
        for line in fh:
            r = json.loads(line)
            if r["batch_size"] == batch:
                curves[r["strategy"]].append(r["trace"])
    return curves


def mean_curve(traces):
    """Mean probability of a wrong verdict after each question; a certified run stays at its last value."""
    L = max(t[-1]["questions"] for t in traces) + 1
    M = np.full((len(traces), L), np.nan)
    for i, t in enumerate(traces):
        for step in t:
            M[i, step["questions"]] = step["p_flip"]
        last = t[-1]["questions"]
        M[i, last:] = t[-1]["p_flip"]
        M[i] = pd.Series(M[i]).ffill().to_numpy()
    return np.arange(L), np.nanmean(M, axis=0)


def curves_figure(curves, strategies, path):
    fig, ax = plt.subplots(figsize=(6, 4))
    for s in strategies:
        if curves.get(s):
            ax.plot(*mean_curve(curves[s]), label=s)
    ax.axhline(0.05, ls="--", c="red", lw=1)
    ax.set_xlabel("questions asked")
    ax.set_ylabel("mean P(verdict wrong)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=200)


def main(prefix):
    df = pd.read_csv(f"{prefix}_runs.csv")
    strategies = [s for s in ORDER if s in df.strategy.unique()]
    batches = sorted(df.batch_size.unique())
    summary = summary_table(df)
    summary.to_csv(f"{prefix}_summary.csv", index=False)
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.3g}"))
    boxplots(df, strategies, batches, f"{prefix}_boxplot_questions.png")
    curves_figure(traces_by_strategy(f"{prefix}_traces.jsonl", batches[0]), strategies, f"{prefix}_curve_pflip.png")
    print(f"figures saved with prefix {prefix}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/lca_J40")

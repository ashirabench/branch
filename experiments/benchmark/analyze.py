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
import os as _os, sys as _sys
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


def main(prefix):
    df = pd.read_csv(f"{prefix}_runs.csv")
    strategies = [s for s in ORDER if s in df.strategy.unique()]
    batches = sorted(df.batch_size.unique())

    # summary + paired Wilcoxon (same seed and world, different strategy)
    rows = []
    key = ["case_seed", "seed", "batch_size", "n_samples"]
    ref = df[df.strategy == "decision_flip"].set_index(key)["questions"]
    for (s, b), g in df.groupby(["strategy", "batch_size"]):
        row = dict(strategy=s, batch_size=b, runs=len(g),
                   q_mean=g.questions.mean(), q_median=g.questions.median(),
                   certified_pct=100 * g.certified.mean(),
                   correct_pct=100 * g.correct.mean(),
                   latency_mean_ms=1000 * g.latency_mean_s.mean())
        if s != "decision_flip" and len(ref):
            paired = g.set_index(key)["questions"].align(ref, join="inner")
            diff = paired[0] - paired[1]
            row["wilcoxon_p_vs_decision_flip"] = (
                wilcoxon(paired[0], paired[1]).pvalue if (diff != 0).any() else 1.0)
        rows.append(row)
    summary = pd.DataFrame(rows).sort_values(["batch_size", "q_mean"])
    summary.to_csv(f"{prefix}_summary.csv", index=False)
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.3g}"))

    # boxplots
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
    fig.savefig(f"{prefix}_boxplot_questions.png", dpi=200)

    # P(flip) curves, batch 1
    curves = defaultdict(list)
    with open(f"{prefix}_traces.jsonl") as fh:
        for line in fh:
            r = json.loads(line)
            if r["batch_size"] == batches[0]:
                curves[r["strategy"]].append(r["trace"])
    fig, ax = plt.subplots(figsize=(6, 4))
    for s in strategies:
        traces = curves.get(s, [])
        if not traces:
            continue
        L = max(t[-1]["questions"] for t in traces) + 1
        M = np.full((len(traces), L), np.nan)
        for i, t in enumerate(traces):
            for step in t:
                M[i, step["questions"]] = step["p_flip"]
            last = t[-1]["questions"]
            M[i, last:] = t[-1]["p_flip"]  # certified runs stay at their final value
            M[i] = pd.Series(M[i]).ffill().to_numpy()
        ax.plot(np.arange(L), np.nanmean(M, axis=0), label=s)
    ax.axhline(0.05, ls="--", c="red", lw=1)
    ax.set_xlabel("questions asked")
    ax.set_ylabel("mean P(verdict wrong)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(f"{prefix}_curve_pflip.png", dpi=200)
    print(f"figures saved with prefix {prefix}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/lca_J40")

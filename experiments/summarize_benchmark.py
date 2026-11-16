"""One table for the whole benchmark: questions to certify per strategy, pooled over cases.

    python experiments/summarize_benchmark.py results/benchmark

Writes <folder>/ALL_summary.csv with, per strategy and batch size: runs, mean and
median questions, share certified and share of certified verdicts that are wrong.

The unit of inference is the CASE, not the session: the sessions of one case share
its beliefs, so they are not independent. Cases are not independent either: the same
pair of products appears in several regions. So every interval is given twice, by case
and by PAIR (all the regions of a pair are resampled together; a file named
<region>_<a>_vs_<b> belongs to the pair <a>_vs_<b>). With 6 or 10 pairs the pair
interval is coarse, and it is the one the readings of the plan use. Hence
  wrong_ci95_pair, dq_ci95_pair  the two intervals below, resampling pairs
  pairs                        number of pairs
  wrong_ci95                   95% percentile interval of a bootstrap over cases
                               (10,000 resamples; exact binomial over sessions when
                               no certificate is wrong, since the bootstrap is then 0)
  binom_ci95                   exact binomial interval over sessions (for reference)
  dq_vs_decision_flip          mean extra questions against decision_flip, per case
  dq_ci95                      its bootstrap interval over cases
  p_vs_decision_flip           exact paired sign flip permutation test on the per case
                               mean questions (two sided; exact with ties and zeros),
                               Holm adjusted over the strategies of a batch size
  p_raw                        the same test before the Holm adjustment
  cases_no_question            cases in which this strategy never asks (the verdict is
                               certified from the priors), which carry no paired information
"""
import glob
import os
import re
import sys

import numpy as np
import pandas as pd
import itertools

from scipy.stats import binomtest


def sign_flip_p(diff):
    """Exact two sided paired permutation test of mean(diff) = 0 (flip each case's sign)."""
    d = np.asarray([x for x in diff if x != 0], dtype=float)
    if len(d) == 0:
        return 1.0
    obs = abs(d.sum())
    if len(d) <= 20:
        signs = np.array(list(itertools.product((1, -1), repeat=len(d))))
        stats = np.abs(signs @ d)
    else:
        stats = np.abs(np.random.default_rng(1).choice((1, -1), size=(200_000, len(d))) @ d)
    return float((stats >= obs - 1e-12).mean())


def pair_of(case):
    """<region>_<a>_vs_<b> -> <a>_vs_<b>; a name of another shape is its own pair."""
    m = re.match(r"^[A-Z]{2,3}(?:-[A-Z0-9]+)?_(.+_vs_.+)$", case)
    return m.group(1) if m else case


def pair_index(cases, n=10_000, seed=0):
    """(resamples x pairs) indices and, per pair, the positions of its cases."""
    pairs = sorted({pair_of(c) for c in cases})
    members = [np.array([i for i, c in enumerate(cases) if pair_of(c) == p]) for p in pairs]
    return np.random.default_rng(seed).integers(0, len(pairs), size=(n, len(pairs))), members


def boot_ratio(num, den, idx, members=None):
    """Resampled sum(num) / sum(den): over cases, or over pairs when members is given."""
    if members is not None:
        num = np.array([num[m].sum() for m in members])
        den = np.array([den[m].sum() for m in members])
    return num[idx].sum(1) / np.maximum(den[idx].sum(1), 1)


def main(folder):
    frames = []
    for f in sorted(glob.glob(os.path.join(folder, "*_runs.csv"))):
        df = pd.read_csv(f)
        df["case"] = os.path.basename(f)[: -len("_runs.csv")]
        frames.append(df)
    if not frames:
        raise SystemExit(f"no *_runs.csv in {folder}")
    df = pd.concat(frames, ignore_index=True)
    df["wrong"] = (df.certified & ~df.correct.astype(bool)).astype(int)
    cases = sorted(df.case.unique())
    idx = np.random.default_rng(0).integers(0, len(cases), size=(10_000, len(cases)))
    pidx, members = pair_index(cases)
    ones = np.ones(len(cases))
    rows = []
    for b, gb in df.groupby("batch_size"):
        per = gb.groupby(["strategy", "case"]).agg(q=("questions", "mean"), w=("wrong", "sum"),
                                                   n=("certified", "sum")).reset_index()
        ref = per[per.strategy == "decision_flip"].set_index("case").reindex(cases)
        block = []
        for s, g in gb.groupby("strategy"):
            h = per[per.strategy == s].set_index("case").reindex(cases)
            W, N = h.w.to_numpy(), h.n.to_numpy()
            wrong, ncert = int(W.sum()), int(N.sum())
            binom = binomtest(wrong, ncert).proportion_ci() if ncert else None
            if wrong and ncert:
                lo, hi = np.percentile(boot_ratio(W, N, idx), [2.5, 97.5])
                plo, phi = np.percentile(boot_ratio(W, N, pidx, members), [2.5, 97.5])
            elif binom:
                lo, hi = plo, phi = binom.low, binom.high
            else:
                lo = hi = plo = phi = float("nan")
            row = dict(strategy=s, batch_size=b, runs=len(g), cases=g.case.nunique(),
                       q_mean=g.questions.mean(), q_median=g.questions.median(),
                       certified_pct=100 * g.certified.mean(),
                       wrong_when_certified_pct=100 * wrong / ncert if ncert else float("nan"),
                       wrong_ci95=f"{100 * lo:.1f} to {100 * hi:.1f}",
                       wrong_ci95_pair=f"{100 * plo:.1f} to {100 * phi:.1f}", pairs=len(members),
                       binom_ci95=f"{100 * binom.low:.1f} to {100 * binom.high:.1f}" if binom else "",
                       cases_no_question=int((g.groupby("case").questions.max() == 0).sum()))
            if s != "decision_flip" and ref.q.notna().all():
                diff = h.q.to_numpy() - ref.q.to_numpy()
                bd = diff[idx].mean(1)
                row["dq_vs_decision_flip"] = diff.mean()
                row["dq_ci95"] = "{:.2f} to {:.2f}".format(*np.percentile(bd, [2.5, 97.5]))
                row["dq_ci95_pair"] = "{:.2f} to {:.2f}".format(
                    *np.percentile(boot_ratio(diff, ones, pidx, members), [2.5, 97.5]))
                row["p_raw"] = sign_flip_p(diff)
            block.append(row)
        raw = [(i, r["p_raw"]) for i, r in enumerate(block) if "p_raw" in r]
        running = 0.0
        for k, (i, pv) in enumerate(sorted(raw, key=lambda t: t[1])):   # Holm step down
            running = max(running, min(1.0, (len(raw) - k) * pv))
            block[i]["p_vs_decision_flip"] = running
        rows += block
    out = pd.DataFrame(rows).sort_values(["batch_size", "q_mean"])
    out.to_csv(os.path.join(folder, "ALL_summary.csv"), index=False)
    print(out.to_string(index=False, float_format=lambda v: f"{v:.3g}"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/benchmark")

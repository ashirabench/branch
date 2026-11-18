"""Every figure and table of the paper, from the benchmark summaries.

    python experiments/benchmark/paper_assets.py                 # uses results/ when present, else paper/data/
    python experiments/benchmark/paper_assets.py --from-snapshot # always the committed snapshot

Inputs: results/benchmark*/ALL_summary.csv written by experiments/benchmark/summarize_benchmark.py
(copied to paper/data/ as a snapshot so the paper also builds without rerunning the
benchmark). Outputs: paper/figures/*.pdf and paper/tables/*.tex.
"""
import argparse
import glob
import os
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

CHOSEN_B = 3   # questions per round used by the app (chosen setting)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAPER = os.path.join(ROOT, "paper")
SNAP = os.path.join(PAPER, "data")
FIGS = os.path.join(PAPER, "figures")
TABS = os.path.join(PAPER, "tables")

# results folder written by run_benchmark.sh -> snapshot name
RUNS = {"benchmark": "benchmark.csv", "benchmark_tails": "benchmark_tails.csv",
        "benchmark_tau0.025": "benchmark_tau0.025.csv",
        "benchmark_tails_tau0.025": "benchmark_tails_tau0.025.csv"}

INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
# categorical slots in fixed order (dataviz reference palette, validated)
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
STRATS = [("decision_flip", "decision flip, $p(1-p)$", "o"),
          ("sobol", "Sobol index of the impact", "s"),
          ("decision_flip_min", "decision flip, $\\min(p,1-p)$", "D"),
          ("entropy", "entropy, least confident", "^"),
          ("margin", "margin", "v"),
          ("random", "random", "x")]
NAMES = {"decision_flip": "Decision flip, $p(1-p)$", "decision_flip_tp": "Decision flip, total probability",
         "decision_entropy": "Decision entropy, $H(p)$", "decision_flip_min": "Decision flip, $\\min(p,1-p)$",
         "sobol": "Sobol index of the impact", "entropy": "Entropy", "least_confident": "Least confident",
         "margin": "Margin", "random": "Random"}

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                     "mathtext.fontset": "stix", "font.size": 8, "axes.edgecolor": MUTED,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.4})


def refresh_snapshot():
    """Summarise the raw runs again and copy the summaries into paper/data/ when they exist.

    The summary is always rebuilt from the *_runs.csv files with the current
    summarize_benchmark.py, so an old ALL_summary.csv can never overwrite the snapshot."""
    import summarize_benchmark
    for folder, name in RUNS.items():
        run_dir = os.path.join(ROOT, "results", folder)
        if not glob.glob(os.path.join(run_dir, "*_runs.csv")):
            continue
        summarize_benchmark.main(run_dir)
        src = os.path.join(run_dir, "ALL_summary.csv")
        if pd.read_csv(src).batch_size.nunique() == 5:   # not a QUICK run
            shutil.copy(src, os.path.join(SNAP, name))
            print("snapshot updated from", os.path.relpath(src, ROOT))
    # the run with new seeds (CONFIRM=1): two batch sizes, decision flip only
    run_dir = os.path.join(ROOT, "results", "benchmark_tails_tau0.025_confirm")
    if glob.glob(os.path.join(run_dir, "*_runs.csv")):
        summarize_benchmark.main(run_dir)
        src = os.path.join(run_dir, "ALL_summary.csv")
        if (pd.read_csv(src).runs >= 540).all():   # not a QUICK run
            shutil.copy(src, os.path.join(SNAP, "benchmark_tails_tau0.025_confirm.csv"))
            print("snapshot updated from", os.path.relpath(src, ROOT))


def t(name):
    return pd.read_csv(os.path.join(SNAP, name))


def row(d, s, b):
    return d[(d.strategy == s) & (d.batch_size == b)].iloc[0]


def fig_batch():
    """Mean questions to certify vs batch size, experts from the priors, tau = 5%."""
    d = t("benchmark.csv")
    fig, ax = plt.subplots(figsize=(3.35, 2.35))
    for (s, label, mk), c in zip(STRATS, SLOTS):
        g = d[d.strategy == s].sort_values("batch_size")
        ax.plot(g.batch_size, g.q_mean, color=c, marker=mk, ms=4, label=label,
                ls="--" if s == "sobol" else "-")
    ax.axvline(CHOSEN_B, ymax=0.62, color=MUTED, lw=0.6, ls=":", zorder=0)
    ax.text(CHOSEN_B + 0.06, 0.25, "app: 3 per round", fontsize=6, color=MUTED)
    ax.set_xticks(range(1, 6))
    ax.set_xlabel("questions asked per round (batch size)")
    ax.set_ylabel("mean questions to certify")
    ax.set_ylim(0, 8.2)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=6.5, loc="upper left", ncol=2, columnspacing=0.8, handlelength=1.6)
    fig.tight_layout(pad=0.3)
    fig.savefig(os.path.join(FIGS, "batch.pdf"))
    plt.close(fig)


def fig_calibration():
    """Share of certified verdicts that are wrong, decision flip, experts from the tails."""
    fig, ax = plt.subplots(figsize=(3.35, 2.2))
    for (f, tau, label), c, dx in [(("benchmark_tails.csv", 5.0, "certificate $\\tau$ = 5%"), SLOTS[0], -0.08),
                                   (("benchmark_tails_tau0.025.csv", 2.5, "certificate $\\tau$ = 2.5%"), SLOTS[1], 0.08)]:
        d = t(f)
        g = d[d.strategy == "decision_flip"].sort_values("batch_size")
        lo = g.wrong_ci95.str.split(" to ").str[0].astype(float)
        hi = g.wrong_ci95.str.split(" to ").str[1].astype(float)
        x = g.batch_size + dx
        ax.errorbar(x, g.wrong_when_certified_pct, yerr=[g.wrong_when_certified_pct - lo,
                                                         hi - g.wrong_when_certified_pct],
                    fmt="o-", ms=3.5, color=c, ecolor=c, elinewidth=1, capsize=0, label=label)
        ax.axhline(tau, color=c, lw=0.8, ls="--")
    conf = os.path.join(SNAP, "benchmark_tails_tau0.025_confirm.csv")
    if os.path.exists(conf):
        g = pd.read_csv(conf).sort_values("batch_size")
        lo = g.wrong_ci95.str.split(" to ").str[0].astype(float)
        hi = g.wrong_ci95.str.split(" to ").str[1].astype(float)
        ax.errorbar(g.batch_size + 0.24, g.wrong_when_certified_pct,
                    yerr=[g.wrong_when_certified_pct - lo, hi - g.wrong_when_certified_pct],
                    fmt="o", ms=3.5, mfc="white", color=SLOTS[1], ecolor=SLOTS[1], elinewidth=1,
                    capsize=0, label="$\\tau$ = 2.5%, new seeds")
    ax.set_xticks(range(1, 6))
    ax.set_xlabel("questions asked per round (batch size)")
    ax.set_ylabel("wrong when certified (%)")
    ax.set_ylim(0, 13.5)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=6.5, loc="upper right")
    fig.tight_layout(pad=0.3)
    fig.savefig(os.path.join(FIGS, "calibration.pdf"))
    plt.close(fig)


def fig_overview():
    """docs/assets/branch_overview.svg -> paper/figures/overview.pdf (needs Playwright)."""
    svg = os.path.join(ROOT, "docs", "assets", "branch_overview.svg")
    out = os.path.join(FIGS, "overview.pdf")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed: keeping the committed overview.pdf")
        return
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto("file://" + svg)
        page.pdf(path=out, width="960px", height="420px", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"}, page_ranges="1")
        b.close()


def _p(v):
    if pd.isna(v):
        return "--"
    if v < 1e-3:
        e = int(f"{v:.0e}".split("e")[1])
        return f"$<10^{{{e + 1}}}$"
    return f"{v:.3f}".rstrip("0").rstrip(".") if v < 0.1 else f"{v:.2f}"


def tab_main():
    """Chosen setting (tau 2.5%, three questions per round): questions, p value, calibration, both expert models."""
    prior, tails = t("benchmark_tau0.025.csv"), t("benchmark_tails_tau0.025.csv")
    order = ["decision_flip", "sobol", "entropy", "least_confident", "margin", "random"]
    lines = []
    for s in order:
        a, b = row(prior, s, CHOSEN_B), row(tails, s, CHOSEN_B)
        name = NAMES[s] + (" (ours)" if s == "decision_flip" else "")
        cells = [name, f"{a.q_mean:.2f}", _p(a.p_vs_decision_flip),
                 f"{a.wrong_when_certified_pct:.1f}", f"{b.q_mean:.2f}", _p(b.p_vs_decision_flip),
                 f"{b.wrong_when_certified_pct:.1f}"]
        if s == "decision_flip":
            cells = [f"\\textbf{{{c}}}" if i in (1, 4) else c for i, c in enumerate(cells)]
        lines.append(" & ".join(cells) + " \\\\")
    with open(os.path.join(TABS, "main.tex"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def tab_losses():
    """Ablation of the loss: mean questions, batch 1, 2 and 3, four conditions."""
    conds = [("benchmark.csv", "Priors, 5\\%"), ("benchmark_tau0.025.csv", "Priors, 2.5\\%"),
             ("benchmark_tails.csv", "Tails, 5\\%"), ("benchmark_tails_tau0.025.csv", "Tails, 2.5\\%")]
    order = ["decision_flip", "decision_flip_tp", "decision_entropy", "decision_flip_min"]
    lines = []
    for s in order:
        cells = [NAMES[s]]
        for f, _ in conds:
            d = t(f)
            for b in (1, 2, 3):
                r = row(d, s, b)
                star = "^{*}" if (s != "decision_flip" and r.p_vs_decision_flip < 0.05) else ""
                cells.append(f"${r.q_mean:.2f}{star}$")
        lines.append(" & ".join(cells) + " \\\\")
    with open(os.path.join(TABS, "losses.tex"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def macro(name, text):
    return f"\\newcommand{{\\{name}}}{{{text}}}\n"


def numbers():
    """Values quoted in the text, as LaTeX macros, so prose and tables never disagree."""
    p, pt = t("benchmark.csv"), t("benchmark_tails.csv")
    c, ct = t("benchmark_tau0.025.csv"), t("benchmark_tails_tau0.025.csv")
    h = t("benchmark_tails_tau0.025_confirm.csv")     # the chosen setting with new seeds (1000 to 1029)
    chosen = row(c, "decision_flip", CHOSEN_B)
    lines = (_questions_and_wrong(p, pt, c, ct, h) + _intervals(p, pt, ct, h) + _p_values(p, c)
             + [macro("nRuns", int(chosen.runs)), macro("nCases", int(chosen.cases)),
                macro("nNoQLoose", int(row(p, "decision_flip", 1).cases_no_question)),
                macro("nNoQStrict", int(row(c, "decision_flip", 1).cases_no_question))]
             + _agreement_with_openlca())
    with open(os.path.join(TABS, "numbers.tex"), "w", encoding="utf-8") as f:
        f.writelines(lines)


def _questions_and_wrong(p, pt, c, ct, h):
    """Mean questions (two decimals) and wrong certificates (per cent, one decimal)."""
    m = {
        "qFlipPriorOne": row(p, "decision_flip", 1).q_mean, "qSobolPriorOne": row(p, "sobol", 1).q_mean,
        "qEntPriorOne": row(p, "entropy", 1).q_mean, "qRandPriorOne": row(p, "random", 1).q_mean,
        "qMinPriorOne": row(p, "decision_flip_min", 1).q_mean,
        "qFlipChosen": row(c, "decision_flip", CHOSEN_B).q_mean, "qSobolChosen": row(c, "sobol", CHOSEN_B).q_mean,
        "qEntChosen": row(c, "entropy", CHOSEN_B).q_mean, "qRandChosen": row(c, "random", CHOSEN_B).q_mean,
        "qFlipChosenTails": row(ct, "decision_flip", CHOSEN_B).q_mean,
        "qEntChosenTails": row(ct, "entropy", CHOSEN_B).q_mean,
        "wFlipTailsOne": row(pt, "decision_flip", 1).wrong_when_certified_pct,
        "wFlipTailsTwo": row(pt, "decision_flip", 2).wrong_when_certified_pct,
        "wFlipStrictTwo": row(ct, "decision_flip", 2).wrong_when_certified_pct,
        "qFlipChosenTwo": row(c, "decision_flip", 2).q_mean,
        "wFlipTailsStrictOne": row(ct, "decision_flip", 1).wrong_when_certified_pct,
        "wFlipChosenTails": row(ct, "decision_flip", CHOSEN_B).wrong_when_certified_pct,
        "wSobolTailsStrictOne": row(ct, "sobol", 1).wrong_when_certified_pct,
        "wRandTailsOne": row(pt, "random", 1).wrong_when_certified_pct,
        "wFlipPriorOne": row(p, "decision_flip", 1).wrong_when_certified_pct,
        "wFlipHoldThree": row(h, "decision_flip", 3).wrong_when_certified_pct,
        "wFlipHoldTwo": row(h, "decision_flip", 2).wrong_when_certified_pct,
        "qFlipHoldThree": row(h, "decision_flip", 3).q_mean,
    }
    return [macro(k, f"{v:.2f}" if k.startswith("q") else f"{v:.1f}\\%") for k, v in m.items()]


def _intervals(p, pt, ct, h):
    ci = {"ciFlipTailsOne": row(pt, "decision_flip", 1).wrong_ci95,
          "ciFlipChosenTails": row(ct, "decision_flip", CHOSEN_B).wrong_ci95,
          "ciFlipStrictTwo": row(ct, "decision_flip", 2).wrong_ci95,
          "ciFlipPriorOne": row(p, "decision_flip", 1).wrong_ci95,
          "ciFlipHoldThree": row(h, "decision_flip", 3).wrong_ci95,
          "ciFlipHoldTwo": row(h, "decision_flip", 2).wrong_ci95}
    return [macro(k, v.replace(" to ", "--") + "\\%") for k, v in ci.items()]


def _p_values(p, c):
    pv = {"pSobolPriorOne": row(p, "sobol", 1).p_vs_decision_flip,
          "pSobolChosen": row(c, "sobol", CHOSEN_B).p_vs_decision_flip}
    return [macro(k, f"{v:.3f}") for k, v in pv.items()]


def _agreement_with_openlca():
    """The 36 benchmark products and one comparison in every grid: counts, largest differences, impacts."""
    v, g = t("validation_openlca.csv"), t("validation_all_grids.csv")
    g = g[g["product"].notna() & (g["product"].astype(str) != "")]
    imp = v.groupby(["product", "region"]).openLCA.mean()
    glass = g[g["product"] == "Refillable glass"].set_index("region").openLCA.astype(float)
    lines = [macro("nGridProducts", len(g)), macro("nGridRegions", g.region.nunique()),
             macro("nGrids", int((~g.region.drop_duplicates().str.startswith("BR-")).sum()))]
    for k, value in (("maxDiffBench", v.relative_difference.max()),
                     ("maxDiffGrids", g.relative_difference.astype(float).max())):
        mant, exp = f"{value:.1e}".split("e")
        lines.append(macro(k, f"${mant}\\times10^{{{int(exp)}}}$"))
    short = {"Beverage carton 1 L": "Carton", "PET single use": "PET", "Aluminium can 330 ml": "Can",
             "Refillable glass": "Glass"}
    lines += [macro(f"imp{short[prod]}{r}", f"{imp.loc[(prod, r)]:.3f}") for prod in short for r in ("PT", "DE", "BR")]
    lines.append(macro("impGlassAM", f"{glass['BR-AM']:.3f}"))
    lines.append(macro("dropAM", f"{round(100 * (1 - glass['BR-AM'] / glass['BR']))}\\%"))
    return lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-snapshot", action="store_true")
    args = ap.parse_args()
    for d in (SNAP, FIGS, TABS):
        os.makedirs(d, exist_ok=True)
    if not args.from_snapshot:
        refresh_snapshot()
    fig_batch()
    fig_calibration()
    fig_overview()
    tab_main()
    tab_losses()
    numbers()
    print("paper assets in", os.path.relpath(FIGS, ROOT), "and", os.path.relpath(TABS, ROOT))

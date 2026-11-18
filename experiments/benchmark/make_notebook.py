"""Build notebooks/branch_walkthrough.ipynb (run, then execute it with nbconvert).

    python experiments/benchmark/make_notebook.py
    jupyter nbconvert --to notebook --execute --inplace notebooks/branch_walkthrough.ipynb
"""
import os

import nbformat as nbf

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("# BRANCH walkthrough\n\n"
       "This notebook reproduces the core of the paper in a few minutes: the lemma behind the query "
       "strategy, one session of the agent on a real comparison, a small version of the benchmark, and "
       "the figures of the paper. The full benchmark is `bash reproduce.sh` (several hours).\n\n"
       "Data: Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026. The factors are "
       "extracted locally from openLCA (`bash reproduce.sh data`) and never redistributed. Without them the "
       "notebook runs on **illustrative demo numbers**, and says so below."),
    code("import os, sys\n"
         "ROOT = os.path.abspath('..') if os.path.basename(os.getcwd()) == 'notebooks' else os.getcwd()\n"
         "sys.path.insert(0, ROOT); os.chdir(ROOT)\n"
         "import numpy as np, pandas as pd\n"
         "from branch.real_cases import load_factors\n"
         "from branch.demo_factors import demo_factors\n"
         "try:\n"
         "    factors, DEMO = load_factors(), False\n"
         "except FileNotFoundError:\n"
         "    factors, DEMO = demo_factors(), True\n"
         "print('DEMO NUMBERS, not real inventory data' if DEMO else 'Real factors: ' + os.path.relpath(factors['path'], ROOT))"),

    md("## 1. The lemma\n\n"
       "BRANCH scores an open choice $j$ by the expected reduction of $p(1-p)$, with "
       "$p = P(I_A < I_B)$. Proposition 1: this equals $p(1-p)\\,S_j(D)$, the first order Sobol index of the "
       "verdict $D = 1\\{I_A < I_B\\}$. Below, the score and $p(1-p)S_j(D)$ computed directly agree up to the "
       "Monte Carlo gap."),
    code("from branch.cases import toy_packaging\n"
         "from branch.montecarlo import State, p_a_lower\n"
         "from branch.query import STRATEGIES\n"
         "m = toy_packaging(); st = State(m, m.sample(200_000, seed=11))\n"
         "scores = STRATEGIES['decision_flip'](st, np.random.default_rng(0))\n"
         "rows = []\n"
         "for name in st.open:\n"
         "    d, w = st.conditional_deltas(name)\n"
         "    pk = (d < 0).mean(axis=1); pbar = float((w * pk).sum())\n"
         "    s_j = float((w * (pk - pbar) ** 2).sum()) / (pbar * (1 - pbar))\n"
         "    rows.append((name, scores[name], pbar * (1 - pbar) * s_j, s_j))\n"
         "pd.DataFrame(rows, columns=['choice', 'decision flip score', 'p(1-p) S_j(D)', 'S_j(D)'])"
         ".sort_values('decision flip score', ascending=False).round(5)"),
    md("Proposition 2: the literal loss $\\min(p, 1-p)$ scores every question zero when no single answer can "
       "carry $p$ across 1/2, so the agent stalls. With the total probability estimator this is exact:"),
    code("from tests.test_lemma import _leaning_model\n"
         "lm = _leaning_model(); s2 = State(lm, lm.sample(100_000, seed=3))\n"
         "print('p =', round(float(p_a_lower(s2.delta)), 4))\n"
         "print('min(p,1-p) scores:', STRATEGIES['decision_flip_min_tp'](s2, np.random.default_rng(0)))\n"
         "print('p(1-p) scores:    ', STRATEGIES['decision_flip_tp'](s2, np.random.default_rng(0)))"),

    md("## 2. One session: single use PET against refillable glass in Portugal\n\n"
       "A simulated expert holds a hidden true value for every choice and answers each question with it. "
       "The agent asks three questions per round and stops when the verdict is wrong with probability below "
       "2.5%, the setting of the web application."),
    code("from branch.real_cases import compare\n"
         "from branch.cases import draw_truth\n"
         "from branch.agent import run_agent\n"
         "model = compare('pet_bottle_1l', 'glass_refillable_1l', region='PT', factors=factors)\n"
         "truth = draw_truth(model, seed=1)\n"
         "r = run_agent(model, lambda n: truth[n], batch_size=3, tau=0.025, seed=1, truth=truth)\n"
         "print(len(model.choices), 'open choices;', r['questions'], 'asked:', r['asked'])\n"
         "print('verdict:', r['verdict'], '| P(wrong) =', round(r['p_flip'], 4), '| agrees with expert:', r['correct'])"),
    md("What each question looks like in the web application, with its plain language help:"),
    code("from branch import webapp\n"
         "from branch.agent import Session\n"
         "s = Session(model, batch_size=3, tau=0.025, seed=1)\n"
         "v = webapp.question_view(s)\n"
         "print(v['text']); print('Why it matters:', v['why']); print('Where to find it:', v['where'])"),

    md("## 3. A small benchmark\n\n"
       "Same comparison, 10 seeds, every strategy. The paper uses 18 cases and 30 seeds per cell."),
    code("strategies = ['decision_flip', 'sobol', 'decision_flip_min', 'entropy', 'margin', 'random']\n"
         "res = []\n"
         "for seed in range(10):\n"
         "    t = draw_truth(model, seed)\n"
         "    for sname in strategies:\n"
         "        out = run_agent(model, lambda n: t[n], strategy=sname, batch_size=3, tau=0.025,\n"
         "                        n_samples=10_000, seed=seed, truth=t)\n"
         "        res.append((sname, seed, out['questions'], out['correct']))\n"
         "df = pd.DataFrame(res, columns=['strategy', 'seed', 'questions', 'correct'])\n"
         "df.groupby('strategy').agg(mean_questions=('questions', 'mean'), correct=('correct', 'mean'))"
         ".sort_values('mean_questions').round(2)"),

    md("## 4. Figures and tables of the paper\n\n"
       "Built from `results/` when the benchmark was rerun, else from the summaries committed in `paper/data/`."),
    code("import subprocess\n"
         "print(subprocess.run([sys.executable, 'experiments/benchmark/paper_assets.py'], "
         "capture_output=True, text=True).stdout)\n"
         "pd.read_csv('paper/data/benchmark_tau0.025.csv').query('batch_size == 3')"
         "[['strategy', 'q_mean', 'wrong_when_certified_pct', 'p_vs_decision_flip']]"),
    code("import matplotlib.pyplot as plt\n"
         "d = pd.read_csv('paper/data/benchmark.csv')\n"
         "fig, ax = plt.subplots(figsize=(5, 3.2))\n"
         "for sname in strategies:\n"
         "    g = d[d.strategy == sname].sort_values('batch_size')\n"
         "    ax.plot(g.batch_size, g.q_mean, marker='o', label=sname)\n"
         "ax.set_xlabel('questions per round'); ax.set_ylabel('mean questions to certify')\n"
         "ax.legend(fontsize=7, frameon=False); plt.show()"),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"}})
os.makedirs(os.path.join(ROOT, "notebooks"), exist_ok=True)
nbf.write(nb, os.path.join(ROOT, "notebooks", "branch_walkthrough.ipynb"))
print("notebooks/branch_walkthrough.ipynb")

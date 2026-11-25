"""Runs the evaluation of the agent and writes its transcripts, its grades and a report.

    python experiments/evals/run_evals.py --demo                 # illustrative factors, no openLCA
    python experiments/evals/run_evals.py                        # the factors read from openLCA
    python experiments/evals/run_evals.py --suite regression --trials 5

Writes results/evals/<tag>/: transcripts.jsonl (every trial, whole), grades.csv (every grader of every
trial), tasks.csv (pass rate, pass@k and pass^k of every task) and report.md.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path[:0] = [_os.path.dirname(_os.path.dirname(_HERE)), _HERE]

import argparse
import csv
import json
import os

from branch.demo_factors import demo_factors
from branch.factors import load_factors

from graders import SESSION_GRADERS, grade
from metrics import pass_at_k, pass_hat_k
from eval_report import write_report
from tasks import capability_tasks, regression_tasks

KS = (1, 3, 5, 10)


def grade_trial(task, transcripts):
    """{grader: (passed, note)} for one trial: the loop's graders on every session, then the task's."""
    out = {}
    for i, s in enumerate(transcripts):
        tag = f"[{i}]" if len(transcripts) > 1 else ""
        out.update({f"{k}{tag}": v for k, v in grade(s, (SESSION_GRADERS if task.loop else []) + task.outcome,
                                                            task.skip).items()})
    out.update({g.__name__: g(transcripts) for g in task.pair})
    return out


def run_task(task, trials, sink):
    """Runs the trials of a task, writes each transcript and grade, returns the rows of grades."""
    rows = []
    for trial in range(trials):
        transcripts = task.run(trial)
        grades = grade_trial(task, transcripts)
        passed = all(ok for ok, _ in grades.values())
        sink.write(json.dumps({"task": task.name, "trial": trial, "passed": passed,
                               "grades": grades, "transcripts": transcripts}, default=float) + "\n")
        rows += [{"task": task.name, "suite": task.suite, "trial": trial, "grader": g, "passed": ok, "note": note}
                 for g, (ok, note) in grades.items()]
    return rows


def task_rows(tasks, grades):
    """One row per task: trials, trials passed, pass@k and pass^k."""
    out = []
    for t in tasks:
        trials = {}
        for g in (g for g in grades if g["task"] == t.name):
            trials[g["trial"]] = trials.get(g["trial"], True) and g["passed"]
        n, c = len(trials), sum(trials.values())
        row = {"task": t.name, "suite": t.suite, "expects": t.expects, "trials": n, "passed": c}
        row.update({f"pass@{k}": pass_at_k(n, c, k) for k in KS if k <= n})
        row.update({f"pass^{k}": pass_hat_k(n, c, k) for k in KS if k <= n})
        out.append(row)
    return out


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", choices=["regression", "capability", "all"], default="all")
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--demo", action="store_true", help="illustrative factors (a check of the harness, not a result)")
    ap.add_argument("--factors", help="factor file (default: BRANCH_FACTORS or the newest in data/factors)")
    ap.add_argument("--tag", default=None)
    a = ap.parse_args(argv)
    factors = demo_factors() if a.demo else load_factors(a.factors)
    tasks = ((regression_tasks(factors) if a.suite in ("regression", "all") else [])
             + (capability_tasks(factors) if a.suite in ("capability", "all") else []))
    out = os.path.join("results", "evals", a.tag or ("demo" if a.demo else "real"))
    os.makedirs(out, exist_ok=True)
    grades = []
    with open(os.path.join(out, "transcripts.jsonl"), "w", encoding="utf-8") as sink:
        for t in tasks:
            grades += run_task(t, a.trials, sink)
            print(f"{t.name}: done", flush=True)
    write_csv(os.path.join(out, "grades.csv"), grades)
    rows = task_rows(tasks, grades)
    write_csv(os.path.join(out, "tasks.csv"), rows)
    write_report(os.path.join(out, "report.md"), rows, grades, factors, a.trials)
    print(f"written to {out}")


if __name__ == "__main__":
    main()

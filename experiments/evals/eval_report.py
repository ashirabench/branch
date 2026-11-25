"""The report of one evaluation run: the regression suite task by task, the capability suite by kind of
expert, and every grader that failed with what it said, so that each failure can be read and judged."""
import datetime
from collections import defaultdict


def _fmt(x):
    return "" if x is None or x != x else f"{x:.3f}"


def _regression(rows, k):
    lines = ["## Regression suite (target: every trial passes)", "",
             f"| Task | What must happen | Passed | pass^{k} |", "|---|---|---|---|"]
    for r in rows:
        if r["suite"] == "regression":
            lines.append(f"| `{r['task']}` | {r['expects']} | {r['passed']}/{r['trials']} | {_fmt(r.get(f'pass^{k}'))} |")
    return lines + [""]


def _capability(rows, k):
    groups = defaultdict(list)
    for r in rows:
        if r["suite"] == "capability":
            groups[r["task"].rsplit("__", 1)[1]].append(r)
    lines = ["## Capability suite (18 comparisons of the paper, by kind of expert)", "",
             f"| Expert | Comparisons | Trials passed | Mean pass@1 | Comparisons with pass^{k} = 1 | Mean pass^{k} |",
             "|---|---|---|---|---|---|"]
    for name, rs in groups.items():
        n, c = sum(r["trials"] for r in rs), sum(r["passed"] for r in rs)
        hat = [r.get(f"pass^{k}", float("nan")) for r in rs]
        lines.append(f"| {name} | {len(rs)} | {c}/{n} | {_fmt(c / n)} | {sum(h == 1.0 for h in hat)} | "
                     f"{_fmt(sum(hat) / len(hat))} |")
    return lines + [""]


def _failures(grades):
    fails = defaultdict(list)
    for g in grades:
        if not g["passed"]:
            fails[g["grader"]].append(f"`{g['task']}` trial {g['trial']}: {g['note']}")
    lines = ["## Failed graders", ""]
    if not fails:
        return lines + ["None.", ""]
    for grader, notes in sorted(fails.items()):
        lines += [f"**{grader}** failed {len(notes)} time(s). First ones:", ""] + [f"- {x}" for x in notes[:5]] + [""]
    return lines


def write_report(path, rows, grades, factors, trials):
    k = max((kk for kk in (1, 3, 5, 10) if kk <= trials), default=1)
    data = ("ILLUSTRATIVE factors (a check of the harness, not a result)" if factors.get("demo")
            else factors.get("citation") or factors.get("path"))
    head = ["# Evaluation of the BRANCH agent", "",
            f"Run on {datetime.date.today().isoformat()}. Unit factors: {data}. Trials per task: {trials}.",
            "Method: experiments/evals/README.md.", ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(head + _regression(rows, k) + _capability(rows, k) + _failures(grades)) + "\n")

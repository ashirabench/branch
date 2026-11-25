"""The evaluation of the agent (experiments/evals/), checked before it is trusted.

A grader that never fails proves nothing. So each grader of the loop is shown a transcript of a
session that keeps the rule and one that breaks it, and must tell them apart; then the harness
runs a few tasks end to end on the illustrative factors.
"""
import copy
import importlib
import os
import sys

import pytest

from branch.demo_factors import demo_factors

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "experiments", "evals"))
graders = importlib.import_module("graders")
tasks = importlib.import_module("tasks")
run_evals = importlib.import_module("run_evals")
metrics = importlib.import_module("metrics")


@pytest.fixture(scope="module")
def good():
    """A real transcript: PET against glass in Portugal, with an expert from the prior."""
    task = next(t for t in tasks.regression_tasks(demo_factors()) if t.name == "public_comparison")
    return task.run(0)[0]


def broken(good, how):
    s = copy.deepcopy(good)
    how(s)
    return s


def _repeat(s):
    s["events"].append(dict(s["events"][0]))


def _unaskable(s):
    s["events"][0]["asked"] = "not_a_choice"


def _late(s):
    s["result"]["trace"].insert(0, {"questions": 0, "p_flip": 0.0, "verdict_a_lower": True, "correct": True})


def _no_reason(s):
    s["result"].update(certified=False, p_flip=0.3)
    s["open_left"], s["stopped_early"] = 2, False


def _bad_rank(s):
    first = s["rounds"][0]
    worst = min(first["open"], key=lambda n: first["scores"][n])
    s["events"][0]["asked"] = worst


def _zero(s):
    s["rounds"][0]["scores"][s["events"][0]["asked"]] = 0.0


def _lie(s):
    s["result"]["certified"] = not s["result"]["certified"]


def _unlabelled(s):
    name = next(iter(s["model"]["sources"]))
    s["model"]["sources"][name] = "my guess"


def _no_notice(s):
    s["report"]["has_iso_notice"] = False


def _skip_lost(s):
    s["events"][0]["answer"] = None


BREAKS = [(graders.no_question_twice, _repeat), (graders.only_open_choices_asked, _unaskable),
          (graders.no_question_after_certificate, _late), (graders.stops_for_a_stated_reason, _no_reason),
          (graders.asks_the_best_ranked, _bad_rank), (graders.no_question_that_cannot_change_the_verdict, _zero),
          (graders.certificate_is_honest, _lie), (graders.every_default_has_a_source, _unlabelled),
          (graders.iso_notice_when_public, _no_notice), (graders.dont_know_keeps_the_prior, _skip_lost)]


@pytest.mark.parametrize("grader,breaker", BREAKS, ids=[g.__name__ for g, _ in BREAKS])
def test_each_grader_passes_the_real_session_and_fails_the_broken_one(good, grader, breaker):
    assert grader(good)[0], grader(good)[1]
    ok, note = grader(broken(good, breaker))
    assert not ok and note


def test_every_grader_of_the_loop_is_checked_here():
    assert {g.__name__ for g in graders.SESSION_GRADERS} - {"value_laden_first"} == {g.__name__ for g, _ in BREAKS}


def test_value_laden_first_fails_when_it_comes_late():
    task = next(t for t in tasks.regression_tasks(demo_factors()) if t.name == "value_laden_choice")
    s = task.run(0)[0]
    assert graders.value_laden_first(s)[0]
    s["events"].append(dict(s["events"][0], round=0))
    assert not graders.value_laden_first(s)[0]


def test_the_outcome_graders_read_the_expert():
    s = {"result": {"certified": True, "verdict_a_lower": True, "verdict": "A < B", "p_flip": 0.0},
         "expert_a_lower": False}
    assert not graders.right_if_certified(s)[0] and not graders.certified_and_right(s)[0]
    s["expert_a_lower"] = True
    assert graders.right_if_certified(s)[0] and graders.certified_and_right(s)[0]


def test_pass_at_k_and_pass_hat_k():
    assert metrics.pass_at_k(10, 10, 3) == 1.0 and metrics.pass_hat_k(10, 10, 3) == 1.0
    assert metrics.pass_hat_k(10, 9, 10) == 0.0 and metrics.pass_at_k(10, 1, 10) == 1.0
    assert metrics.pass_hat_k(4, 2, 2) == pytest.approx(1 / 6)


def test_a_small_run_writes_every_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_evals.main(["--demo", "--suite", "regression", "--trials", "1", "--tag", "t"])
    out = tmp_path / "results" / "evals" / "t"
    for name in ("transcripts.jsonl", "grades.csv", "tasks.csv", "report.md"):
        assert (out / name).stat().st_size > 0
    assert "ILLUSTRATIVE" in (out / "report.md").read_text(encoding="utf-8")

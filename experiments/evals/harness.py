"""One trial of the agent, kept as a transcript: every round of scores, every question and answer, the result.

The terms follow Anthropic's guide to evaluating agents ("Demystifying evals for AI agents", experiments/evals/README.md):
a task is one test with a success criterion, a trial one attempt at it, a transcript the whole record
of the trial, and the outcome the final state. The agent is not changed to be evaluated: the session
is the one the web application runs (branch.agent.Session), and the harness only watches it.
"""
from branch.agent import BATCH, ISO_PUBLIC_NOTICE, TAU, Session
from branch.montecarlo import p_a_lower
from branch.report import markdown_report

N_SAMPLES = 20_000          # the number of draws of the application


def _flip(state):
    p = float(p_a_lower(state.delta))
    return min(p, 1.0 - p)


def _spy(session):
    """Wraps the scoring of the session so that every round's scores are kept; returns the list."""
    rounds, inner = [], session.score_fn

    def scored(state, rng):
        scores = inner(state, rng)
        rounds.append({"asked_before": len(session.asked), "p_flip": _flip(state),
                       "open": sorted(state.open), "scores": {k: float(v) for k, v in scores.items()}})
        return scores
    session.score_fn = scored
    return rounds


def _drive(session, oracle, rounds, stop_after):
    """Runs the loop of the application; stop_after ends the session early, as the button does."""
    events = []
    while (name := session.next_question()) is not None:
        if stop_after is not None and len(session.asked) >= stop_after:
            session.finish_early()
            break
        value = oracle(name)
        events.append({"asked": name, "answer": value, "round": len(rounds) - 1})
        session.answer(name, value)
    return events


def _model_facts(model):
    return {"label_a": model.label_a, "label_b": model.label_b,
            "askable": [c.name for c in model.choices if c.askable],
            "value_laden": [c.name for c in model.choices if c.value_laden],
            "sources": {c.name: c.source for c in model.choices}}


KEPT = ("verdict", "verdict_a_lower", "certified", "p_flip", "questions", "asked", "unknown",
        "correct", "trace", "decided_by", "notices", "tau", "batch_size", "seed")


def record_session(model, oracle, seed, truth=None, public=False, stop_after=None,
                   tau=TAU, batch=BATCH, n_samples=N_SAMPLES):
    """Runs one session as the application does and returns its transcript (a plain dict)."""
    s = Session(model, "decision_flip", batch, n_samples, tau, seed, truth=truth, public_comparison=public)
    rounds = _spy(s)
    events = _drive(s, oracle, rounds, stop_after)
    result = s.result()
    report = markdown_report(result, model, analysis=False)
    return {"model": _model_facts(model), "rounds": rounds, "events": events,
            "result": {k: result[k] for k in KEPT}, "open_left": len(s.state.open),
            "max_questions": s.max_q, "public": public, "stopped_early": stop_after is not None,
            "expert_a_lower": s.expert_a_lower,
            "report": {"says_not_certified": "NOT certified" in report,
                       "has_iso_notice": ISO_PUBLIC_NOTICE in report,
                       "verdict_line": next(x for x in report.splitlines() if x.startswith("**Verdict:**"))}}

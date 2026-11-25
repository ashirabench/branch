"""Graders: code that reads a transcript and says whether one property holds, and why not.

Every grader here is deterministic (Anthropic's guide prefers code based graders where the property
can be checked by code; BRANCH has no language model, so every property can). Each returns
(passed, note). The note says what failed, so a failed trial can be read and judged fair or not.

SESSION_GRADERS hold on every session of every task: they are the rules of the agent's loop (paper,
Section "Methods") and of its report. The tasks add the graders of their own outcome.
"""
import math

from harness import N_SAMPLES


def no_question_twice(s):
    asked = [e["asked"] for e in s["events"]]
    repeated = sorted({n for n in asked if asked.count(n) > 1})
    return not repeated, f"asked twice: {repeated}" if repeated else ""


def only_open_choices_asked(s):
    bad = [e["asked"] for e in s["events"] if e["asked"] not in s["model"]["askable"]]
    return not bad, f"not askable: {bad}" if bad else ""


def value_laden_first(s):
    """Value laden choices stay with the person and come before any scored question."""
    laden = set(s["model"]["value_laden"])
    flags = [e["asked"] in laden for e in s["events"]]
    ok = flags == sorted(flags, reverse=True) and all(e["round"] < 0 for e in s["events"] if e["asked"] in laden)
    return ok, "" if ok else f"order {[e['asked'] for e in s['events']]} with value laden {sorted(laden)}"


def no_question_after_certificate(s):
    """No round is opened once the probability of a wrong verdict is below the certificate."""
    tau = s["result"]["tau"]
    early = [t for t in s["result"]["trace"][:-1] if t["p_flip"] < tau]
    return not early, f"kept asking at p_flip {early[0]['p_flip']:.4f}" if early else ""


def stops_for_a_stated_reason(s):
    """The session ends certified, with nothing left to ask, at the limit, or at the person's request."""
    r = s["result"]
    reasons = {"certified": r["certified"], "nothing left": s["open_left"] == 0,
               "limit": r["questions"] >= s["max_questions"], "person stopped": s["stopped_early"]}
    ok = any(reasons.values())
    return ok, "" if ok else f"stopped with p_flip {r['p_flip']:.4f}, {s['open_left']} open, no reason"


def asks_the_best_ranked(s):
    """In every round, each question asked scores at least as high as every choice left unasked."""
    for i, rnd in enumerate(s["rounds"]):
        asked = [e["asked"] for e in s["events"] if e["round"] == i]
        rest = [rnd["scores"][n] for n in rnd["open"] if n not in asked]
        if asked and rest and min(rnd["scores"][n] for n in asked) < max(rest):
            return False, f"round {i}: asked {asked} below a better unasked choice"
    return True, ""


def no_question_that_cannot_change_the_verdict(s):
    """Every scored question had some power to change the verdict when it was asked."""
    useless = [e["asked"] for e in s["events"]
               if e["round"] >= 0 and s["rounds"][e["round"]]["scores"][e["asked"]] <= 0.0]
    return not useless, f"asked with score 0: {useless}" if useless else ""


def certificate_is_honest(s):
    """The certified flag agrees with the probability, and the report says the same thing."""
    r = s["result"]
    flag_ok = r["certified"] == (r["p_flip"] < r["tau"])
    report_ok = s["report"]["says_not_certified"] == (not r["certified"])
    ok = flag_ok and report_ok and r["verdict"] in s["report"]["verdict_line"]
    return ok, "" if ok else f"certified={r['certified']} p_flip={r['p_flip']:.4f} report={s['report']}"


def every_default_has_a_source(s):
    srcs = s["model"]["sources"]
    bad = [n for n, src in srcs.items() if not src.startswith(("SOURCE", "ASSUMPTION"))]
    missing = sorted(set(srcs) - set(s["result"]["decided_by"]))
    ok = not bad and not missing
    return ok, "" if ok else f"unlabelled: {bad}; not in the report: {missing}"


def dont_know_keeps_the_prior(s):
    skipped = [e["asked"] for e in s["events"] if e["answer"] is None]
    bad = [n for n in skipped if s["result"]["decided_by"].get(n) != "human: don't know (prior kept)"]
    return not bad, f"skipped but not reported as prior kept: {bad}" if bad else ""


def iso_notice_when_public(s):
    has = s["report"]["has_iso_notice"]
    return has == s["public"], "" if has == s["public"] else f"public={s['public']} notice={has}"


SESSION_GRADERS = [no_question_twice, only_open_choices_asked, value_laden_first,
                   no_question_after_certificate, stops_for_a_stated_reason, asks_the_best_ranked,
                   no_question_that_cannot_change_the_verdict, certificate_is_honest,
                   every_default_has_a_source, dont_know_keeps_the_prior, iso_notice_when_public]


# ---------------------------------------------------------------- graders of the outcome, used by tasks

def right_if_certified(s):
    """Outcome: a certified verdict is the verdict of the expert's own world."""
    r = s["result"]
    ok = not r["certified"] or r["verdict_a_lower"] == s["expert_a_lower"]
    return ok, "" if ok else f"certified {r['verdict']} but the expert's world says the opposite"


def certified_and_right(s):
    """Outcome: the verdict is certified and it is the expert's."""
    r = s["result"]
    ok = r["certified"] and r["verdict_a_lower"] == s["expert_a_lower"]
    return ok, "" if ok else f"certified={r['certified']} verdict={r['verdict']} p_flip={r['p_flip']:.4f}"


def asked_nothing(s):
    q = s["result"]["questions"]
    return q == 0, "" if q == 0 else f"asked {q}: {s['result']['asked']}"


def asked_something(s):
    q = s["result"]["questions"]
    return q > 0, "" if q else f"certified with no question at p_flip {s['result']['p_flip']:.4f}"


def not_certified(s):
    c = s["result"]["certified"]
    return not c, "" if not c else f"certified at p_flip {s['result']['p_flip']:.4f}"


def right_verdict(s):
    """Outcome: the agent ends on the verdict of the expert's world, certified or not."""
    r = s["result"]
    ok = r["verdict_a_lower"] == s["expert_a_lower"]
    return ok, "" if ok else f"ended on {r['verdict']} (p_flip {r['p_flip']:.4f}), the expert's world says the opposite"


def at_most_one_question(s):
    q = s["result"]["questions"]
    return q <= 1, "" if q <= 1 else f"asked {q} after the person stopped"


def value_laden_all_asked(s):
    missing = sorted(set(s["model"]["value_laden"]) - set(s["result"]["asked"]))
    return not missing, f"value laden never asked: {missing}" if missing else ""


def answers_read_as_meant(t):
    bad = [(n, raw, want, got) for n, raw, want, got in t["answers"]
           if not (got == want or (isinstance(want, float) and isinstance(got, float) and math.isclose(got, want)))]
    return not bad, f"read wrongly: {bad}" if bad else ""


# ---------------------------------------------------------------- graders of two transcripts of one task

def _winner(s):
    m, r = s["model"], s["result"]
    return m["label_a"] if r["verdict_a_lower"] else m["label_b"]


def swap_keeps_the_winner(pair):
    """A against B and B against A, the same expert. The two sessions draw their worlds in another
    order, so the same product must win and both must end certified or both not; the probabilities
    are compared only when the same questions were asked, within five standard errors of a difference
    of two Monte Carlo estimates (after different questions they are different probabilities)."""
    r1, r2 = (s["result"] for s in pair)
    p1, p2, tau = r1["p_flip"], r2["p_flip"], r1["tau"]
    tol = 5 * math.sqrt(2 * max((p1 + p2) / 2, 1 / N_SAMPLES) / N_SAMPLES)
    near_tau = abs(p1 - tau) <= tol or abs(p2 - tau) <= tol
    same_p = sorted(r1["asked"]) != sorted(r2["asked"]) or abs(p1 - p2) <= tol
    ok = _winner(pair[0]) == _winner(pair[1]) and (r1["certified"] == r2["certified"] or near_tau) and same_p
    return ok, "" if ok else (f"winners {_winner(pair[0])} / {_winner(pair[1])}, p_flip {p1:.4f} / {p2:.4f}, "
                              f"certified {r1['certified']} / {r2['certified']}")


def scale_changes_nothing(pair):
    """Every unit factor times ten scales both impacts: the draws are the same, so everything must be."""
    r1, r2 = (s["result"] for s in pair)
    keys = ("asked", "verdict_a_lower", "certified")
    ok = all(r1[k] == r2[k] for k in keys) and math.isclose(r1["p_flip"], r2["p_flip"], abs_tol=1e-12)
    return ok, "" if ok else f"{[(k, r1[k], r2[k]) for k in keys + ('p_flip',) if r1[k] != r2[k]]}"


def grade(session, graders, skip=()):
    """{grader name: (passed, note)} for one session."""
    return {g.__name__: g(session) for g in graders if g.__name__ not in skip}

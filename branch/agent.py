"""BDI control loop (Step 6), Wooldridge style deliberation.

Beliefs     montecarlo.State: distributions over open choices, shared samples.
Desire      a verdict on sign(I_A - I_B) whose probability of being wrong is
            below tau, with as few human questions as possible.
Intentions  compute  propagate beliefs (vectorised Monte Carlo)
            ask      value laden choices first (they always stay with the
                     human), then the batch_size best questions by strategy
            certify  stop when P(verdict wrong) < tau or nothing is left
Reconsider  the ranking is recomputed after every round of answers.

The human may answer "I don't know" (oracle returns None): the choice keeps
its prior distribution and is not asked again.
"""
import time
from typing import Optional

import numpy as np

from .backend import sync, to_numpy
from .lca_model import Model
from .montecarlo import State, p_a_lower
from .query import STRATEGIES

# The setting of the application (paper, Section "Experiments"): the certificate and the questions per round.
TAU = 0.025
BATCH = 3

ISO_PUBLIC_NOTICE = (
    "This comparison will be disclosed to the public. ISO 14044 requires a critical "
    "review by a panel of independent interested parties for comparative assertions "
    "disclosed to the public. BRANCH follows ISO 14040 and ISO 14044 and prepares the "
    "study for that review, but it does not replace the panel of reviewers.")


def verdict_label(a_lower: bool, model: Model) -> str:
    return f"{model.label_a} < {model.label_b}" if a_lower else f"{model.label_b} < {model.label_a}"


class Session:
    """One BRANCH session, one question at a time (for the web app).

        s = Session(model)
        while (name := s.next_question()) is not None:
            s.answer(name, value)        # value None = "I don't know"
        result = s.result()

    Same deliberation as run_agent: value laden choices first, then rounds of
    batch_size questions ranked by the strategy, reconsidered after every
    round, until the verdict is certified or nothing is left to ask.
    """

    def __init__(self, model, strategy="decision_flip", batch_size=1, n_samples=20_000,
                 tau=0.05, seed=0, max_questions=None, truth=None,
                 value_laden_first=True, public_comparison=False, reference_a_lower=None):
        self.model, self.strategy, self.batch_size = model, strategy, batch_size
        self.n_samples, self.tau, self.seed = n_samples, tau, seed
        self.public_comparison = public_comparison
        self.score_fn = STRATEGIES[strategy]
        self.rng = np.random.default_rng(np.random.SeedSequence([seed, 7]))
        self.state = State(model, model.sample(n_samples, seed))
        self.max_q = max_questions if max_questions is not None else sum(c.askable for c in model.choices)
        self.expert_a_lower = None if truth is None else model.delta_at(truth) < 0
        if reference_a_lower is not None:      # verdict of another model at the expert's world (ablations)
            self.expert_a_lower = bool(reference_a_lower)
        self.trace, self.latencies, self.asked = [], [], []
        self.pending = ([n for n in self.state.open if model.by_name[n].value_laden]
                        if value_laden_first else [])
        self.done = False

    def p_a_lower(self) -> float:
        return float(p_a_lower(self.state.delta))

    def _record(self):
        """Append the current belief to the trace; returns the flip probability."""
        pl = self.p_a_lower()
        pf = min(pl, 1.0 - pl)
        self.trace.append({"questions": len(self.asked), "p_flip": pf, "verdict_a_lower": pl >= 0.5,
                           "correct": None if self.expert_a_lower is None
                           else bool((pl >= 0.5) == self.expert_a_lower)})
        return pf

    def next_question(self) -> Optional[str]:
        """Name of the next choice to ask, or None when the session is over."""
        if self.pending:
            return self.pending[0]
        if self.done:
            return None
        pf = self._record()
        if pf < self.tau or not self.state.open or len(self.asked) >= self.max_q:
            self.done = True
            return None
        t0 = time.perf_counter()
        scores = self.score_fn(self.state, self.rng)
        sync(self.model.xp)
        self.latencies.append(time.perf_counter() - t0)
        k = min(self.batch_size, self.max_q - len(self.asked), len(self.state.open))
        self.pending = sorted(self.state.open, key=lambda n: scores[n], reverse=True)[:k]
        return self.pending[0]

    def answer(self, name: str, value: Optional[float]) -> None:
        """Engine number for the answer, or None for "I don't know"."""
        if name not in self.pending:
            raise ValueError(f"{name} is not the question being asked")
        self.pending.remove(name)
        self.asked.append(name)
        if value is None:
            self.state.mark_unknown(name)
        else:
            self.state.fix(name, value)

    def finish_early(self) -> None:
        """Stop asking now, at the person's request.

        Every open choice keeps its prior, the questions already answered keep
        their answers, and result() says whether the verdict is certified at
        this point: usually it is not, and the report says so instead of
        pretending.
        """
        self.pending = []
        self._record()
        self.done = True

    def result(self) -> dict:
        if not self.done:
            raise RuntimeError("the session is not over: call next_question until it returns None")
        model, state, asked = self.model, self.state, self.asked
        final = self.trace[-1]
        a_terms = [i for i, t in enumerate(model.terms) if t.sign > 0]
        b_terms = [i for i, t in enumerate(model.terms) if t.sign < 0]
        ia = to_numpy(sum(state.contrib[i] for i in a_terms)) if a_terms else np.zeros(1)
        ib = -to_numpy(sum(state.contrib[i] for i in b_terms)) if b_terms else np.zeros(1)
        impacts = {model.label_a: (float(ia.mean()), *map(float, np.percentile(ia, [5, 95]))),
                   model.label_b: (float(ib.mean()), *map(float, np.percentile(ib, [5, 95])))}
        decided_by = {}
        for c in model.choices:
            if not c.askable:
                decided_by[c.name] = f"nobody: uncertainty of the database ({c.source})"
            elif c.name in state.unknown:
                decided_by[c.name] = "human: don't know (prior kept)"
            elif c.name in asked:
                decided_by[c.name] = "human"
            elif c.name in state.fixed:
                decided_by[c.name] = "given before the session"
            else:
                decided_by[c.name] = f"prior ({c.source})"
        lat = self.latencies
        return {
            "strategy": self.strategy, "batch_size": self.batch_size, "n_samples": self.n_samples,
            "seed": self.seed, "tau": self.tau,
            "questions": len(asked), "asked": list(asked), "unknown": list(state.unknown),
            "certified": final["p_flip"] < self.tau, "p_flip": final["p_flip"],
            "verdict": verdict_label(final["verdict_a_lower"], model),
            "verdict_a_lower": final["verdict_a_lower"],
            "correct": final["correct"],
            "latency_mean_s": float(np.mean(lat)) if lat else 0.0,
            "latency_max_s": float(np.max(lat)) if lat else 0.0,
            "trace": self.trace, "fixed": dict(state.fixed), "decided_by": decided_by,
            "impacts": impacts,
            "notices": [ISO_PUBLIC_NOTICE] if self.public_comparison else [],
        }


def run_agent(model, oracle, strategy="decision_flip", batch_size=1, n_samples=20_000,
              tau=0.05, seed=0, max_questions=None, truth=None,
              value_laden_first=True, public_comparison=False, reference_a_lower=None):
    """Run one BRANCH session with an oracle.

    oracle(name) -> engine number, or None for "I don't know".
    truth        full expert world {name: engine number}, for evaluation only.
    reference_a_lower  when the expert's world is judged by another model than the agent's
                 (knowledge ablations): whether A is lower there. Default: the agent's own model.
    """
    s = Session(model, strategy, batch_size, n_samples, tau, seed, max_questions, truth,
                value_laden_first, public_comparison, reference_a_lower)
    while (name := s.next_question()) is not None:
        s.answer(name, oracle(name))
    return s.result()


def ask_human_cli(model, inp=input, out=print):
    """Terminal oracle for the human study.

    Empty answer or '?' = I don't know. Invalid input is asked again. A value
    outside the support of the prior must be confirmed, because it usually
    means a typo (for example 0 refill trips).
    """
    def oracle(name):
        c = model.by_name[name]
        out(f"\n{c.question or name}   [source of the default: {c.source}]")
        while True:
            if c.kind == "categorical":
                for i, (label, p) in enumerate(zip(c.labels, c.probs)):
                    out(f"  [{i}] {label}   (prior {p:.0%})")
                raw = inp("Answer number (Enter or ? if you don't know): ").strip()
                if raw in ("", "?"):
                    return None
                if raw.isdigit() and int(raw) < len(c.labels):
                    return float(int(raw))
                out("Please type one of the numbers shown.")
                continue
            lo, hi = c._frozen().ppf([0.05, 0.95])
            raw = inp(f"Value, typical range {lo:.3g} to {hi:.3g} (Enter or ? if you don't know): ").strip()
            if raw in ("", "?"):
                return None
            try:
                v = float(raw.replace(",", "."))
            except ValueError:
                out("Please type a number.")
                continue
            a, b = c._frozen().support()
            if not (a <= v <= b):
                ok = inp(f"{v:g} is outside the possible range ({a:g} to {b:g}) of the default. "
                         "Keep it anyway? [y/N] ").strip().lower().startswith(("y", "s"))
                if not ok:
                    continue
            return v
    return oracle


def ask_public_comparison() -> bool:
    raw = input("Will this comparison be disclosed to the public (for example in marketing)? [y/N] ")
    public = raw.strip().lower().startswith(("y", "s"))
    if public:
        print("\nNOTE: " + ISO_PUBLIC_NOTICE)
    return public

# Evaluation of the agent

The benchmark of the paper measures how many questions BRANCH asks and how often a certified verdict is wrong. This folder evaluates the agent as an agent: what it does in each session, trial after trial, graded by code, with the whole record of every session kept for reading. It follows the method of Anthropic's guide *Demystifying evals for AI agents* (see References).

```bash
python experiments/evals/run_evals.py              # the factors read from openLCA (data/factors)
python experiments/evals/run_evals.py --demo       # illustrative factors: a check of the harness, not a result
python experiments/evals/run_evals.py --suite regression --trials 5
```

About two minutes for both suites with ten trials. The results go to `results/evals/<tag>/`.

## Terms

| Term of the guide | Here |
|---|---|
| Task | One test with its success criterion: a comparison, a kind of simulated expert, and what must happen (`tasks.py`) |
| Trial | One attempt at a task. Trial *t* uses the seed *t* for the Monte Carlo draws of the agent and a new expert, except in the tasks with one fixed expert |
| Harness | `harness.py` runs the session of the web application (`branch.agent.Session`) unchanged and only watches it |
| Transcript | Every round of scores, every question with its answer, the result and what the report says (`transcripts.jsonl`) |
| Outcome | The final state: the verdict, whether it is certified, and whether it is the verdict of the expert's own world |
| Grader | A function that reads a transcript and returns passed or failed with the reason (`graders.py`). All are code: BRANCH has no language model, so no judgement needs one |

## The two suites

**Regression.** Rules that must hold on every trial; the target is 100%, and a failure is a defect.

| Task | What must happen | The opposite case |
|---|---|---|
| `clear_gap_*` | PET against the same bottle three times heavier: certify and ask nothing | `near_tie_*` |
| `near_tie_*` | PET against an identical bottle: ask before any verdict | `clear_gap_*` |
| `near_tie_all_unknown_*` | The same tie when every answer is "I don't know": do not certify | `clear_gap_*` |
| `identical_products` | The same product twice with the same answers: say they are equal, certify nothing | `clear_gap_*` |
| `finish_after_one_question` | The person stops after one answer: the report says honestly whether the verdict is certified | |
| `public_comparison` | A comparison for the public: the report carries the ISO 14044 notice | every other task, which must not |
| `value_laden_choice` | A value laden choice is always asked, and first (only the toy model of the README has one, so this task skips the check of sources, which are placeholders there) | |
| `swap_products` | A against B and B against A, same expert: the same product wins | |
| `scale_all_factors` | Every unit factor times ten: the same questions, probability and verdict | |
| `answers_typed_in_the_form` | Numbers, commas, percent, blanks and nonsense are read as meant, or refused with a message; a real value beyond the default's range is taken | |

Every session of every task is also graded by the rules of the loop (`SESSION_GRADERS`): no question twice; only open choices asked; value laden choices first; no round opened after the certificate is reached; the session stops for the reason it states, and the state agrees with it (certified, nothing left, no question left that can change the verdict, the limit, or the person stopped); each question asked is among the best ranked of its round; no question asked whose score says it cannot change the verdict; the certified flag and the report agree with the probability; every default is labelled SOURCE or ASSUMPTION and appears in the report; a skipped question keeps its prior; the ISO notice appears exactly when the comparison is public.

**Capability.** The 18 comparisons of the paper (four beverage packages, Portugal, Germany and Brazil) with three kinds of simulated expert:

| Expert | Each trial | Passes when |
|---|---|---|
| `prior` | a new expert drawn from the priors | a certified verdict is the expert's |
| `adverse` | a new expert whose world is chosen against the agent | a certified verdict is the expert's |
| `fixed` | the same expert, new Monte Carlo draws of the agent | the agent ends on the expert's verdict |

## pass@k and pass^k

For each task, from *n* trials of which *c* passed: pass@k is the chance that at least one of *k* trials passes, pass^k the chance that all *k* pass (`metrics.py`). A person relies on BRANCH in every session, so pass^k is the measure that matters; the report gives both.

## Does the rule on useless questions change the paper?

`check_useless_questions.py` runs the settings of the paper with the agent's strategy and counts the sessions in which a best ranked question had a score of zero or below. Only those sessions differ from the code before 25 November 2026; every other one is the same draw for draw.

## The graders are checked too

A grader that never fails proves nothing. `tests/test_evals.py` shows each grader of the loop a real transcript and the same transcript broken in the way the grader is meant to catch, and fails if the grader does not tell them apart.

## Reading the transcripts

The guide's last advice is to read the transcripts before trusting a score. `report.md` lists, for every grader that failed, the first trials with the reason; each line of `transcripts.jsonl` holds the whole trial, with the scores of every round.

## References

Anthropic. n.d. "Demystifying Evals for AI Agents." Anthropic Research. Accessed November 25, 2026. https://www.anthropic.com/research/demystifying-evals-for-ai-agents.

Chen, Mark, Jerry Tworek, Heewoo Jun, et al. 2021. "Evaluating Large Language Models Trained on Code." arXiv:2107.03374.

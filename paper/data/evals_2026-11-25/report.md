# Evaluation of the BRANCH agent

Run on 2026-11-25. Unit factors: Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026. Trials per task: 10.
Method: experiments/evals/README.md.

## Regression suite (target: every trial passes)

| Task | What must happen | Passed | pass^10 |
|---|---|---|---|
| `clear_gap_PT` | PET against the same bottle three times heavier: certify, ask nothing | 10/10 | 1.000 |
| `near_tie_PT` | PET against an identical PET bottle: ask before any verdict | 10/10 | 1.000 |
| `near_tie_all_unknown_PT` | the same tie, the person answers 'I don't know' to everything: do not certify | 10/10 | 1.000 |
| `clear_gap_DE` | PET against the same bottle three times heavier: certify, ask nothing | 10/10 | 1.000 |
| `near_tie_DE` | PET against an identical PET bottle: ask before any verdict | 10/10 | 1.000 |
| `near_tie_all_unknown_DE` | the same tie, the person answers 'I don't know' to everything: do not certify | 10/10 | 1.000 |
| `clear_gap_BR` | PET against the same bottle three times heavier: certify, ask nothing | 10/10 | 1.000 |
| `near_tie_BR` | PET against an identical PET bottle: ask before any verdict | 10/10 | 1.000 |
| `near_tie_all_unknown_BR` | the same tie, the person answers 'I don't know' to everything: do not certify | 10/10 | 1.000 |
| `identical_products` | the same product twice with the same answers: say they are equal, certify nothing | 10/10 | 1.000 |
| `finish_after_one_question` | the person stops after one answer: say honestly whether it is certified | 10/10 | 1.000 |
| `public_comparison` | a comparison for the public: show the ISO 14044 notice | 10/10 | 1.000 |
| `value_laden_choice` | a value laden choice: always ask it, and first | 10/10 | 1.000 |
| `swap_products` | A against B and B against A: the same product wins | 10/10 | 1.000 |
| `scale_all_factors` | every unit factor times ten: the same questions and verdict | 10/10 | 1.000 |
| `answers_typed_in_the_form` | numbers, commas, percent, blanks and nonsense are read as meant or refused with a message | 10/10 | 1.000 |

## Capability suite (18 comparisons of the paper, by kind of expert)

| Expert | Comparisons | Trials passed | Mean pass@1 | Comparisons with pass^10 = 1 | Mean pass^10 |
|---|---|---|---|---|---|
| prior | 18 | 177/180 | 0.983 | 15 | 0.833 |
| adverse | 18 | 169/180 | 0.939 | 11 | 0.611 |
| fixed | 18 | 180/180 | 1.000 | 18 | 1.000 |

## Failed graders

**right_if_certified** failed 14 time(s). First ones:

- `pet_bottle_1l__aluminium_can_330ml__PT__prior` trial 0: certified PET single use < Aluminium can 330 ml but the expert's world says the opposite
- `pet_bottle_1l__aluminium_can_330ml__BR__prior` trial 0: certified PET single use < Aluminium can 330 ml but the expert's world says the opposite
- `glass_refillable_1l__aluminium_can_330ml__DE__prior` trial 4: certified Refillable glass < Aluminium can 330 ml but the expert's world says the opposite
- `pet_bottle_1l__aluminium_can_330ml__PT__adverse` trial 1: certified PET single use < Aluminium can 330 ml but the expert's world says the opposite
- `pet_bottle_1l__aluminium_can_330ml__PT__adverse` trial 5: certified PET single use < Aluminium can 330 ml but the expert's world says the opposite


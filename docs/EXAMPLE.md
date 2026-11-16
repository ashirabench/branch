# One comparison, from a bill of materials to a model in openLCA

A bottler in Portugal wants to know which has the lower climate impact per litre delivered: a single-use PET bottle or a refillable glass bottle. The numbers below are the output of BRANCH 0.2.0 with factors read from BAFU:2026 (EF 3.1) on 16 November 2026.

## 1. What the person gives

Two bills of materials and a region. The two products of this example ship with the repository ([`data/benchmark/pet_bottle_1l.json`](../data/benchmark/pet_bottle_1l.json) and [`glass_refillable_1l.json`](../data/benchmark/glass_refillable_1l.json)); each states the parts and their materials, and little else.

## 2. What BRANCH fills in

Everything the person did not state becomes a choice with a distribution and a label. This comparison has 14 open choices. Six of them:

| Choice | What BRANCH assumes until told otherwise | Label |
|---|---|---|
| Distance from the bottling plant to the shops | 50 to 400 km | assumption |
| Mass of the PET bottle | 25 to 42 g, most likely 32 | assumption |
| Heat to wash one glass bottle | 0.05 to 0.5 MJ | assumption |
| Times a glass bottle is filled | 5 to 40, most likely 15 | assumption |
| Recycled content of the PET | around 27% | source for the centre |
| Mass of the glass bottle | 450 to 625 g, most likely 480 | source for the centre |

With these beliefs alone the comparison is open: refillable glass has the lower impact in 57% of the 20,000 worlds BRANCH draws, so a verdict would be wrong with probability 43%.

## 3. What BRANCH asks

It ranks the 14 choices by how much their answer can change which product wins, and asks the first three:

1. How far does the truck travel from the bottling plant to the shops, one way? **100 km**
2. How many grams does the PET bottle weigh? **34 g**
3. How much heat is used to wash one glass bottle? **0.15 MJ**

After these three answers the probability of a wrong verdict falls from 43% to 0.8%, below the 2.5% that BRANCH requires, and it stops. It never asks about the other 11 choices: they stay as distributions, and the report lists each with its source or with the word assumption.

| | kg CO2 eq per litre | 90% interval |
|---|---|---|
| PET, single use | 0.113 | 0.096 to 0.129 |
| Refillable glass | 0.067 | 0.052 to 0.091 |

The same three questions are not the ones a different comparison would get. With the answers "I don't know" to everything, BRANCH would say that it cannot certify a verdict, and why.

To repeat it in the terminal (it asks the questions and you type the answers):

```bash
python examples/demo_cli.py --region PT
```

or in the browser with `python app.py`.

## 4. What goes back to openLCA

With openLCA open on the same database and its IPC server started, add `--push` to the command above, or press **Send to openLCA** in the application after confirming that the database is a copy or has a backup. In the folder **BRANCH** of the database you then find, for each product:

- a **process** with one exchange per dataset, each linked to the process of the database it came from;
- one **input parameter** per continuous choice, with the question, the value, who decided it (the person or BRANCH's default) and its source. The three answered parameters have no uncertainty; the open ones carry the distribution BRANCH used;
- **formulas** as the amounts of the exchanges. The glass of the refillable bottle, for example, is `(glass_bottle_mass_g / 1000) / glass_trips`, so changing the number of trips in openLCA changes the amount of glass;
- a **product system**, which openLCA calculates. BRANCH compares openLCA's result with its own and shows the difference; over the 36 products of the benchmark the largest relative difference is a few billionths.

Because the choices are parameters with uncertainty, openLCA's own Monte Carlo simulation runs on the model. Sending the same comparison again updates these objects; it does not add copies.

Two limits: openLCA has no beta distribution, which BRANCH uses for recycling rates, so those parameters have no uncertainty in openLCA and say so; and a choice between options (which dataset, which disposal route) is not a number, so it is fixed at the option of the model and listed in the description of the process.

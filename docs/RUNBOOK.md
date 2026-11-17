# Operating BRANCH: every task, what you should see, and what goes wrong

One section per task. Each gives the command, the result that means it worked, and the failures that have happened, with their cause and their fix. Commands run in a terminal, from the top of the repository, with the environment active (`source .venv/bin/activate`), unless the section says otherwise.

| I want to | Section |
|---|---|
| Install BRANCH and know it works | [1](#1-install-and-test) |
| Show the application without openLCA | [2](#2-show-the-application-without-openlca) |
| Let BRANCH talk to openLCA | [3](#3-start-the-ipc-server-of-openlca) |
| Read the unit factors from my database | [4](#4-read-the-unit-factors-once-per-database) |
| Use the application with real factors and send a model to openLCA | [5](#5-use-the-application-with-real-factors) |
| Check BRANCH against openLCA | [6](#6-check-branch-against-openlca) |
| Remove what BRANCH wrote into a database | [7](#7-remove-what-branch-wrote-into-a-database) |
| Repeat what the paper says about the database | [8](#8-read-the-database-file-directly) |
| Repeat the experiments, rebuild the paper | [9](#9-repeat-the-experiments-and-rebuild-the-paper) |
| Publish a version | [10](#10-publish-a-version) |
| Bring a computer up to date | [11](#11-bring-a-computer-up-to-date) |

## 1. Install and test

```bash
git clone https://github.com/ashirabench/branch.git && cd branch
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
pytest -q
```

**It worked when** the last line reads `N passed` with no `failed`. One or two tests are skipped when no factor file is present; that is expected.

| What you see | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` during the tests | A test needs a package that the installed extras do not bring | Install with `".[all]"`. If it happens only on GitHub, add the package to the extra that `.github/workflows/tests.yml` installs |
| A test passes here and fails on GitHub or on another computer, about a file that is missing | The file exists here but git ignores it | `git check-ignore -v <file>` names the rule in `.gitignore`. Add an exception (a line that starts with `!`) and commit the file |
| Tests about checksums of data files fail on Windows only | Git converted line endings of a data file | `.gitattributes` must list the kind of file with `-text` (today `*.csv` and `*.json`) |

## 2. Show the application without openLCA

```bash
BRANCH_DEMO=1 python app.py
```

**It worked when** the terminal prints `BRANCH for openLCA is running at http://127.0.0.1:<port>` and the browser opens that page. The port is 7860 when it is free, otherwise the next free one. The numbers of this mode are illustrative: do not quote them.

| What you see | Cause | Fix |
|---|---|---|
| `No impact factors configured on this server` | Neither `BRANCH_DEMO=1` nor a factor file | Use the command above, or do section 4 first |
| The page does not open by itself | The browser was not started | Copy the address printed in the terminal into the browser |

## 3. Start the IPC server of openLCA

This happens **in openLCA**, not in the terminal.

1. Open openLCA 2 and open the database (double click on it; its name turns bold).
2. Menu **Tools**, **Developer tools**, **IPC Server**. Leave the port at 8080 and press the green start button.
3. **Leave that small window open.** Closing it stops the server.

**It worked when** the commands of sections 4 to 7 answer instead of refusing the connection.

| What you see | Cause | Fix |
|---|---|---|
| `Connection refused`, or `openLCA is not answering` | The server is not running, or its window was closed | Do the three steps again |
| The command answers but finds no process | No database is open, or another one is | Open the right database, then start the server again |

## 4. Read the unit factors, once per database

Needs section 3.

```bash
python experiments/openlca/extract_factors.py --method "EF 3.1"
```

**It worked when** the last line reads `saved data/factors/<database>_<method>.json: N factors, 0 unresolved`. It takes about ten minutes. The file stays on your computer: git ignores `data/factors/`, because the licence of the database does not allow publishing its values.

| What you see | Cause | Fix |
|---|---|---|
| `NOT READ: <key>: no process of the database has this exact name` | The database names that dataset differently (another version, another database) | `python experiments/openlca/extract_factors.py --find "<part of the name>"` lists candidates. The names BRANCH looks for are in `branch/olca_extract.py` |
| `? <key>: N candidates` | Several processes match | Choose one and write its exact name in `branch/olca_extract.py` |
| A new product or region needs factors the file lacks | The file was extracted before | Add `--update`: it reads only what is missing |

## 5. Use the application with real factors

```bash
python app.py
```

It uses the newest file in `data/factors/`. To send the model of a comparison to openLCA (needs section 3): press **Send to openLCA** on the page, after ticking that the database is a copy or has a backup. In openLCA the objects appear in the folder **BRANCH** of processes, flows and product systems. If the navigation does not show them, close the database and open it again (right click on it). [`docs/EXAMPLE.md`](EXAMPLE.md) shows what arrives.

Sending the same comparison again updates the objects; it does not add copies.

## 6. Check BRANCH against openLCA

Needs sections 3 and 4.

```bash
python experiments/openlca/validate_openlca.py                        # the 36 products of the 18 cases
python experiments/openlca/validate_openlca.py --all-grids --pairs 1  # 166 products in 83 regions
python experiments/openlca/validate_probability.py                    # the probability, on 200 random worlds
```

**It worked when** the first two end with `N products checked, largest relative difference X` and X is of the order of 1e-8 or smaller (the paper reports 3.8e-9 and 2.0e-8). The third prints the largest relative difference over the worlds, in how many worlds the two agree on the winner, and `inside` or `OUTSIDE` for BRANCH's probability against the exact interval; the criteria were fixed beforehand in point 17 of [`experiments/record/PLAN_2026-11-15.md`](../experiments/record/PLAN_2026-11-15.md).

These scripts remove what they create. With `validate_openlca.py`, add `--keep` to look at the objects in openLCA.

| What you see | Cause | Fix |
|---|---|---|
| `N comparison(s) could not be checked` | openLCA refused some request; the table marks the rows with `error` | Read the message in the row. Usually a dataset of the factor file is not in the open database: the factor file and the open database must be the same |
| A large relative difference | BRANCH and the database disagree: this is a finding, not noise | Do not publish. Open the dataset in openLCA and compare its reference unit and amount with `python experiments/openlca/audit_factors.py` |

## 7. Remove what BRANCH wrote into a database

Needs section 3.

```bash
python experiments/openlca/clean_branch_objects.py            # only lists
python experiments/openlca/clean_branch_objects.py --delete   # asks for "yes", then deletes
```

**It worked when** the list shows three counts (product systems, processes, flows whose name starts with `BRANCH | ` or `BRANCH check | `), and after `--delete` the line reads `Deleted N objects; 0 remain`. Nothing else in the database is touched.

## 8. Read the database file directly

No openLCA needed, and openLCA may stay open: the script reads a copy.

```bash
pip install -e ".[database]"
python experiments/openlca/read_database.py --db ~/openLCA-data-1.4/databases/<name> counts
python experiments/openlca/read_database.py --db ~/openLCA-data-1.4/databases/<name> signs
```

**It worked when** each number is followed by `as in the paper` (for BAFU:2026 v1.1: 11,951 processes, 420,087 exchanges, 227,083 with a pedigree entry, 266,822 lognormal, 14,167 waste outputs with the wrong sign). `THE PAPER SAYS ...` means the database is another version.

| What you see | Cause | Fix |
|---|---|---|
| `The Derby jars were not found` | Not a Mac, or openLCA is not in `/Applications` | Pass `--libs <openLCA folder>/plugins/olca-app_<version>/libs` |
| `No space left on device` | The copy needs as much free disk as the database (1 to 3 GB) | Free the space; the script removes its copy when it ends, also after an error |

## 9. Repeat the experiments and rebuild the paper

```bash
bash reproduce.sh paper      # figures, tables and paper/main.pdf from the committed summaries; no openLCA
QUICK=1 bash reproduce.sh    # the whole pipeline with 3 seeds, to see that it runs
bash reproduce.sh            # everything; the experiments take minutes to hours, by the number of cores
```

**It worked when** the stage `paper` prints `paper/main.pdf: 15 pages` and the script ends with `== done`. The stage `paper` needs LaTeX (`latexmk`).

An experiment is never run before its plan is written and committed in [`experiments/record/`](../experiments/record/): what is measured, with which seeds, and what result would count as a failure. Which file supports which sentence of the paper is in [`docs/CLAIMS.md`](CLAIMS.md).

## 10. Publish a version

By hand, write one line in `CHANGELOG.md` that contains `Release v<version>` and name the version in `packaging/release_notes.md`; commit and push both. Then:

```bash
bash release.sh 0.2.2 --dry    # every check and the tests, nothing published
bash release.sh 0.2.2          # the same checks, then version, commit, tag, push, and the wait for the installers
```

**It worked when** the last line reads `PUBLISHED: v0.2.2, three installers, <address>`. Until every check has passed, nothing reaches GitHub; each refusal starts with `NOT PUBLISHED:` and says why.

| What you see | Cause | Fix |
|---|---|---|
| `main here differs from main on GitHub` | Something was committed on the website, or not pushed | `git pull`, or `git push origin main`, then run again |
| `tests fail in a fresh copy` although `pytest` passes here | A file the tests need is not in git (see section 1) | `git status --ignored` shows ignored files; commit what the tests need |
| `commits with another author or a visible e-mail address` | A commit was made with another identity | Make the commit again with the author of the others, before publishing |
| After the push, an installer is missing | A job on GitHub failed or was cancelled in the queue | On the Actions page open the run of the tag, **Re-run failed jobs**; then `bash release.sh check 0.2.2` |
| A warning about a version of Node on the Actions page | A notice from GitHub about its own actions | None needed; it does not change the installers |

## 11. Bring a computer up to date

```bash
cd ~/branch && git pull --ff-only && source .venv/bin/activate && pip install -q -e ".[all]" && pytest -q
```

| What you see | Cause | Fix |
|---|---|---|
| `Not possible to fast-forward` | This computer has commits that GitHub does not have | `git status` and `git log origin/main..HEAD` show them; push them or decide what to keep before pulling |
| `Unable to create '.git/...lock': File exists` | A git command was interrupted | Make sure no other git command is running, then delete that one lock file |

#!/usr/bin/env bash
# Master script: everything in the paper from a clean clone.
#
#   bash reproduce.sh            # all stages below, in order
#   bash reproduce.sh paper      # only rebuild figures, tables and the PDF from the committed summaries
#   QUICK=1 bash reproduce.sh    # 3 seeds and batch 1 only, to check the pipeline in minutes
#
# Stages (run one or several by name: install data test experiments figures paper):
#   1. install      Python packages (into the active conda env or venv, else a new .venv)
#   2. data         unit impact factors from a local openLCA (BAFU:2026 + EF 3.1); skipped when
#                   data/factors/*.json already exists. Without openLCA, the next stages use the
#                   benchmark summaries committed in paper/data/.
#   3. test         the unit tests (engine, lemma, builder, connector, web app)
#   4. experiments  the full benchmark: 18 cases x 30 seeds x batch 1 to 5, priors and tails,
#                   certificate 5% and 2.5%, the run with new seeds, then three other impact categories and
#                   two knowledge ablations in the chosen setting (minutes to hours, by the number of cores)
#   5. figures      every figure and table of the paper (experiments/benchmark/paper_assets.py)
#   6. paper        paper/main.pdf (latexmk)
#
# Data: Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026.
# Its terms forbid redistribution, so factors are extracted locally and never committed.
set -euo pipefail
cd "$(dirname "$0")"
STAGES=("$@")
[[ ${#STAGES[@]} -eq 0 ]] && STAGES=(install data test experiments figures paper)
want() { local s; for s in "${STAGES[@]}"; do [[ "$s" == "$1" ]] && return 0; done; return 1; }
say() { printf '\n== %s\n' "$*"; }

PY=python3
if want install; then
  say "1. install"
  if [[ -z "${CONDA_DEFAULT_ENV:-}" || "${CONDA_DEFAULT_ENV:-}" == "base" ]] && [[ -z "${VIRTUAL_ENV:-}" ]]; then
    [[ -d .venv ]] || python3 -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
  fi
  $PY -m pip install --quiet --upgrade pip
  $PY -m pip install --quiet -e ".[olca,experiments,report,app,dev]"
fi
[[ -f .venv/bin/activate && -z "${VIRTUAL_ENV:-}" && -z "${CONDA_DEFAULT_ENV:-}" ]] && source .venv/bin/activate

have_factors() { ls data/factors/*.json >/dev/null 2>&1; }
olca_up() { $PY -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(s.connect_ex(('127.0.0.1', ${OLCA_PORT:-8080})))"; }

if want data; then
  say "2. data"
  if have_factors; then
    echo "factors found: $(ls -t data/factors/*.json | head -1)"
  elif olca_up; then
    $PY experiments/openlca/extract_factors.py --method "${BRANCH_METHOD:-EF 3.1}" --all-grids --port "${OLCA_PORT:-8080}"
  else
    cat <<'MSG'
No factors and no openLCA on port 8080. To extract them (once, about 10 minutes):
  1. Install openLCA 2.6 and import BAFU:2026 and the openLCA LCIA methods (openLCA Nexus, free).
  2. In openLCA: open the database, then Tools > Developer tools > IPC Server > Start (port 8080).
  3. Run: bash reproduce.sh data
Continuing with the benchmark summaries committed in paper/data/.
MSG
  fi
fi

if want test; then
  say "3. test"
  BRANCH_DEMO=1 $PY -m pytest -q tests
fi

if want experiments; then
  say "4. experiments"
  if have_factors; then
    for cfg in "prior 0.05" "tails 0.05" "prior 0.025" "tails 0.025"; do
      set -- $cfg
      TRUTH=$1 TAU=$2 bash experiments/benchmark/run_benchmark.sh
    done
    CONFIRM=1 bash experiments/benchmark/run_benchmark.sh   # new seeds 1000 to 1029 for the chosen setting
    bash experiments/benchmark/run_proposal_experiments.sh  # other impact categories and knowledge ablations
    bash experiments/benchmark/run_more_seeds.sh            # the larger run: 5,400 sessions per category
    bash experiments/benchmark/run_v02_experiments.sh       # experiments after the audit (docs/CLAIMS.md, rows 2 to 4 and 9 to 12)
  else
    echo "skipped: no factors (see stage 2); the paper uses paper/data/*.csv"
  fi
fi

if want figures; then
  say "5. figures and tables"
  $PY experiments/benchmark/paper_assets.py
  $PY experiments/benchmark/proposal_assets.py
fi

if want paper; then
  say "6. paper"
  (cd paper && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex >/dev/null && \
     echo "paper/main.pdf: $(pdfinfo main.pdf 2>/dev/null | awk '/Pages/ {print $2}') pages")
fi
say "done"

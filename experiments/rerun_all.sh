#!/usr/bin/env bash
# Everything that has to run again after a prior changes, in one command.
#
#   bash experiments/rerun_all.sh
#
# Needs: the extracted factors in data/factors/, and openLCA open on the BAFU:2026
# database with the IPC server on port 8080 (Tools > Developer tools > IPC Server > Start).
# It keeps the previous results folder, reruns the full benchmark and the run with new
# seeds, validates against openLCA (18 cases and every grid), rebuilds the figures,
# tables and numbers of the paper, and commits and pushes paper/.
set -euo pipefail
cd "$(dirname "$0")/.."
python -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(s.connect_ex(('127.0.0.1', ${OLCA_PORT:-8080})))" || {
  echo "openLCA is not answering on port ${OLCA_PORT:-8080}. In openLCA: open the BAFU database, then"
  echo "Tools > Developer tools > IPC Server > Start. Leave that window open and run this again."; exit 1; }
[[ -d results ]] && mv results "results_$(date +%Y-%m-%d_%H%M%S)"
KEEP=""; command -v caffeinate >/dev/null 2>&1 && KEEP="caffeinate -i"
echo "== 1/4 benchmark (about 10 minutes on a laptop with many cores)"
$KEEP bash reproduce.sh experiments
echo "== 2/4 validation against openLCA"
python experiments/validate_openlca.py
python experiments/validate_openlca.py --all-grids --pairs 1
cp results/validation_all_grids.csv paper/data/validation_all_grids.csv
echo "== 3/4 figures, tables and numbers of the paper"
python experiments/paper_assets.py
echo "== 4/4 commit and push"
git add paper/data paper/tables paper/figures
git commit -m "Benchmark and validation run again ($(date +%Y-%m-%d))" && git push
echo "Done. You can stop the IPC Server and close openLCA."

#!/usr/bin/env bash
# One session after the disposal datasets of the plastics changed (14 November 2026):
# PET and polyethylene now use the disposal datasets of their own polymer.
#
#   bash experiments/record/disposal_datasets_session.sh              # everything
#   bash experiments/record/disposal_datasets_session.sh materials    # resume at the validation of the added materials
#
# Needs openLCA open on BAFU:2026 with the IPC server on port 8080 for steps 1 and 2.
# Step 3 (the benchmark) does not use openLCA. Nothing is committed: the results stay in
# the folder to be read before the paper changes.
set -euo pipefail
cd "$(dirname "$0")/../.."
python -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(s.connect_ex(('127.0.0.1', 8080)))" || {
  echo "openLCA is not answering on port 8080. In openLCA: open the database, then"
  echo "Tools > Developer tools > IPC Server > Start. Then run this again."; exit 1; }
mkdir -p outputs
FROM="${1:-start}"
FACTORS="$(ls -t data/factors/*.json | head -1)"
if [[ "$FROM" == "start" ]]; then
cp "$FACTORS" outputs/factors_backup_before_disposal_fix.json
# the summaries of the paper as they were with the stand-in datasets, kept for comparison
KEEP_DIR="paper/data/before_disposal_datasets_2026-11-14"
mkdir -p "$KEEP_DIR" && cp paper/data/*.csv "$KEEP_DIR"/ && cp -R paper/data/proposal_2026-11-13 "$KEEP_DIR"/
[[ -d results ]] && mv results "results_$(date +%Y-%m-%d_%H%M%S)"
mkdir -p results

echo "== 1/4 factors of the six disposal datasets"
python experiments/openlca/extract_factors.py --method "EF 3.1" --update --only \
  disposal_polyethylene_terephthalate_incineration disposal_polyethylene_incineration \
  disposal_polyethylene_landfill disposal_plastics_mixture_incineration \
  disposal_plastics_mixture_landfill disposal_expanded_polystyrene_incineration \
  | tee outputs/disposal_extraction.log
python - "$FACTORS" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
new = ["disposal_polyethylene_terephthalate_incineration", "disposal_polyethylene_incineration",
       "disposal_polyethylene_landfill", "disposal_plastics_mixture_incineration",
       "disposal_plastics_mixture_landfill", "disposal_expanded_polystyrene_incineration"]
missing = [k for k in new if k not in data["factors"]]
if missing:
    sys.exit("NOT EXTRACTED: " + ", ".join(missing) + ". Nothing else was run.")
for old in ("disposal_pet_incineration", "disposal_pet_landfill"):   # names of the old stand-in
    data["factors"].pop(old, None)
json.dump(data, open(path, "w"), indent=2)
cc = lambda k: data["factors"][k].get("impacts", data["factors"][k]).get("Climate change")
print("climate change, kg CO2 eq per kg:")
for k in new:
    print(f"  {k}: {cc(k):.4f}")
print(len(data["factors"]), "factors in", path)
PY

echo "== 2/4 validation against openLCA (18 cases, every grid, every added material)"
python experiments/openlca/validate_openlca.py | tee outputs/disposal_validation.log
python experiments/openlca/validate_openlca.py --all-grids --pairs 1 | tee -a outputs/disposal_validation.log
fi
python experiments/openlca/validate_materials.py | tee -a outputs/disposal_validation.log
cp results/validation_all_grids.csv paper/data/validation_all_grids.csv

echo "== 3/4 the whole benchmark again (openLCA is no longer needed)"
KEEP=""; command -v caffeinate >/dev/null 2>&1 && KEEP="caffeinate -i"
$KEEP bash reproduce.sh experiments

echo "== 4/4 tables, figures and numbers of the paper"
python experiments/benchmark/paper_assets.py
python experiments/benchmark/proposal_assets.py
echo
echo "Done. Nothing was committed. You can stop the IPC Server and close openLCA."

#!/usr/bin/env bash
# Other impact categories and knowledge ablations, as fixed in experiments/PLAN_2026-11-13.md.
#
#   bash experiments/run_proposal_experiments.sh            # everything (placebo first)
#   bash experiments/run_proposal_experiments.sh placebo    # only the check of the new code path
#   bash experiments/run_proposal_experiments.sh rest       # everything except the placebo
#
# Chosen setting of the paper: tau 2.5%, three questions per round, 30 seeds, N = 20,000,
# experts from the priors and from their tails, four strategies.
# Writes results/proposal/<name>_<expert>/ALL_summary.csv.
set -euo pipefail
cd "$(dirname "$0")/.."

PRODUCTS=(pet_bottle_1l glass_refillable_1l aluminium_can_330ml beverage_carton_1l)
REGIONS=(PT DE BR)
STRATS=(decision_flip sobol entropy random)
ls data/factors/*.json >/dev/null 2>&1 || { echo "No factors in data/factors/."; exit 1; }

run() {  # name, category, ablation
  local name=$1 category=$2 ablation=$3
  for truth in prior tails; do
    local out="proposal/${name}_${truth}"
    mkdir -p "results/$out"
    for region in "${REGIONS[@]}"; do
      for ((i = 0; i < ${#PRODUCTS[@]}; i++)); do
        for ((j = i + 1; j < ${#PRODUCTS[@]}; j++)); do
          a=${PRODUCTS[$i]}; b=${PRODUCTS[$j]}
          python experiments/run_grid.py --case real --a "$a" --b "$b" --region "$region" \
            --batch 3 --seeds 30 --n 20000 --tau 0.025 --truth "$truth" --strategies "${STRATS[@]}" \
            --category "$category" --ablation "$ablation" --tag "$out/${region}_${a}_vs_${b}" >/dev/null
        done
      done
    done
    python experiments/summarize_benchmark.py "results/$out" >/dev/null
    echo "done: results/$out/ALL_summary.csv"
  done
}

[[ "${1:-all}" == "rest" ]] || run placebo "Climate change" none
[[ "${1:-all}" == "placebo" ]] && exit 0
run acidification "Acidification" none
run water_use "Water use" none
run resource_use_fossils "Resource use fossils" none
run no_location "Climate change" no_location
run uniform "Climate change" uniform

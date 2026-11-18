#!/usr/bin/env bash
# Other impact categories and knowledge ablations, as fixed in experiments/record/PLAN_2026-11-13.md.
#
#   bash experiments/benchmark/run_proposal_experiments.sh            # everything (placebo first)
#   bash experiments/benchmark/run_proposal_experiments.sh placebo    # only the check of the new code path
#   bash experiments/benchmark/run_proposal_experiments.sh rest       # everything except the placebo
#   QUICK=1 bash experiments/benchmark/run_proposal_experiments.sh    # PT, three pairs, one seed, N = 2,000: checks that it runs, not a result
#
# Chosen setting of the paper: tau 2.5%, three questions per round, 30 seeds, N = 20,000,
# experts from the priors and from their tails, four strategies.
# Writes results/proposal/<name>_<expert>/ALL_summary.csv.
set -euo pipefail
cd "$(dirname "$0")/../.."

PRODUCTS=(pet_bottle_1l glass_refillable_1l aluminium_can_330ml beverage_carton_1l)
REGIONS=(PT DE BR)
STRATS=(decision_flip sobol entropy random)
if [[ "${QUICK:-0}" == "1" ]]; then
  SEEDS=1; N=2000; REGIONS=(PT); PRODUCTS=(pet_bottle_1l glass_refillable_1l aluminium_can_330ml)
else
  SEEDS=30; N=20000
fi
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
          python experiments/benchmark/run_grid.py --case real --a "$a" --b "$b" --region "$region" \
            --batch 3 --seeds "$SEEDS" --n "$N" --tau 0.025 --truth "$truth" --strategies "${STRATS[@]}" \
            --category "$category" --ablation "$ablation" --tag "$out/${region}_${a}_vs_${b}" >/dev/null
        done
      done
    done
    python experiments/benchmark/summarize_benchmark.py "results/$out" >/dev/null
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

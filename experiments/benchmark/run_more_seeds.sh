#!/usr/bin/env bash
# The larger run fixed in experiments/record/PLAN_2026-11-15.md: 300 further seeds (2000 to 2299) per case
# in the chosen setting, with experts from the tails, for Acidification and Climate change.
#
#   bash experiments/benchmark/run_more_seeds.sh
#   QUICK=1 bash experiments/benchmark/run_more_seeds.sh   # PT, three pairs, one seed, N = 2,000: checks that it runs, not a result
#
# Writes results/more_seeds/<category>_tails/ALL_summary.csv.
set -euo pipefail
cd "$(dirname "$0")/../.."
PRODUCTS=(pet_bottle_1l glass_refillable_1l aluminium_can_330ml beverage_carton_1l)
REGIONS=(PT DE BR)
if [[ "${QUICK:-0}" == "1" ]]; then
  SEEDS=1; N=2000; REGIONS=(PT); PRODUCTS=(pet_bottle_1l glass_refillable_1l aluminium_can_330ml)
else
  SEEDS=300; N=20000
fi
ls data/factors/*.json >/dev/null 2>&1 || { echo "No factors in data/factors/."; exit 1; }
for category in "Acidification" "Climate change"; do
  out="more_seeds/$(echo "$category" | tr ' ' '_')_tails"
  mkdir -p "results/$out"
  for region in "${REGIONS[@]}"; do
    for ((i = 0; i < ${#PRODUCTS[@]}; i++)); do
      for ((j = i + 1; j < ${#PRODUCTS[@]}; j++)); do
        a=${PRODUCTS[$i]}; b=${PRODUCTS[$j]}
        python experiments/benchmark/run_grid.py --case real --a "$a" --b "$b" --region "$region" \
          --batch 3 --seeds "$SEEDS" --n "$N" --tau 0.025 --truth tails --strategies decision_flip \
          --category "$category" --ablation none --first-seed 2000 --tag "$out/${region}_${a}_vs_${b}" >/dev/null
      done
    done
  done
  python experiments/benchmark/summarize_benchmark.py "results/$out" >/dev/null
  echo "done: results/$out/ALL_summary.csv"
done

#!/usr/bin/env bash
# Meta 2: the full real benchmark in one command (proposal v2, section 6).
#
#   bash experiments/benchmark/run_benchmark.sh            # full run (hours on a laptop)
#   QUICK=1 bash experiments/benchmark/run_benchmark.sh    # PT, three pairs, one seed, N = 2,000: checks that it runs, not a result
#   TRUTH=tails bash experiments/benchmark/run_benchmark.sh  # experts drawn from the tails of the priors
#   TRUTH=tails TAU=0.025 bash experiments/benchmark/run_benchmark.sh  # stricter certificate
#   CONFIRM=1 bash experiments/benchmark/run_benchmark.sh   # held out check of the chosen setting:
#       fresh seeds 1000 to 1029, tail experts, tau 2.5%, batch 2 and 3, decision flip only
#   BRANCH_REGIONS=another/folder bash experiments/benchmark/run_benchmark.sh   # other region files
#   BRANCH_FACTORS=data/factors_second/hybrid_elcd32.json ONLY="PT DE" SUFFIX=_elcd \
#       bash experiments/benchmark/run_benchmark.sh   # second database test: other factor file, two regions,
#                                           # results in results/benchmark..._elcd
#
# Needs the extracted BAFU factors in data/factors/ (openLCA does NOT need to be open).
# Every pair of the four benchmark products, in Portugal, Germany and Brazil;
# every query strategy; batch sizes 1 to 5; 30 seeds; then boxplots, P(flip)
# curves and paired Wilcoxon tests per case, and one table for all cases.
set -euo pipefail
cd "$(dirname "$0")/../.."

PRODUCTS=(pet_bottle_1l glass_refillable_1l aluminium_can_330ml beverage_carton_1l)
REGIONS=(PT DE BR)
if [[ -n "${ONLY:-}" ]]; then read -ra REGIONS <<< "$ONLY"; fi
if [[ "${QUICK:-0}" == "1" ]]; then
  SEEDS=1; BATCH=(1); N=2000; REGIONS=(PT); PRODUCTS=(pet_bottle_1l glass_refillable_1l aluminium_can_330ml)
else
  SEEDS=30; BATCH=(1 2 3 4 5); N=20000
fi
FIRST_SEED=0; STRATS=()
if [[ "${CONFIRM:-0}" == "1" ]]; then
  TRUTH=tails; TAU=0.025; BATCH=(2 3); FIRST_SEED=1000; STRATS=(--strategies decision_flip)
fi
TRUTH=${TRUTH:-prior}
TAU=${TAU:-0.05}
OUT=results/benchmark$([[ "$TRUTH" == "tails" ]] && echo _tails || true)$([[ "$TAU" != "0.05" ]] && echo "_tau${TAU}" || true)$([[ "${CONFIRM:-0}" == "1" ]] && echo _confirm || true)${SUFFIX:-}
mkdir -p "$OUT"
[[ -n "${BRANCH_FACTORS:-}" && -f "$BRANCH_FACTORS" ]] || ls data/factors/*.json >/dev/null 2>&1 || { echo "No factors in data/factors/. Run experiments/openlca/extract_factors.py first."; exit 1; }

for region in "${REGIONS[@]}"; do
  for ((i = 0; i < ${#PRODUCTS[@]}; i++)); do
    for ((j = i + 1; j < ${#PRODUCTS[@]}; j++)); do
      a=${PRODUCTS[$i]}; b=${PRODUCTS[$j]}; tag="$(basename "$OUT")/${region}_${a}_vs_${b}"
      echo "== $region: $a vs $b"
      python experiments/benchmark/run_grid.py --case real --a "$a" --b "$b" --region "$region" \
        --batch "${BATCH[@]}" --seeds "$SEEDS" --n "$N" --tag "$tag" --truth "$TRUTH" --tau "$TAU" \
        --first-seed "$FIRST_SEED" ${STRATS[@]+"${STRATS[@]}"}
      python experiments/benchmark/analyze.py "results/$tag" > "results/${tag}_analysis.txt"
    done
  done
done

python experiments/benchmark/summarize_benchmark.py "$OUT"
echo "done: $OUT/ALL_summary.csv"

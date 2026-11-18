#!/usr/bin/env bash
# The experiments of version 0.2 fixed in experiments/record/PLAN_2026-11-15.md (blocks A2, A3, B2, B3).
# None of them needs openLCA: they read the factor file.
#
#   bash experiments/benchmark/run_v02_experiments.sh                # everything that the factor file allows
#   bash experiments/benchmark/run_v02_experiments.sh families       # one block: families | elcd | cff | wash | uncertainty
#   bash experiments/benchmark/run_v02_experiments.sh review         # equivalence | adverse | synthetic (plan, points 13 to 15)
#   QUICK=1 bash experiments/benchmark/run_v02_experiments.sh        # one region, two pairs, one seed, N = 2,000: checks that it runs
#
# Setting of the paper: tau 2.5%, three questions per round, N = 20,000, four strategies, experts
# from the priors and from their tails. Seeds 200 to 229: new seeds, because 0 to 29 chose the
# setting of the paper (FIRST_SEED=0 repeats the old ones); QUICK uses seed 900, so that a check
# of the code never shows a seed of the results. Writes results/v02/<block>_<expert>/.
# Sensitivity runs (not readings): wash_old, cff_heat_none, cff_heat_district, cff_pet_ssp,
# uncertainty_correlated.
# The block "uncertainty" runs only when the factor file carries the uncertainty of the datasets
# (experiments/openlca/extract_uncertainty.py, which does need openLCA).
set -euo pipefail
cd "$(dirname "$0")/../.."

BENCH=(pet_bottle_1l glass_refillable_1l aluminium_can_330ml beverage_carton_1l)
E=data/examples
FAMILIES=(   # B2, fixed on 16 November 2026: "A B" per line
  "$E/ps_cup_05l.json $E/pla_cup_05l.json"
  "$E/ps_cup_05l.json $E/eps_cup_03l.json"
  "$E/pla_cup_05l.json $E/eps_cup_03l.json"
  "$E/pp_bottle_1l.json pet_bottle_1l"
  "$E/pvc_bottle_1l.json pet_bottle_1l"
  "$E/pp_bottle_1l.json $E/pvc_bottle_1l.json"
  "$E/steel_can_05l.json aluminium_can_330ml"
  "$E/carton_box_1l.json $E/paper_bag_1l.json"
  "$E/bag_in_box_3l.json beverage_carton_1l"
  "$E/carton_box_1l.json beverage_carton_1l"
)
STRATS=(decision_flip sobol entropy random)
if [[ "${QUICK:-0}" == "1" ]]; then SEEDS=1; N=2000; else SEEDS=30; N=20000; fi
if [[ "${QUICK:-0}" == "1" ]]; then FIRST="${FIRST_SEED:-900}"; else FIRST="${FIRST_SEED:-200}"; fi
has_factor() { python - "$BAFU" "$1" <<'PY'
import json, sys
sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1]))["factors"] else 1)
PY
}
BAFU="$(ls -t data/factors/*.json 2>/dev/null | head -1 || true)"
[[ -n "$BAFU" ]] || { echo "No factors in data/factors/."; exit 1; }
WHAT="${1:-all}"
want() { [[ "$WHAT" == "all" || "$WHAT" == "$1" ]]; }
name() { basename "$1" .json; }

bench_pairs() { local i j; for ((i = 0; i < ${#BENCH[@]}; i++)); do for ((j = i + 1; j < ${#BENCH[@]}; j++)); do
  echo "${BENCH[$i]} ${BENCH[$j]}"; done; done; }

run() {  # block name, factor file, regions (quoted list), pairs (function or "families"), extra run_grid options...
  local block=$1 factors=$2 regions=$3 pairs=$4 limit=1000; shift 4
  if [[ "${QUICK:-0}" == "1" ]]; then regions=${regions%% *}; limit=2; fi   # one region, two pairs
  for truth in ${TRUTHS:-prior tails}; do
    local out="v02/${block}_${truth}"
    rm -rf "results/$out"; mkdir -p "results/$out"
    for region in $regions; do
      while read -r a b; do
        BRANCH_FACTORS="$factors" python experiments/benchmark/run_grid.py --case real --a "$a" --b "$b" --region "$region" \
          --batch 3 --seeds "$SEEDS" --first-seed "$FIRST" --n "$N" --tau 0.025 --truth "$truth" --strategies "${STRATS[@]}" \
          --tag "$out/${region}_$(name "$a")_vs_$(name "$b")" "$@" >/dev/null
      done < <(if [[ "$pairs" == "families" ]]; then printf '%s\n' "${FAMILIES[@]}"; else bench_pairs; fi | head -n "$limit")
    done
    python experiments/benchmark/summarize_benchmark.py "results/$out" >/dev/null
    echo "done: results/$out/ALL_summary.csv"
  done
}

if want families; then
  echo "== B2. Other product families: 10 pairs in PT, DE and BR"
  run families "$BAFU" "PT DE BR" families
fi

if want elcd; then
  echo "== B3. A second database: placebo first, then the hybrid with ELCD 3.2"
  python experiments/data/make_hybrid_factors.py --replace none >/dev/null
  python experiments/data/make_hybrid_factors.py >/dev/null
  python experiments/data/make_hybrid_factors.py --climate ipcc2021 >/dev/null
  run bafu12 "$BAFU" "PT DE" bench
  run placebo12 data/factors_second/placebo_none.json "PT DE" bench
  python - <<'PY'
import csv, glob, os, sys
bad = []
for truth in ("prior", "tails"):
    for f in sorted(glob.glob(f"results/v02/bafu12_{truth}/*_runs.csv")):
        g = f.replace("bafu12_", "placebo12_")
        a, b = list(csv.DictReader(open(f))), list(csv.DictReader(open(g)))
        cols = [c for c in a[0] if c not in ("latency_mean_s", "latency_max_s", "wall_s")]
        if len(a) != len(b) or any(x[c] != y[c] for x, y in zip(a, b) for c in cols):
            bad.append(os.path.basename(f))
if bad:
    sys.exit("PLACEBO FAILED: the file with nothing replaced does not reproduce BAFU in " + ", ".join(bad))
print("placebo passed: the factor file with nothing replaced reproduces BAFU in the 12 cases, both experts")
PY
  run elcd data/factors_second/hybrid_elcd32.json "PT DE" bench
  run elcd_ipcc2021 data/factors_second/hybrid_elcd32_ipcc2021.json "PT DE" bench
fi

if want cff; then
  echo "== A2. Circular Footprint Formula against cut-off, the 18 cases"
  run cutoff "$BAFU" "PT DE BR" bench
  run cff "$BAFU" "PT DE BR" bench --system-model cff
  echo "== A2, sensitivity: no credit for heat, district heat instead of gas, PET quality 1"
  run cff_heat_none "$BAFU" "PT DE BR" bench --system-model cff --cff-heat none
  if has_factor district_heat_ch_average; then
    run cff_heat_district "$BAFU" "PT DE BR" bench --system-model cff --cff-heat district
  else
    echo "   district heat skipped: no factor district_heat_ch_average (python experiments/openlca/extract_factors.py --update --only district_heat_ch_average)"
  fi
  run cff_pet_ssp "$BAFU" "PT DE BR" bench --system-model cff --cff-pet-ssp
fi

if want wash; then
  echo "== A1, sensitivity: washing electricity with the upper bound of before 16 November (0.03 kWh)"
  [[ -d results/v02/cutoff_prior ]] || run cutoff "$BAFU" "PT DE BR" bench
  run wash_old "$BAFU" "PT DE BR" bench --wash-kwh-high 0.03
fi

if want uncertainty; then
  if python - "$BAFU" <<'PY'
import json, sys
f = json.load(open(sys.argv[1]))["factors"]
sys.exit(0 if any((v.get("uncertainty") or {}).get("Climate change", {}).get("gsd") for v in f.values()) else 1)
PY
  then
    echo "== A3. The uncertainty of the datasets in every draw, the 18 cases"
    [[ -d results/v02/cutoff_prior ]] || run cutoff "$BAFU" "PT DE BR" bench
    run uncertainty "$BAFU" "PT DE BR" bench --inventory-uncertainty on
    echo "== A3, sensitivity: all factors moving together (the bound opposite to independence)"
    run uncertainty_correlated "$BAFU" "PT DE BR" bench --inventory-uncertainty correlated
    echo "== Third ablation of the proposal: the spread only for the factors whose runs are consistent"
    run uncertainty_consistent "$BAFU" "PT DE BR" bench --inventory-uncertainty consistent
  else
    echo "== A3 skipped: $BAFU has no uncertainty yet (python experiments/openlca/extract_uncertainty.py, with openLCA open)"
  fi
fi

# Second review of 16 November 2026 (plan, points 13 to 15). Seeds 300 to 329, used nowhere before.
# "review" runs the three blocks; with no argument they run with everything else.
if [[ "${QUICK:-0}" == "1" ]]; then FIRST=950; else FIRST="${REVIEW_FIRST_SEED:-300}"; fi
want2() { [[ "$WHAT" == "all" || "$WHAT" == "$1" || "$WHAT" == "review" ]]; }

if want2 equivalence; then
  echo "== 13. Equivalence with the Sobol index of the impact: new seeds, experts from the priors"
  TRUTHS="prior" run eq_families "$BAFU" "PT DE BR" families
  TRUTHS="prior" run eq_bench "$BAFU" "PT DE BR" bench
fi

if want2 adverse; then
  echo "== 14. A second wrong expert: every continuous belief wrong on the side against the verdict"
  TRUTHS="adverse" run stress_families "$BAFU" "PT DE BR" families
  TRUTHS="adverse" run stress_bench "$BAFU" "PT DE BR" bench
fi

if want2 synthetic; then
  echo "== 15. Illustration: where decision flip and the Sobol index of the impact part (synthetic models)"
  if [[ "${QUICK:-0}" == "1" ]]; then MODELS=$(seq 5900 5901); SYN_SEEDS=1; else MODELS=$(seq 5000 5099); SYN_SEEDS=5; fi
  python experiments/benchmark/run_grid.py --case lca --J 40 --case_seeds $MODELS --strategies decision_flip sobol entropy \
    --batch 1 3 --seeds "$SYN_SEEDS" --first-seed "$FIRST" --n "$N" --tau 0.025 --truth prior --tag v02/synthetic >/dev/null
  echo "done: results/v02/synthetic_runs.csv"
fi
python experiments/benchmark/v02_summary.py

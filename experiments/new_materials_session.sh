#!/usr/bin/env bash
# New materials, the part that needs openLCA (openLCA open, BAFU:2026 open, IPC Server on 8080).
#
#   bash experiments/new_materials_session.sh
#
# 1. Extracts the factors of the datasets the added materials need and keeps every factor already
#    in the file (about 5 to 10 minutes). A dataset that is not found is listed, not guessed.
# 2. Checks every added material against openLCA in PT, DE and BR
#    -> paper/data/validation_new_materials.csv
set -euo pipefail
cd "$(dirname "$0")/.."
python -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(s.connect_ex(('127.0.0.1', 8080)))" || {
  echo "openLCA is not answering on port 8080. In openLCA: open the database, then"
  echo "Tools > Developer tools > IPC Server > Start. Then run this again."; exit 1; }

KEYS=(pp_granulate ps_gpps ps_hips eps_expandable pvc_regional_storage pla_granulate thermoforming
      steel_unalloyed sheet_rolling_steel kraft_paper_unbleached kraft_paper_bleached
      folding_boxboard solid_bleached_board solid_unbleached_board whitelined_chipboard
      disposal_pp_incineration disposal_ps_incineration disposal_ps_landfill
      disposal_pvc_incineration disposal_pvc_landfill disposal_tin_sheet_incineration
      disposal_tin_sheet_landfill disposal_packaging_paper_incineration disposal_paper_landfill)

echo "== 1/2 factors of the new datasets (${#KEYS[@]} datasets)"
mkdir -p outputs
cp "$(ls -t data/factors/*.json | head -1)" outputs/factors_backup_before_new_materials.json
python experiments/extract_factors.py --method "EF 3.1" --update --only "${KEYS[@]}" | tee outputs/new_materials_extraction.log

echo "== 2/2 every added material against openLCA (PT, DE, BR)"
python experiments/validate_materials.py | tee outputs/new_materials_validation.log

echo
echo "Done. You can stop the IPC Server now."

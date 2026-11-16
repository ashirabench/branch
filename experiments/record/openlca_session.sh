#!/usr/bin/env bash
# Everything that needs openLCA, in one go (openLCA open, database open, IPC Server on 8080).
#
#   bash experiments/record/openlca_session.sh
#
# 1. Extracts every unit factor again (fix of 2 Nov 2026: per unit of the reference
#    exchange, e.g. kWh, not of the flow's reference unit, e.g. MJ).
# 2. Validates BRANCH against openLCA on the 18 benchmark cases -> paper/data/validation_openlca.csv
# 3. Lists the secondary packaging datasets (boxes, film, pallets) -> outputs/datasets_secondary_packaging.csv
set -euo pipefail
cd "$(dirname "$0")/../.."
python -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(s.connect_ex(('127.0.0.1', 8080)))" || {
  echo "openLCA is not answering on port 8080. In openLCA: open the database, then"
  echo "Tools > Developer tools > IPC Server > Start. Then run this again."; exit 1; }

echo "== 1/3 factors (about 10 to 20 minutes)"
mkdir -p outputs
ls data/factors/*.json >/dev/null 2>&1 && cp "$(ls -t data/factors/*.json | head -1)" outputs/factors_backup_before_unit_fix.json || true
python experiments/openlca/extract_factors.py --method "EF 3.1" --all-grids

echo "== 2/3 validation against openLCA (18 cases)"
python experiments/openlca/validate_openlca.py

echo "== 3/3 secondary packaging datasets"
python experiments/openlca/list_datasets.py --full --database secondary_packaging \
  --grep "corrugated" "cardboard" "carton box" "folding box" "stretch" "shrink" "film" "pallet" "wrapping"

echo
echo "Done. Send me: paper/data/validation_openlca.csv and outputs/datasets_secondary_packaging.csv"
echo "You can stop the IPC Server now."

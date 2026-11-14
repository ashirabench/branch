#!/usr/bin/env bash
# Products that are not containers, the part that needs openLCA (openLCA open, BAFU:2026 open,
# IPC Server on 8080).
#
#   bash experiments/any_product_session.sh
#
# 1. Reads the factors of the processes two example products name (data/examples/cotton_bag.json
#    and pp_bag.json), keeping every factor already in the file.
# 2. Checks the comparison against openLCA -> paper/data/validation_any_product.csv
# 3. Tries the search and the reading of a process chosen by name, as the app does them
#    -> outputs/any_product_check.log
set -euo pipefail
cd "$(dirname "$0")/.."
python -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(s.connect_ex(('127.0.0.1', 8080)))" || {
  echo "openLCA is not answering on port 8080. In openLCA: open the database, then"
  echo "Tools > Developer tools > IPC Server > Start. Then run this again."; exit 1; }
mkdir -p outputs
cp "$(ls -t data/factors/*.json | head -1)" outputs/factors_backup_before_any_product.json

echo "== 1/3 factors of the processes of the two example products"
python -u experiments/extract_factors.py --method "EF 3.1" --update \
  --specs data/examples/cotton_bag.json data/examples/pp_bag.json --region PT

echo "== 2/3 the comparison against openLCA"
python -u experiments/validate_openlca.py --specs data/examples/cotton_bag.json data/examples/pp_bag.json \
  --regions PT --out paper/data/validation_any_product.csv

echo "== 3/3 search and reading of a process by name, as in the app"
python -u experiments/check_any_product.py | tee outputs/any_product_check.log

echo
echo "Done. You can stop the IPC Server now."

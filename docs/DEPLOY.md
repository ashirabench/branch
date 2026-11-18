# Hosting BRANCH for companies

Companies only need a browser. openLCA runs once, on your side, to extract the factors.

## 1. Extract the factors (once per database and method)

With openLCA 2.6 open on BAFU:2026 and the IPC server running:

```bash
python experiments/openlca/extract_factors.py --method "EF 3.1"
python experiments/openlca/extract_factors.py --update --specs pet_bottle_1l glass_refillable_1l aluminium_can_330ml beverage_carton_1l --region BR-AM
```

This writes `data/factors/<database>_<method>.json`. It is git ignored and must stay that way.

## 2. Run the app

Locally:

```bash
pip install -e ".[app]"
python app.py     # newest file in data/factors/, http://127.0.0.1:7860
BRANCH_DEMO=1 python app.py                                         # illustrative numbers, for showing the interface
```

On a server, the command is the same. `BRANCH_HOST=0.0.0.0` makes the page answer to other computers, `PORT` chooses the port and `BRANCH_FACTORS` names the factor file, which stays on the server. Put the page behind HTTPS.

```bash
BRANCH_HOST=0.0.0.0 PORT=7860 BRANCH_FACTORS=/srv/factors/<your factors file>.json python app.py
```

This repository does not ship a container image: an earlier version had a Dockerfile that no test ever built, and it was removed on 18 November 2026.

## 3. Rules for the factors file

- The server reads it; the page never offers it for download. Only results leave the server.
- Every report cites "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026".
- Keep a copy of the BAFU terms of use with the deployment, and record the date you checked that a hosted calculator is allowed.

## 4. What a company does

1. Picks the region (for example Amazonas, Manaus).
2. Starts from an example product or types its own bill of materials (part, material, grams), for two products.
3. Answers the few questions BRANCH asks, presses "I don't know", or finishes early (the report then says how sure BRANCH is).
4. Downloads the manager report (PDF) and the technical report (Markdown).

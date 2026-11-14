# Hosting BRANCH for companies

Companies only need a browser. openLCA runs once, on your side, to extract the factors.

## 1. Extract the factors (once per database and method)

With openLCA 2.6 open on BAFU:2026 and the IPC server running:

```bash
python experiments/extract_factors.py --method "EF 3.1"
python experiments/extract_factors.py --update --specs pet_bottle_1l glass_refillable_1l aluminium_can_330ml beverage_carton_1l --region BR-AM
```

This writes `data/factors/<database>_<method>.json`. It is git ignored and must stay that way.

## 2. Run the app

Locally:

```bash
pip install -e ".[app]"
python app.py     # newest file in data/factors/, http://127.0.0.1:7860
BRANCH_DEMO=1 python app.py                                         # illustrative numbers, for showing the interface
```

On a server (Docker): the image does not contain the factors; mount them read only.

```bash
docker build -t branch .
docker run -p 7860:7860 -v $PWD/data/factors:/srv/factors:ro \
  -e BRANCH_FACTORS=/srv/factors/<your factors file>.json branch
```

Any host that runs a container works (a university VM, Render, Fly.io, a Hugging Face Space with the factors in a private dataset). Put it behind HTTPS.

## 3. Rules for the factors file

- The server reads it; the page never offers it for download. Only results leave the server.
- Every report cites "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026".
- Keep a copy of the BAFU terms of use with the deployment, and record the date you checked that a hosted calculator is allowed.

## 4. What a company does

1. Picks the region (for example Amazonas, Manaus).
2. Starts from an example product or types its own bill of materials (part, material, grams), for two products.
3. Answers the few questions BRANCH asks, presses "I don't know", or finishes early (the report then says how sure BRANCH is).
4. Downloads the manager report (PDF) and the technical report (Markdown).

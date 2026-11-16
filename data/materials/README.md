# Materials

Every file here adds a material to the catalogue without touching the code (`branch/catalogue.py` loads them). A file named after a built in material (`pet`, `hdpe`, `ldpe`, `glass`, `aluminium`, `liquid_packaging_board`) replaces it.

1. Find the datasets in your database: `python experiments/openlca/list_datasets.py --grep "tinplate" --full`.
2. Add their name patterns to `PROCESSES` in `branch/olca_extract.py` and extract: `python experiments/openlca/extract_factors.py --update --only tinplate`.
3. Write `data/materials/<id>.json`:

```json
{
  "label": "tinplate",
  "datasets": {"tinplate": ["tinplate", 1.0]},
  "datasets_source": "SOURCE: BAFU:2026 tinplate dataset",
  "conversion": null,
  "recycled": null,
  "end_of_life": {
    "model": "split",
    "recycling_rate": ["beta", {"a": 6, "b": 4}, "ASSUMPTION: about 60% of steel cans recycled; replace with Eurostat env_waspac"],
    "incineration_share": ["uniform", {"low": 0.2, "high": 0.8}, "ASSUMPTION: share of non recycled steel incinerated"],
    "incineration": "disposal_steel_incineration",
    "landfill": "disposal_steel_landfill"
  }
}
```

Every prior starts with `SOURCE:` (cited) or `ASSUMPTION:` (placeholder). Regions can override any prior with the key `"<material id>.<field>"`, for example `"tinplate.recycling_rate"`.

## Materials in this folder

| File | Material | Note |
|---|---|---|
| `corrugated_board.json` | corrugated board | formed box, no conversion step |
| `cartonboard.json` | cartonboard | four grades (FBB, SBB, SUB, WLC) |
| `kraft_paper.json` | kraft paper | bleached or unbleached; landfill dataset is a proxy |
| `pp.json` | polypropylene | landfill uses the plastics mixture dataset (the polypropylene one is marked obsolete) |
| `ps.json` | polystyrene | general purpose or high impact |
| `eps.json` | expanded polystyrene | the expansion of the beads is not modelled |
| `pvc.json` | PVC | |
| `pla.json` | PLA | end of life uses the plastics mixture datasets (the database has none for PLA) |
| `steel.json` | steel sheet | proxy for tinplate, the tin coating is not modelled |

Every dataset option of these materials was checked against openLCA on 14 November 2026
(`paper/data/validation_new_materials.csv`, made by `experiments/openlca/validate_materials.py`).
The recycling rates are assumptions except where `data/regions/` gives a sourced national value.

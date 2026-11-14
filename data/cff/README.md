# Circular Footprint Formula parameters

One file per material (`pet.json`, `aluminium.json`, ...) with the values of the official PEF **Annex C** (European Commission, JRC). Only copy values from Annex C; never estimate them.

```json
{"A": 0.2, "Qsin_Qp": 1.0, "Qsout_Qp": 1.0,
 "recycling_eol_key": "optional factor key of the recycling process at end of life",
 "source": "SOURCE: PEF Annex C, version and row"}
```

R1 (recycled content) and R2 (recycling rate) are not here: they come from the company or the region. Energy recovery credits (R3 term) are not yet included.

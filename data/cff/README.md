# Circular Footprint Formula parameters

What `system_model="cff"` reads (the cut-off default reads nothing from this folder).

| File | Content | Source |
|---|---|---|
| `<material>.json` | `A`, `Qsin_Qp`, `Qsout_Qp` of one material, each with the row it was copied from | Part C of Annex II (former PEF Annex C), version 2.1, May 2020 |
| `annex_c_packaging_A_R1_R2.csv` | The 21 packaging rows of the sheet "A - R1 - R2": `A`, `R1` and the recycling rate of every country | the same file |
| `annex_c_packaging_Qs_Qp.csv` | The sheet "Qs-Qp" (packaging materials only) | the same file |
| `energy_recovery.json` | MJ of electricity and of steam delivered per kg of each material burnt | ELCD 3.2, incineration data sets of the average European waste-to-energy plant (`data/second_database/`) |

The Annex file (`Part_C_Annex_II_V2.1_May2020.ods`, 67,186 bytes, SHA-256 `44c2642f…d66f75`) was read on
16 November 2026 from the European Platform on Life Cycle Assessment. Only values copied from it go into the
`<material>.json` files; nothing is estimated. A test checks the packaging table against the checksum computed
on the Commission's page.

## What the formula uses, and from where

| Parameter | Value in BRANCH |
|---|---|
| `A` | Annex: 0.5 for plastics, 0.2 for metals, glass and paper |
| `B` | 0, the default stated in the Annex |
| `Qsin/Qp`, `Qsout/Qp` | Annex, sheet "Qs-Qp". PET uses mechanical recycling (0.9); solid state polycondensation would be 1 |
| `R1`, `R2` | not the Annex defaults: the recycled content and the recycling rate are choices of the comparison, with the priors of the region (national statistics where there are any). The Annex defaults are kept in the CSV for comparison |
| `R3` | (1 − `R2`) × the share incinerated of what is not recycled, as in the Annex example |
| `Ev`, `E*v` | the virgin dataset of the material |
| `Erec`, `ErecEoL` | the recycled dataset of the material when the database has one; `recycling_eol_key` in the file names another one. Without any, the impact of recycling is asked as a share of the virgin material (an `ASSUMPTION` choice) |
| `E_ER`, `E_D` | the incineration and landfill datasets of the material |
| `LHV × X_ER,elec`, `LHV × X_ER,heat` | `energy_recovery.json`. The Annex says these come with the EF datasets, which BRANCH does not have |
| `E_SE,elec` | the electricity mix of the region |
| `E_SE,heat` | heat from natural gas, an assumption (ELCD itself credits a district heating mix) |

## Limits

- PS, EPS, PVC and PLA have no row in the sheet "Qs-Qp", so a product with them cannot be assessed with the formula.
- Aluminium and PLA have no ELCD incineration data set and receive no energy credit.
- The packaging glass datasets of BAFU:2026 already contain cullet, so with the formula the recycled content of glass is partly counted in the dataset as well.
- Glass and steel take heat from the furnace: their "recovered energy" is negative, a small burden instead of a credit.

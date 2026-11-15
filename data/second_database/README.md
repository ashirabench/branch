# Second database: ELCD 3.2

Files of the second database test fixed in `experiments/PLAN_2026-11-15.md`, section B3.

| File | Content |
|---|---|
| `elcd32_map.json` | Which ELCD process replaces which BRANCH factor (21), and the 8 factors ELCD does not have |
| `elcd32_factors.json` | Climate change and Acidification per unit for those 21 processes, written by `experiments/second_database/read_elcd.py` from the database file |

The database file itself (`elcd_3_2_greendelta_v2_18_correction_20220908.zolca`, free on
[openLCA Nexus](https://nexus.openlca.org/database/ELCD)) is not kept here.

## Licence and credit

Each ELCD data set states that it "can be used free of charge by anybody to perform LCA studies, to
distribute it to third parties, to convert it to other formats", provided that reference is given to
the owner of the data set and to the ELCD database with its version number. Each factor in
`elcd32_factors.json` names the owner of its data set. The values here are results computed from the
data sets, not complete ELCD data sets.

European Commission, Joint Research Centre. 2018. *European Reference Life Cycle Database (ELCD),
Version 3.2*. Distributed by GreenDelta on openLCA Nexus, file of 8 September 2022.
https://nexus.openlca.org/database/ELCD.

## Limits

- The factors are computed outside openLCA. The comparison with openLCA on three processes is in the plan
  and has not been made yet.
- ELCD was discontinued in 2018; the data sets used state validity periods that end between 2009 and 2015.
- The method in the file is EF 3.0, while the BAFU factors of BRANCH use EF 3.1.
- No BAFU value is stored in this folder. The hybrid factor file carries BAFU values and stays out of git
  (`data/factors_second/`).

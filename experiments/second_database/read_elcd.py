"""Unit impact factors of ELCD 3.2 read straight from the database file, without openLCA.

    python experiments/second_database/read_elcd.py --zolca elcd_3_2_greendelta_v2_18_correction_20220908.zolca \
        --derby derby-10.14.2.0.jar

Writes data/second_database/elcd32_factors.json. Needs Java (javac and java) and the Apache Derby
jar. The .zolca file is a zip of a Derby database; it is free on openLCA Nexus
(https://nexus.openlca.org/database/ELCD) and is not kept in this repository.

What it computes. ELCD processes are aggregated: each one stores its life cycle inventory. For the
processes named in data/second_database/elcd32_map.json the impact per unit is

    sum over elementary flows of  amount * characterisation factor  /  |reference amount|

with the amounts and the factors converted to the reference unit of each flow, as openLCA does.
The factors come from the methods stored in the same file: "EF 3.0 Method (adapted)" for Climate
change and Acidification, and "IPCC 2021 AR6" (GWP 100) for a second reading of Climate change.

Three things the first version of this calculation got wrong or had to settle, kept here on purpose:
- 45 pairs of category and flow have their factor stored twice. One factor per flow is used
  (the two are always equal); adding both changed 3 of the 483 aggregated processes by up to 0.08%.
- Waste treatment processes have a negative reference amount (-1 kg, -1000 kg): the absolute
  value is used, so the result is per kilogram of waste treated.
- Electricity has a reference amount of 3.6 MJ, which is the kWh that BRANCH uses.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT_DIR = os.path.join(ROOT, "data", "second_database")
CATEGORIES = {   # label in the output -> (method, category) in the ELCD file
    "Climate change": ("EF 3.0 Method (adapted)", "Climate change"),
    "Acidification": ("EF 3.0 Method (adapted)", "Acidification"),
    "Climate change (IPCC 2021 GWP 100)": ("IPCC 2021 AR6", "IPCC 2021 GWP 100"),
}

IMPACT_SQL = """select p.ref_id, sum((e.resulting_amount_value*ue.conversion_factor/pe.conversion_factor)*f.v)
from tbl_processes p join tbl_exchanges e on e.f_owner=p.id
join tbl_units ue on ue.id=e.f_unit join tbl_flow_property_factors pe on pe.id=e.f_flow_property_factor
join (select x.f_flow, max(x.value*pf.conversion_factor/uf.conversion_factor) v from tbl_impact_factors x
      join tbl_units uf on uf.id=x.f_unit join tbl_flow_property_factors pf on pf.id=x.f_flow_property_factor
      where x.f_impact_category={cat} group by x.f_flow) f on f.f_flow=e.f_flow
where p.process_type='LCI_RESULT' group by p.ref_id"""
PROCESS_SQL = """select p.ref_id, p.name, l.code, e.resulting_amount_value, u.name, a.name, d.valid_from, d.valid_until
from tbl_processes p join tbl_exchanges e on e.id=p.f_quantitative_reference join tbl_units u on u.id=e.f_unit
left join tbl_locations l on l.id=p.f_location left join tbl_process_docs d on d.id=p.f_process_doc
left join tbl_actors a on a.id=d.f_dataset_owner where p.process_type='LCI_RESULT'"""
CATEGORY_SQL = """select c.id, m.name, c.name from tbl_impact_categories c
join tbl_impact_methods m on c.f_impact_method=m.id"""
CHECK_SQL = [   # each must return 0: nothing this script would silently get wrong
    "select count(*) from tbl_exchanges e join tbl_processes p on p.id=e.f_owner "
    "where p.process_type='LCI_RESULT' and e.resulting_amount_formula is not null",
    "select count(*) from tbl_impact_factors where formula is not null",
]
# A factor stored twice with two different values would make "one factor per flow" a choice. It
# happens in other categories of this file (ecotoxicity, water use), never in the three used here.
TWICE_SQL = ("select count(*) from (select f_flow from tbl_impact_factors where f_impact_category={cat} "
             "group by f_flow having count(*)>1 and min(value)<>max(value)) t")


def run(db, classpath, statements):
    out = subprocess.run(["java", "-cp", classpath, "Query", db] + statements, capture_output=True, text=True,
                         cwd=os.path.dirname(db),          # Derby writes derby.log where it runs
                         env={k: v for k, v in os.environ.items() if k != "JAVA_TOOL_OPTIONS"})
    if out.returncode != 0:
        sys.exit(out.stderr[-2000:])
    blocks, rows = [], []
    for line in out.stdout.splitlines():
        if line == "--":
            blocks.append(rows)
            rows = []
        else:
            rows.append(line.split("\t"))
    return blocks


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--zolca", required=True)
    ap.add_argument("--derby", required=True, help="path of the Apache Derby jar")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "elcd32_factors.json"))
    args = ap.parse_args()
    with open(os.path.join(OUT_DIR, "elcd32_map.json")) as fh:
        mapping = json.load(fh)
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "db")
        with zipfile.ZipFile(args.zolca) as z:
            z.extractall(db)
        subprocess.run(["javac", "-d", tmp, os.path.join(HERE, "Query.java")], check=True)
        cp = os.pathsep.join([tmp, os.path.abspath(args.derby)])
        cats, procs, *checks = run(db, cp, [CATEGORY_SQL, PROCESS_SQL] + CHECK_SQL)
        for sql, rows in zip(CHECK_SQL, checks):
            if rows[0][0] != "0":
                sys.exit(f"check failed ({rows[0][0]} rows): {sql}")
        ids = {}
        for label, (method, category) in CATEGORIES.items():
            hit = [r[0] for r in cats if r[1] == method and r[2] == category]
            if len(hit) != 1:
                sys.exit(f"category {method} / {category}: found {len(hit)}")
            ids[label] = hit[0]
        for label, rows in zip(ids, run(db, cp, [TWICE_SQL.format(cat=i) for i in ids.values()])):
            if rows[0][0] != "0":
                sys.exit(f"{label}: {rows[0][0]} flows have two different factors")
        impacts = {label: {r[0]: float(r[1]) for r in rows} for label, rows in
                   zip(ids, run(db, cp, [IMPACT_SQL.format(cat=i) for i in ids.values()]))}
    by_ref = {r[0]: r for r in procs}
    factors = {}
    for key, m in mapping["mapped"].items():
        ref_id, name, loc, amount, unit, owner, valid_from, valid_until = by_ref[m["ref_id"]]
        amount = float(amount)
        if name != m["process"] or loc != m["location"]:
            sys.exit(f"{key}: the file has {name!r} [{loc}], the map says {m['process']!r} [{m['location']}]")
        per = 1.0 if (unit == "MJ" and abs(amount - 3.6) < 1e-9 and m["unit"] == "kWh") else abs(amount)
        expected = {"kWh": "MJ", "kg": "kg", "MJ": "MJ", "t*km": "t*km"}[m["unit"]]
        if unit != expected:
            sys.exit(f"{key}: reference unit {unit}, BRANCH unit {m['unit']}")
        factors[key] = {"process": name, "id": ref_id, "location": loc, "unit": m["unit"],
                        "reference": f"{amount:g} {unit}", "owner": owner,
                        "valid": f"{valid_from[:4]} to {valid_until[:4]}", "note": m.get("note", ""),
                        "impacts": {label: impacts[label][ref_id] / per for label in CATEGORIES}}
    data = {"database": "ELCD 3.2 (openLCA Nexus file elcd_3_2_greendelta_v2_18_correction_20220908)",
            "method": "EF 3.0 Method (adapted); IPCC 2021 AR6 for the second reading of climate change",
            "citation": "European Commission, Joint Research Centre, European Reference Life Cycle Database "
                        "(ELCD), version 3.2; each factor names the owner of its data set",
            "computed": datetime.date.today().isoformat(), "computed_by": "experiments/second_database/read_elcd.py",
            "aggregated_processes_in_the_file": len(procs), "factors": factors, "not_in_elcd": mapping["gaps"]}
    with open(args.out, "w") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    print(f"wrote {len(factors)} factors from {len(procs)} aggregated processes to {args.out}")


if __name__ == "__main__":
    main()

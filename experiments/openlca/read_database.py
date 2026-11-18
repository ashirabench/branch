"""Read an openLCA database file directly, with SQL, to repeat what the paper says about the database.

    python experiments/openlca/read_database.py --db ~/openLCA-data-1.4/databases/bafu_2026 counts
    python experiments/openlca/read_database.py --db <folder or .zolca> signs
    python experiments/openlca/read_database.py --db <folder or .zolca> datasets
    python experiments/openlca/read_database.py --db <folder or .zolca> sql "select count(*) from tbl_flows"

An openLCA database is an Apache Derby database: a folder under openLCA's data folder, or the same
folder zipped as a .zolca file. This script never opens the original. It copies the folder (or unzips
the file) to a temporary place and reads the copy, so openLCA can stay open and nothing is written to
your database. The copy needs as much free disk as the database, one to three gigabytes.

Reports
    counts    processes, exchanges, exchanges with a pedigree entry, lognormal exchanges
    signs     lognormal exchanges whose geometric mean has the opposite sign of the amount, by kind of flow
    datasets  for every dataset in the factor file of BRANCH: its exchanges, written to
              results/database_audit/ (never committed: this is content of the database)
    process   NAME: description and exchanges of the processes whose name contains NAME
    sql       any query; one line of output per row, tab separated

What it needs
    Two packages.       pip install -e ".[database]"   (JPype1 and jdk4py)
                        jdk4py brings a Java runtime, so nothing else has to be installed. To use
                        another Java (21 or newer), set JAVA_HOME.
    The Derby jars.     They ship inside openLCA. On a Mac the script finds them in
                        /Applications/openLCA.app; elsewhere pass --libs <folder with derby-*.jar>
                        (in the openLCA folder: plugins/olca-app_<version>/libs).

The numbers printed for BAFU:2026 v1.1 are compared with the ones the paper states, so a different
version of the database shows at once.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAC_LIBS = "/Applications/openLCA.app/Contents/Eclipse/plugins/olca-app_*/libs"

LOGNORMAL = 1   # distribution_type of a lognormal exchange in openLCA 2
SQL = {
    "processes": "select count(*) from tbl_processes",
    "exchanges": "select count(*) from tbl_exchanges",
    "with_pedigree": "select count(*) from tbl_exchanges where dq_entry is not null",
    "lognormal": f"select count(*) from tbl_exchanges where distribution_type={LOGNORMAL}",
    "signs": ("select f.flow_type, e.is_input, count(*) from tbl_exchanges e join tbl_flows f on e.f_flow=f.id "
              f"where e.distribution_type={LOGNORMAL} and e.parameter1_value*e.resulting_amount_value<0 "
              "group by f.flow_type, e.is_input"),
}
PAPER = {   # what the paper states for BAFU:2026 v1.1
    "processes": 11951, "exchanges": 420087, "with_pedigree": 227083, "lognormal": 266822,
    "wrong_sign_waste_outputs": 14167,
}


def find_jvm():
    """Path of the Java virtual machine library. Order: JAVA_HOME, the jdk4py package."""
    homes = [os.environ.get("JAVA_HOME")]
    try:
        import jdk4py
        homes.append(str(jdk4py.JAVA_HOME))
    except Exception:
        pass
    for home in filter(None, homes):
        for name in ("libjvm.dylib", "libjvm.so", "jvm.dll"):
            found = glob.glob(os.path.join(home, "**", name), recursive=True)
            if found:
                return found[0]
    sys.exit("No Java found. Run `pip install jdk4py`, or install Java 21 or newer and set JAVA_HOME.")


def find_jars(libs=None):
    """The Derby jars of openLCA: derby-<version>.jar and, from Derby 10.15 on, derbyshared-<version>.jar.
    One version only: two versions of Derby on the same path do not start."""
    folders = [libs] if libs else sorted(glob.glob(MAC_LIBS), reverse=True)
    for folder in folders:
        engines = sorted(glob.glob(os.path.join(folder, "derby-*.jar")))
        if engines:
            version = os.path.basename(engines[-1])[len("derby-"):-len(".jar")]
            shared = os.path.join(folder, f"derbyshared-{version}.jar")
            return [engines[-1]] + ([shared] if os.path.exists(shared) else [])
    sys.exit("The Derby jars were not found. Pass --libs <openLCA folder>/plugins/olca-app_<version>/libs")


def working_copy(db, tmp):
    """A copy of the database that is safe to open. Returns the folder that holds service.properties."""
    db = os.path.abspath(os.path.expanduser(db))
    target = os.path.join(tmp, "db")
    if os.path.isdir(db):
        shutil.copytree(db, target, ignore=shutil.ignore_patterns("*.lck", "_olca_"))
    elif zipfile.is_zipfile(db):
        with zipfile.ZipFile(db) as z:
            z.extractall(target)
    else:
        sys.exit(f"{db} is neither a database folder nor a .zolca file")
    for dirpath, _, files in os.walk(target):
        if "service.properties" in files:
            return dirpath
    sys.exit("no Derby database inside (service.properties is missing)")


class Database:
    """The copy of the database, opened through Java's own database interface from Python."""

    def __init__(self, db, libs=None):
        try:
            import jpype
        except ImportError:
            sys.exit('This script needs two packages: pip install -e ".[database]"')
        self.tmp = tempfile.mkdtemp(prefix="branch_db_")
        jars = find_jars(libs)
        self.conn = None
        try:
            print("copying the database to a temporary folder ...", file=sys.stderr)
            self.path = working_copy(db, self.tmp)
            if not jpype.isJVMStarted():
                jpype.startJVM(find_jvm(), "--enable-native-access=ALL-UNNAMED",
                               f"-Dderby.stream.error.file={os.path.join(self.tmp, 'derby.log')}", classpath=jars)
            self.conn = jpype.java.sql.DriverManager.getConnection("jdbc:derby:" + self.path)
        except BaseException:
            self.close()          # never leave a copy of some gigabytes behind
            raise

    def query(self, *statements):
        """One list of rows (each a list of strings) per statement."""
        blocks = []
        for sql in statements:
            st = self.conn.createStatement()
            rs = st.executeQuery(sql)
            n = rs.getMetaData().getColumnCount()
            rows = []
            while rs.next():
                rows.append(["" if rs.getString(k) is None else str(rs.getString(k)) for k in range(1, n + 1)])
            rs.close()
            st.close()
            blocks.append(rows)
        return blocks

    def close(self):
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)


def compare(label, value):
    want = PAPER.get(label)
    note = "" if want is None else ("   as in the paper" if value == want else f"   THE PAPER SAYS {want:,}")
    print(f"{label:28s} {value:>10,}{note}")


def report_counts(db):
    keys = ["processes", "exchanges", "with_pedigree", "lognormal"]
    for key, block in zip(keys, db.query(*[SQL[k] for k in keys])):
        compare(key, int(block[0][0]))


def report_signs(db):
    (rows,) = db.query(SQL["signs"])
    total = 0
    for flow_type, is_input, n in sorted(rows):
        kind = f"{flow_type.lower().replace('_', ' ')}, {'input' if is_input in ('1', 'true') else 'output'}"
        print(f"{kind:28s} {int(n):>10,}")
        total += int(n)
        if flow_type == "WASTE_FLOW" and is_input not in ("1", "true"):
            compare("wrong_sign_waste_outputs", int(n))
    print(f"{'all kinds':28s} {total:>10,}")


def exchanges_sql(where):
    return ("select p.name, l.code, f.name, f.flow_type, e.is_input, e.resulting_amount_value, e.distribution_type, "
            "e.parameter1_value, e.parameter2_value, e.dq_entry from tbl_exchanges e join tbl_processes p on e.f_owner=p.id "
            "join tbl_flows f on e.f_flow=f.id left join tbl_locations l on p.f_location=l.id "
            f"where {where} order by p.name, e.is_input, f.name")


def write_tsv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    head = ["process", "location", "flow", "flow_type", "is_input", "amount", "distribution", "parameter1", "parameter2",
            "pedigree"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\t".join(head) + "\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")


def report_datasets(db, factors=None):
    files = [factors] if factors else sorted(glob.glob(os.path.join(ROOT, "data", "factors", "*.json")))
    if not files:
        sys.exit("no factor file in data/factors/: extract the factors first (docs/RUNBOOK.md, section 4)")
    entries = json.load(open(files[-1], encoding="utf-8"))["factors"]
    ids = sorted({e["id"] for e in entries.values() if e.get("id")})
    quoted = ", ".join("'" + i.replace("'", "") + "'" for i in ids)
    (rows,) = db.query(exchanges_sql(f"p.ref_id in ({quoted})"))
    out = os.path.join(ROOT, "results", "database_audit", "datasets.tsv")
    write_tsv(out, rows)
    print(f"{len(ids)} datasets, {len(rows)} exchanges written to {out}")
    print("This file is content of the database: it stays on your computer (results/ is not committed).")


def report_process(db, name):
    like = name.lower().replace("'", "")
    desc, rows = db.query(f"select name, cast(description as varchar(4000)) from tbl_processes where lower(name) like '%{like}%'",
                          exchanges_sql(f"lower(p.name) like '%{like}%'"))
    for r in desc:
        print(r[0] + "\n    " + (r[1] if len(r) > 1 else ""))
    out = os.path.join(ROOT, "results", "database_audit", "process.tsv")
    write_tsv(out, rows)
    print(f"{len(rows)} exchanges written to {out}")


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True, help="database folder of openLCA, or a .zolca file")
    ap.add_argument("--libs", default=None, help="folder with the Derby jars of openLCA")
    ap.add_argument("--factors", default=None, help="factor file for `datasets` (default: the newest in data/factors/)")
    ap.add_argument("report", choices=["counts", "signs", "datasets", "process", "sql"])
    ap.add_argument("argument", nargs="?", help="NAME for `process`, the query for `sql`")
    args = ap.parse_args()
    if args.report in ("process", "sql") and not args.argument:
        ap.error(f"`{args.report}` needs an argument")
    return args


def main():
    args = parse_args()
    db = Database(args.db, args.libs)
    try:
        if args.report == "counts":
            report_counts(db)
        elif args.report == "signs":
            report_signs(db)
        elif args.report == "datasets":
            report_datasets(db, args.factors)
        elif args.report == "process":
            report_process(db, args.argument)
        else:
            for row in db.query(args.argument)[0]:
                print("\t".join(row))
    finally:
        db.close()


if __name__ == "__main__":
    main()

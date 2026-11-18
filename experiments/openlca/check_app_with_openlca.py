"""Use the app as a person would, from the form to openLCA, for a product that is not a container.

    python experiments/openlca/check_app_with_openlca.py            # openLCA open, IPC server on 8080
    python experiments/openlca/check_app_with_openlca.py --offline  # only the steps that need no openLCA

The script starts the app on this computer, then presses its buttons through the same web
interface the browser uses:

  1. searches the openLCA database for a process;
  2. fills the form with two products described by processes of the database (the cotton bag and
     the polypropylene bag of data/examples/) and presses Compare; the factors of those processes
     are NOT in the factor file the app starts with, so the app has to read them from openLCA itself;
  3. answers the first question and skips the others until the app finishes;
  4. opens the two reports the app wrote;
  5. presses "Send to openLCA" and reads the comparison of openLCA's result with BRANCH's.

It works on a copy of the factor file, so the real file is not changed, and it deletes from openLCA
the two processes and product systems it sent. It prints one line per step and ends with
ALL STEPS PASSED, or stops at the first step that fails and says why.
"""
import argparse
import json
import os
import re
import shutil
import socket
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

INPUT_HEADERS = ["what it is for", "stage", "openLCA process (exact name)", "smallest amount", "largest amount"]
BOM_HEADERS = ["component", "material", "mass (g)"]
SERVICE = "carrying the shopping of one household for one year"
UNITS_B = 4


def fail(step, why):
    sys.exit(f"\nFAILED at step {step}: {why}")


def rows_of(example):
    with open(os.path.join(ROOT, "data", "examples", example), encoding="utf-8") as fh:
        spec = json.load(fh)
    rows = [[e["id"], e["stage"].replace("_", " "), e["process"], e["amount"][0], e["amount"][1]]
            for e in spec["exchanges"]]
    return spec["name"], rows


def table(headers, rows):
    return {"headers": headers, "data": rows, "metadata": None}


def texts(result):
    return [x for x in result if isinstance(x, str) and x.strip()]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip the steps that need openLCA")
    ap.add_argument("--port", type=int, default=8080, help="openLCA IPC server port")
    return ap.parse_args()


def factors_for_the_check(offline):
    """A copy of the factor file in a folder of its own, set as the file of the app. Returns (folder, copy).

    Online, the factors of the processes chosen by name are taken out, so the app must read them itself."""
    from branch.factors import load_factors
    real = load_factors()
    work = tempfile.mkdtemp(prefix="branch_app_check_")
    copy = os.path.join(work, os.path.basename(real["path"]))
    with open(real["path"], encoding="utf-8") as fh:
        data = json.load(fh)
    chosen = sorted(k for k in data["factors"] if k.startswith("proc:"))
    if not offline:
        data["factors"] = {k: v for k, v in data["factors"].items() if not k.startswith("proc:")}
    with open(copy, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.environ["BRANCH_FACTORS"] = copy
    os.environ["BRANCH_HOME"] = work
    os.environ.pop("BRANCH_DEMO", None)
    print(f"factor file for this check: a copy with {len(data['factors'])} factors "
          f"({'kept' if offline else 'removed'} the {len(chosen)} factors of processes chosen by name)")
    return work, copy


SENT_KINDS = ("ProductSystem", "Process", "Flow")


def openlca_before(port):
    """(client, the identifiers already in the database), so that only what this check sends is removed."""
    from branch import connector
    ready, _ = connector.status(port)
    if not ready:
        fail(0, "openLCA is not connected. In openLCA: open the database, then Tools > Developer tools > "
                "IPC Server > Start.")
    import olca_schema as o
    c = connector.client(port)
    return c, {kind: {d.id for d in c.get_descriptors(getattr(o, kind))} for kind in SENT_KINDS}


def start_app():
    """(the page, a client of its API)."""
    try:
        from gradio_client import Client
    except ImportError:
        fail(0, 'the app is not installed in this Python environment. Run: pip install -e ".[app]"')
    from branch import webapp
    port = free_port()
    ui = webapp.build_ui()
    ui.launch(server_name="127.0.0.1", server_port=port, prevent_thread_lock=True, inbrowser=False, quiet=True)
    return ui, Client(f"http://127.0.0.1:{port}/", verbose=False)


def step_search(app, offline):
    if offline:
        print("1. search: skipped (offline)")
        return
    found = app.predict("cotton textile", api_name="/on_find")
    if "Textile, woven cotton, at plant" not in found or "| kg |" not in found:
        fail(1, f"the search did not list the cotton textile process with its unit:\n{found}")
    print("1. search: found 'Textile, woven cotton, at plant', amounts in kg")


def step_compare(app, copy, offline):
    """Fill the two forms and press Compare. Returns (what the page answered, the two product names)."""
    from branch import webapp
    name_a, rows_a = rows_of("cotton_bag.json")
    name_b, rows_b = rows_of("pp_bag.json")
    # four polypropylene bags for the use of one cotton bag: close enough for BRANCH to have to ask
    r = app.predict("PT", name_a, 1, False, table(BOM_HEADERS, []), 1, table(INPUT_HEADERS, rows_a),
                    name_b, 1, False, table(BOM_HEADERS, []), UNITS_B, table(INPUT_HEADERS, rows_b),
                    SERVICE, "Climate change", "cut-off", False, api_name="/on_start")
    said = texts(r)
    if any(t.startswith("**Please check:**") for t in said):
        fail(2, next(t for t in said if t.startswith("**Please check:**")))
    with open(copy, encoding="utf-8") as fh:
        now = json.load(fh)["factors"]
    needed = webapp.missing_process_keys(
        [webapp.spec_from_fields(name_a, 1, False, [], inputs=rows_a),
         webapp.spec_from_fields(name_b, 1, False, [], used_ids={"cotton_bag"}, inputs=rows_b)], {"factors": {}})
    missing = [k for k in needed if k not in now]
    if missing:
        fail(2, f"the app started without reading these factors: {missing}")
    print(f"2. Compare: the app {'had' if offline else 'read from openLCA'} the factors of "
          f"{len(needed)} processes and started the session")
    return r, (name_a, name_b)


def reports_in(result):
    return [x for x in result if isinstance(x, list) and x and all(isinstance(f, str) for f in x)]


def answer_next(app, r, said, asked):
    """Answer the first question with the middle of its typical range, skip the others."""
    question = next(t for t in said if t.startswith("### "))
    label = next((x.get("label") for x in r if isinstance(x, dict) and x.get("visible") and
                  str(x.get("label", "")).startswith("Your answer")), None)
    m = re.search(r"typical: ([0-9.eE+-]+) to ([0-9.eE+-]+)", label or "")
    if asked == 1 and m:
        value = (float(m.group(1)) + float(m.group(2))) / 2
        print(f"3. question 1: {question[4:].splitlines()[0][:90]}  -> answered {value:g}")
        return app.predict(None, value, api_name="/answer")
    print(f"3. question {asked}: {question[4:].splitlines()[0][:90]}  -> I don't know")
    return app.predict(None, None, api_name="/skip")


def step_questions(app, r):
    """Go through the questions until the reports arrive. Returns the files of the reports."""
    asked, said = 0, texts(r)
    while not reports_in(r) and asked < 40 and any(t.startswith("### ") for t in said):
        asked += 1
        r = answer_next(app, r, said, asked)
        said = texts(r)
        if any(t.startswith("**") and "Give an answer" in t for t in said):
            fail(3, "the app refused a valid answer")
    files = reports_in(r)
    if not files:
        r = app.predict(api_name="/on_finish")
        said, files = texts(r), reports_in(r)
    if not files:
        fail(3, f"the session did not end with the two reports. The app said: {said[:2]}")
    if asked == 0:
        fail(3, "BRANCH asked nothing, so the questions were not exercised")
    print(f"3. session finished after {asked} question(s)")
    return files[0]


def step_reports(files, names):
    pdf = next((f for f in files if f.lower().endswith(".pdf")), None)
    md = next((f for f in files if f.lower().endswith(".md")), None)
    if not pdf or not md or os.path.getsize(pdf) < 2000:
        fail(4, f"the reports are missing or empty: {files}")
    with open(md, encoding="utf-8") as fh:
        report = fh.read()
    for needle in (*names, SERVICE, "material", "transport"):
        if needle not in report:
            fail(4, f"the technical report does not mention {needle!r}")
    with open(pdf, "rb") as fh:
        if fh.read(5) != b"%PDF-":
            fail(4, "the manager report is not a PDF")
    print(f"4. reports: manager PDF ({os.path.getsize(pdf) // 1024} kB) and technical report name both "
          "products, the service and the stages")


def step_send(app, c, before):
    """Send to openLCA, read its answer, and remove from the database what this check sent."""
    import olca_schema as o
    first = app.predict(False, api_name="/on_send")
    if "backup" not in first.lower():
        fail(5, f"the app sent without the backup confirmed:\n{first}")
    sent = app.predict(True, api_name="/on_send")       # this check runs on a database kept for it
    rels = [float(x) for x in re.findall(r"\| ([0-9.eE+-]+)% \|", sent)]
    if "**Sent to openLCA**" not in sent or len(rels) != 2:
        fail(5, f"openLCA did not confirm the two products:\n{sent}")
    if max(rels) > 1e-4:                    # per cent
        fail(5, f"openLCA and BRANCH differ:\n{sent}")
    print(f"5. Send to openLCA: both products calculated there; largest difference {max(rels):.2g}%")
    removed = 0
    for kind in SENT_KINDS:
        for d in c.get_descriptors(getattr(o, kind)):
            if d.id not in before[kind] and (d.name or "").startswith("BRANCH | "):
                c.delete(d)
                removed += 1
    print(f"   removed from openLCA the {removed} objects this check sent")


def main():
    args = parse_args()
    work, copy = factors_for_the_check(args.offline)
    c, before = (None, None) if args.offline else openlca_before(args.port)
    ui, app = start_app()
    try:
        step_search(app, args.offline)
        r, names = step_compare(app, copy, args.offline)
        step_reports(step_questions(app, r), names)
        if args.offline:
            print("5. Send to openLCA: skipped (offline)")
        else:
            step_send(app, c, before)
    finally:
        ui.close()
        shutil.rmtree(work, ignore_errors=True)
    print("\nALL STEPS PASSED" + (" (offline: steps 1 and 5 and the reading of factors were skipped)"
                                 if args.offline else ""))


if __name__ == "__main__":
    main()

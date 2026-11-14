"""Smoke test of a running app (demo numbers): one whole comparison through its web interface.

    python packaging/smoke_session.py http://127.0.0.1:7860

Used by the installers workflow on the built application, so a packaging mistake (a missing
data folder, a missing report library) fails the build instead of reaching a user. It checks
the version on the page, runs the default comparison, skips every question and opens the
manager report.
"""
import os
import re
import sys

from gradio_client import Client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def expected_version():
    with open(os.path.join(ROOT, "pyproject.toml")) as fh:
        return re.search(r'^version = "([^"]+)"', fh.read(), re.M).group(1)


def table(headers, rows):
    return {"headers": headers, "data": rows, "metadata": None}


def main(url):
    app = Client(url, verbose=False)
    page = str(app.config)
    version = expected_version()
    if f"Version {version}" not in page:
        sys.exit(f"the page does not show version {version}")
    for needed in ("corrugated board", "Search the openLCA database"):
        if needed not in page:
            sys.exit(f"the page lacks {needed!r}: a data folder or the new form is missing from the build")
    bom = ["component", "material", "mass (g)"]
    inputs = table(["what it is for", "stage", "openLCA process (exact name)", "smallest amount", "largest amount"],
                   [["", "", "", None, None]])
    r = app.predict("PT", "PET single use", 1, False, table(bom, [["bottle", "pet", 32.0], ["cap", "hdpe", 2.0]]), 1,
                    inputs, "Refillable glass", 1, True, table(bom, [["bottle", "glass", 450.0]]), 1, inputs,
                    "", "Climate change", "cut-off", False, api_name="/on_start")
    said = [x for x in r if isinstance(x, str)]
    if any(t.startswith("**Please check:**") for t in said):
        sys.exit(next(t for t in said if t.startswith("**Please check:**")))

    def reports(result):
        return [x for x in result if isinstance(x, list) and x and all(isinstance(f, str) for f in x)]

    asked = 0
    while not reports(r) and asked < 40:
        asked += 1
        r = app.predict(None, None, api_name="/skip")
    if not reports(r):
        r = app.predict(api_name="/on_finish")
    files = reports(r)
    if not files or not any(f.lower().endswith(".pdf") and os.path.getsize(f) > 2000 for f in files[0]):
        sys.exit("the comparison did not end with the manager report (PDF)")
    print(f"version {version} on the page; default comparison finished after {asked} skipped question(s); "
          "manager report written")


if __name__ == "__main__":
    main(sys.argv[1])

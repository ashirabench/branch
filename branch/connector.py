"""BRANCH for openLCA: the link between the app and the openLCA running on the same computer.

openLCA offers external tools one official door, its IPC server (Tools > Developer tools >
IPC Server). Through it the connector:

  1. checks that openLCA is open and answering;
  2. reads, once, the unit impact factors of the open database (BAFU:2026) into a folder of
     the user's own computer: the BAFU terms of use do not allow shipping them;
  3. sends a finished comparison back to openLCA, where openLCA builds the product systems,
     calculates them and the result is compared with BRANCH's.
"""
import os
import socket
import sys

PORT = int(os.environ.get("OLCA_PORT", "8080"))

HOW_TO_START = (
    "1. Open **openLCA** and double click your database (BAFU:2026) in the Navigation panel.\n"
    "2. In openLCA, choose **Tools > Developer tools > IPC Server**, keep port **8080** and press **Start**.\n"
    "3. Come back here and press **Check again**.")

GET_BAFU = ("BRANCH needs the free BAFU:2026 database in openLCA (openLCA Nexus, nexus.openlca.org), "
            "with the openLCA LCIA methods (EF 3.1).")


def user_dir():
    """Per user folder for factors and reports (never inside the app bundle)."""
    if os.environ.get("BRANCH_HOME"):
        d = os.environ["BRANCH_HOME"]
    elif sys.platform == "darwin":
        d = os.path.expanduser("~/Library/Application Support/BRANCH")
    elif sys.platform.startswith("win"):
        d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BRANCH")
    else:
        d = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "branch")
    os.makedirs(d, exist_ok=True)
    return d


def factors_dir():
    d = os.path.join(user_dir(), "factors")
    os.makedirs(d, exist_ok=True)
    return d


def port_open(port=PORT, timeout=1.0):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def client(port=PORT):
    import olca_ipc as ipc
    return ipc.Client(port)


def status(port=PORT):
    """(ready: bool, message in Markdown)."""
    if not port_open(port):
        return False, "**openLCA is not connected.**\n\n" + HOW_TO_START
    try:
        import olca_schema as o
        c = client(port)
        n = len(c.get_descriptors(o.Process))
    except Exception as exc:  # server up but no database, or another program on the port
        return False, (f"**Something answers on port {port}, but not an openLCA database** ({exc}).\n\n"
                       + HOW_TO_START)
    if n == 0:
        return False, "**openLCA is connected, but the open database has no processes.** " + GET_BAFU
    return True, f"**openLCA is connected** ({n:,} processes in the open database)."


MARKER_PROCESS = "Polyethylene terephthalate, granulate, bottle grade, at plant"
SETUP_STEPS = (
    ("openLCA is open and its IPC server is started",
     "Install openLCA (free, openlca.org/download) and open it. Then choose **Tools > Developer tools > "
     "IPC Server**, keep port **8080** and press **Start**."),
    ("A database is open in openLCA",
     "Double click your database in the Navigation panel of openLCA."),
    ("The open database is BAFU:2026 with the EF 3.1 method",
     GET_BAFU + " In openLCA, import the database with **File > Import**, then open it."),
    ("BRANCH has read the impact factors",
     "Press **Read factors from openLCA** below (once, about 15 minutes)."),
)


def probe(port=PORT, method="EF 3.1"):
    """What the open openLCA answers: {"port", "processes", "method", "marker"} (False where it fails)."""
    out = {"port": port_open(port), "processes": 0, "method": False, "marker": False}
    if not out["port"]:
        return out
    try:
        import olca_schema as o
        from .olca_extract import norm
        c = client(port)
        procs = c.get_descriptors(o.Process)
        out["processes"] = len(procs)
        out["marker"] = any(norm(MARKER_PROCESS) in norm(d.name) for d in procs)
        out["method"] = any(norm(method) in norm(d.name) for d in c.get_descriptors(o.ImpactMethod))
    except Exception:
        pass
    return out


def checklist(port=PORT, state=None, factors=False):
    """The four steps before the first comparison: [(done, title, what to do)].

    A step counts as done only when every step before it is done, so the first step
    still to do is always the next thing to do. Steps 1 to 3 are read from openLCA
    (`state`, see probe, replaces the live check in the tests); `factors` says whether
    the app has real factors loaded."""
    st = probe(port) if state is None else state
    raw = [bool(st["port"]), st["processes"] > 0, bool(st["marker"] and st["method"]),
           bool(factors)]
    steps, ok = [], True
    for (title, todo), done in zip(SETUP_STEPS[:3], raw[:3]):
        ok = ok and done
        steps.append((ok, title, todo))
    # The factors stay on this computer, so step 4 can be done while openLCA is closed.
    steps.append((raw[3], *SETUP_STEPS[3]))
    return steps


def checklist_markdown(port=PORT, state=None, factors=False):
    steps = checklist(port, state, factors)
    nxt = next((i for i, (done, _, _) in enumerate(steps) if not done), None)
    lines = []
    for i, (done, title, todo) in enumerate(steps):
        mark = "done" if done else ("**do this now**" if i == nxt else "to do")
        lines.append(f"{i + 1}. {title}: {mark}." + (f" {todo}" if i == nxt else ""))
    if nxt is None:
        lines.append("\nEverything is ready. You can compare now.")
    elif steps[3][0] and nxt < 3:
        lines.append("\nThe factors are already loaded, so you can compare now. "
                     "openLCA is only needed to send a comparison back to it.")
    return "\n".join(lines)


def search_processes(text, port=PORT, limit=15):
    """Processes of the open database whose name contains every word of `text`:
    [{"name", "location", "unit", "category"}], shortest names first. The unit is the one the
    amounts must be given in (reference flow of the process). Needs openLCA connected."""
    import olca_schema as o
    from .olca_extract import loc, norm
    words = norm(text).split()
    if not words:
        return []
    c = client(port)
    hits = [d for d in c.get_descriptors(o.Process) if all(w in norm(d.name) for w in words)]
    hits.sort(key=lambda d: (len(d.name or ""), d.name or "", loc(d)))
    out = []
    for d in hits[:limit]:
        unit = ""
        try:
            proc = c.get(o.Process, d.id)
            ref = next((e for e in proc.exchanges or [] if e.is_quantitative_reference), None)
            unit = ref.unit.name if ref and ref.unit else ""
        except Exception:
            pass
        out.append({"name": d.name, "location": loc(d), "unit": unit, "category": d.category or ""})
    return out


def read_process_factors(keys, path=None, port=PORT, method="EF 3.1", progress=print):
    """Add the factors of processes chosen by name (builder.process_key) to the factor file
    at `path` (default: the connector's own file), keeping every factor already in it.
    Returns (path, {key: candidates or reason} for the keys that were not found)."""
    from .olca_extract import extract
    path = path or os.path.join(factors_dir(), "bafu2026_factors.json")
    out = extract(client(port), path, method=method, database="bafu2026", all_grids=False,
                  keys=list(keys), update=True, progress=progress)
    return path, {k: v for k, v in out["unresolved"].items() if k in set(keys)}


def read_factors(port=PORT, method="EF 3.1", progress=print):
    """Extract every factor BRANCH uses from the open openLCA database. Returns (path, summary)."""
    from .olca_extract import extract
    path = os.path.join(factors_dir(), "bafu2026_factors.json")
    out = extract(client(port), path, method=method, database="bafu2026", all_grids=True, progress=progress)
    n, bad = len(out["factors"]), len(out["unresolved"])
    summary = f"Read {n} factors from openLCA ({out['method']})."
    if bad:
        summary += (f" {bad} datasets were not found: {', '.join(sorted(out['unresolved'])[:6])}"
                    f"{'...' if bad > 6 else ''}. " + GET_BAFU)
    return path, summary


def send(model, result, port=PORT):
    """Push the comparison to openLCA and check it there. Returns a Markdown summary."""
    from .olca_bridge import push_comparison
    out = push_comparison(client(port), model, result)
    lines = ["**Sent to openLCA**, folder **BRANCH**: " + ", ".join(p.name for p in out["processes"]) + ".", "",
             "| Product | openLCA | BRANCH | Difference |", "|---|---|---|---|"]
    check = out["check"] or {}
    if "error" in check:
        return lines[0] + f"\n\nopenLCA could not check it: {check['error']}"
    for label, chk in check.items():
        rel = chk.get("relative_difference")
        lines.append(f"| {label} | {chk['openLCA']:.4g} | {chk['BRANCH']:.4g} | "
                     f"{'n/a' if rel is None else f'{100 * rel:.3g}%'} |")
    lines += ["", "In openLCA: refresh the Navigation panel (F5) and open **Product systems > BRANCH**."]
    return "\n".join(lines)

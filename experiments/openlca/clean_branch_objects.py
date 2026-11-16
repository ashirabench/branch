"""Remove from the open openLCA database what BRANCH wrote into it.

    python experiments/openlca/clean_branch_objects.py            # only lists what it would delete
    python experiments/openlca/clean_branch_objects.py --delete   # deletes after you type yes

It touches only product systems, processes and flows whose name starts with "BRANCH | " or
"BRANCH check | "; a process or flow that openLCA reports in another folder is left alone. Nothing of the database
itself is touched. The order is systems, processes, flows, because openLCA refuses to delete an
object that another one still uses. Needs openLCA open with its IPC server started.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import olca_schema as o  # noqa: E402

from branch import olca_bridge  # noqa: E402

PREFIXES = ("BRANCH | ", "BRANCH check | ")


def ours(d, need_folder):
    if not (d.name or "").startswith(PREFIXES):
        return False
    folder = getattr(d, "category", None) or ""
    return not need_folder or not folder or folder == olca_bridge.CATEGORY


def find(c):
    """[(kind, [descriptors])] in the order in which they can be deleted."""
    return [(kind.__name__, [d for d in c.get_descriptors(kind) if ours(d, need_folder)])
            for kind, need_folder in ((o.ProductSystem, False), (o.Process, True), (o.Flow, True))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    c = olca_bridge.client(args.port)
    found = find(c)
    for kind, items in found:
        print(f"{len(items):5d} {kind}")
    total = sum(len(items) for _, items in found)
    if not args.delete or not total:
        print("Nothing deleted." + ("" if not total else " Add --delete to remove them."))
        return
    if input(f"Delete these {total} objects from the open database? This cannot be undone. Type yes: ").strip() != "yes":
        print("Nothing deleted.")
        return
    failed = 0
    for kind, items in found:
        for d in items:
            try:
                c.delete(d)
            except Exception:
                failed += 1
    left = sum(len(items) for _, items in find(c))
    print(f"Deleted {total - left} objects; {left} remain" + (f" ({failed} refused by openLCA)." if failed else "."))


if __name__ == "__main__":
    main()

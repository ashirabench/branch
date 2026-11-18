"""What the scripts that check BRANCH against openLCA share: connect, find the cause of a difference,
remove what was written, save the table."""
import csv
import os
import sys

import olca_schema as o

from branch import olca_bridge

NOT_ANSWERING = ("openLCA is not answering. In openLCA: open the database, then "
                 "Tools > Developer tools > IPC Server > Start.")
DIFFERENT = 1e-4          # a relative difference above this is looked into, exchange by exchange


def connect(port):
    """The client of openLCA, after one call that shows it answers."""
    c = olca_bridge.client(port)
    try:
        c.get_descriptors(o.UnitGroup)
    except Exception as exc:   # whatever the failure, it means the same to the person: the server is not on
        sys.exit(f"{NOT_ANSWERING} ({exc})")
    return c


def cause_of(c, model, result, label):
    """Which exchanges explain a difference: each one alone in openLCA against BRANCH."""
    diag = olca_bridge.diagnose_in_openlca(c, model, result, labels=[label])
    return "; ".join(f"{k} x{ol / br:.3g}" for k, ol, br, r in diag.get(label, []) if r and r > DIFFERENT and br)


def remove(c, sent):
    """Take out of the database what one push_comparison wrote."""
    for ref in sent["systems"] + sent["processes"] + sent.get("flows", []):
        try:
            c.delete(ref)
        except Exception as exc:       # said, not hidden: what stays in the database must be known
            print(f"  could not remove {getattr(ref, 'name', ref)} from openLCA: {exc}")


def save(rows, path, fields=None):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)

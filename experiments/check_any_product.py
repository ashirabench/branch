"""Try, against the open openLCA database, what the app does for a product that is not a container:
search a process by words, read the factor of a process chosen by name, and explain a name that
several locations share. Prints what it finds; changes only the factor file (new factors are added).

    python experiments/check_any_product.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from branch import connector, webapp  # noqa: E402
from branch.builder import process_key  # noqa: E402
from branch.real_cases import load_factors  # noqa: E402


def main():
    ready, msg = connector.status()
    print(msg)
    if not ready:
        sys.exit(1)
    for words in ("cotton textile", "tap water user", "laptop computer"):
        print(f"\nsearch: {words}")
        print(webapp.search_text(connector.search_processes(words, limit=8)))

    path = load_factors()["path"]
    before = set(load_factors()["factors"])
    chosen = [process_key("Viscose fibres, at plant"), process_key("Tap water, at user"),
              process_key("This process does not exist")]
    _, bad = connector.read_process_factors(chosen, path)
    after = load_factors()["factors"]
    print("\nfactors kept:", before <= set(after), "| added:", sorted(set(after) - before))
    for key in chosen:
        if key in after:
            f = after[key]
            print(f"read: {f['process']} [{f['location']}], per {f['unit']}, "
                  f"climate change {f['impacts'].get('Climate change'):.4g}")
    print("\nnot read, as the app would say it:")
    print(webapp.explain_unresolved(bad) if bad else "(nothing)")


if __name__ == "__main__":
    main()

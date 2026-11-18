"""Interactive BRANCH session in the terminal (human study prototype).

    python examples/demo_cli.py                      # real factors, Portugal
    python examples/demo_cli.py --region DE
    python examples/demo_cli.py --toy                # placeholder toy case
    python examples/demo_cli.py --a aluminium_can_330ml --b beverage_carton_1l
    python examples/demo_cli.py --a my_product.json --b data/benchmark/pet_bottle_1l.json
    python examples/demo_cli.py --push                 # send the result to openLCA
    python examples/demo_cli.py --push --defaults      # no questions: every default kept (validation)

The real case needs the factors extracted by experiments/openlca/extract_factors.py.
Writes outputs/report.md.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from branch.agent import ask_human_cli, ask_public_comparison, run_agent  # noqa: E402
from branch.cases import toy_packaging  # noqa: E402
from branch.real_cases import compare  # noqa: E402
from branch.report import markdown_report  # noqa: E402


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", "--country", dest="region", default="PT",
                    help="region code from data/regions/ (PT, DE, BR, BR-N, BR-AM, ...)")
    ap.add_argument("--category", default="Climate change")
    ap.add_argument("--a", default="pet_bottle_1l", help="product A: benchmark name or JSON file")
    ap.add_argument("--b", default="glass_refillable_1l", help="product B: benchmark name or JSON file")
    ap.add_argument("--toy", action="store_true")
    ap.add_argument("--push", action="store_true",
                    help="send the resolved comparison to the open openLCA database and check it there")
    ap.add_argument("--jsonld", help="also save it as an openLCA JSON-LD zip at this path")
    ap.add_argument("--port", type=int, default=8080, help="openLCA IPC server port")
    ap.add_argument("--diagnose", action="store_true",
                    help="with --push: check every exchange alone in openLCA to explain a difference")
    ap.add_argument("--backup-confirmed", dest="backup_confirmed", action="store_true",
                    help="with --push: the open database is a copy or has a backup (otherwise the demo asks)")
    ap.add_argument("--defaults", action="store_true",
                    help="ask nothing: keep every default (used to check BRANCH against openLCA)")
    return ap.parse_args()


def connect(args):
    """The client of openLCA when something will be sent to it, checked before any question is asked."""
    if not (args.push or args.jsonld) or args.toy:
        return None
    from branch import olca_bridge  # needed only to talk to openLCA
    c = olca_bridge.client(args.port)
    try:
        c.get_descriptors(olca_bridge.o.UnitGroup)
    except Exception:          # whatever the failure, it means the server is not on
        sys.exit(f"openLCA is not answering on port {args.port}. In openLCA: open the database, then "
                 "Tools > Developer tools > IPC Server > Start. Then run this command again.")
    return c


def the_model(args):
    if args.toy:
        print("BRANCH: PET single use vs refillable glass, 1 L delivered (PLACEHOLDER toy data)")
        return toy_packaging()
    model = compare(args.a, args.b, args.region, args.category)
    print(f"BRANCH: {model.label_a} vs {model.label_b}, 1 L delivered, {args.region}, "
          f"{args.category} (BAFU:2026 factors)")
    return model


def confirm_backup():
    ok = input("\nBRANCH will write two processes, two flows and two product systems into the database open "
               "in openLCA.\nIs it a copy, or do you have a backup? Type yes to send: ").strip().lower()
    if ok not in ("yes", "y"):
        sys.exit("Nothing was sent. In openLCA: right click the database, Backup database.")


def send(c, args, model, result):
    """Write the comparison into openLCA and print how openLCA's result compares with BRANCH's."""
    from branch import olca_bridge
    out = olca_bridge.push_comparison(c, model, result, jsonld_path=args.jsonld)
    print("\nSent to openLCA (category BRANCH):", ", ".join(p.name for p in out["processes"]))
    for label, chk in (out["check"] or {}).items():
        print(f"  {label}: openLCA {chk.get('openLCA')}, BRANCH {chk.get('BRANCH')}, "
              f"relative difference {chk.get('relative_difference')}")
    if args.diagnose:
        print("\nPer exchange check in openLCA (each exchange alone):")
        for label, rows in olca_bridge.diagnose_in_openlca(c, model, result).items():
            print(f"  {label}")
            for key, olca, branch, rel in rows:
                flag = "   <-- differs" if rel is not None and rel > 1e-4 else ""
                print(f"    {key:45s} openLCA {olca:.6g}  BRANCH {branch:.6g}  rel {rel:.2g}{flag}")


def to_openlca(c, args, model, result):
    if args.toy:
        print("The toy case has no openLCA datasets behind it: nothing to send.")
        return
    if args.push:
        if not args.backup_confirmed:
            confirm_backup()
        send(c, args, model, result)
    else:
        from branch import olca_bridge
        built = olca_bridge.build_objects(c, model, result)
        olca_bridge.write_jsonld(args.jsonld, built.objects, built.created)
    if args.jsonld:
        print(f"Saved {args.jsonld} (import into the database that holds the BAFU processes)")


def main():
    args = parse_args()
    c = connect(args)
    model = the_model(args)
    public = False if args.defaults else ask_public_comparison()
    oracle = (lambda name: None) if args.defaults else ask_human_cli(model)
    result = run_agent(model, oracle, strategy="decision_flip", public_comparison=public)
    report = markdown_report(result, model)
    os.makedirs("outputs", exist_ok=True)
    with open("outputs/report.md", "w") as fh:
        fh.write(report)
    print("\n" + report)
    print("Saved outputs/report.md")
    if args.push or args.jsonld:
        to_openlca(c, args, model, result)


if __name__ == "__main__":
    main()

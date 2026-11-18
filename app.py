"""BRANCH for openLCA, web app.

    python app.py                 # real factors: newest file in data/factors/ or the user folder
    BRANCH_DEMO=1 python app.py   # illustrative numbers

Finds a free port on its own (7860 if free, else the next one), prints the address and
opens it in the browser. docs/RUNBOOK.md, section 5, says how to host it on a server (BRANCH_HOST and PORT).
"""
import os

if __name__ == "__main__":
    if os.environ.get("BRANCH_HOST"):            # server deployment: fixed host and port, no browser
        from branch.webapp import build_ui
        build_ui().launch(server_name=os.environ["BRANCH_HOST"], server_port=int(os.environ.get("PORT", 7860)))
    else:                                        # on a laptop: free port and open the browser
        from branch.desktop import main
        main()

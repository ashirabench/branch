"""BRANCH for openLCA, desktop entry point (the installed app runs this).

Starts the BRANCH page on this computer only (127.0.0.1), on the first free port from
7860, and opens it in the default browser. Nothing leaves the computer: the factors stay
in the user's folder and openLCA is reached through its local IPC server.
"""
import os
import socket
import sys
import webbrowser


def port_free(port):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    if getattr(sys, "frozen", False):          # inside the installed app
        os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
    from branch.webapp import build_ui
    ui = build_ui()
    start = int(os.environ.get("PORT", "7860"))
    for port in range(start, start + 50):
        if not port_free(port):
            continue
        try:
            ui.launch(server_name="127.0.0.1", server_port=port, show_error=True, prevent_thread_lock=True)
        except OSError:                        # taken between the check and the launch
            continue
        url = f"http://127.0.0.1:{port}"
        print(f"\nBRANCH for openLCA is running at {url}\nKeep this window open while you use it; "
              "close it (or press Ctrl+C) to stop BRANCH.\n", flush=True)
        if not os.environ.get("BRANCH_NO_BROWSER"):
            webbrowser.open(url)
        try:
            ui.block_thread()
        except KeyboardInterrupt:
            pass
        return
    raise SystemExit(f"No free port between {start} and {start + 49}.")


if __name__ == "__main__":
    main()

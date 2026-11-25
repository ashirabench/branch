# PyInstaller spec for "BRANCH for openLCA" (macOS .app, Windows folder with .exe, Linux folder).
#
#   pip install -e ".[app,olca,report]" pyinstaller
#   pyinstaller packaging/branch.spec --noconfirm
#
# Output: dist/BRANCH for openLCA/ (and dist/BRANCH for openLCA.app on macOS).
# The BAFU factors are NOT bundled: the app reads them from the user's own openLCA.
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
NAME = "BRANCH for openLCA"

datas, binaries, hidden = [], [], []
for pkg in ("gradio", "gradio_client", "safehttpx", "groovy", "olca_schema", "olca_ipc"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hidden += h
    except Exception:
        pass
datas += collect_data_files("reportlab")
sys.path.insert(0, ROOT)
from branch.paths import RUNTIME_DATA  # noqa: E402  the one list of the data BRANCH reads at run time

for sub in RUNTIME_DATA:
    src = os.path.join(ROOT, "data", sub)
    if os.path.isdir(src):
        datas.append((src, os.path.join("data", sub)))

a = Analysis(
    [os.path.join(ROOT, "packaging", "launch.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    # platformdirs: needed at start by the pkg_resources hook of recent setuptools
    hiddenimports=hidden + ["platformdirs", "branch", "branch.webapp", "branch.connector", "branch.olca_extract",
                            "branch.olca_bridge", "branch.manager_report", "branch.report"],
    excludes=["cupy", "torch", "tensorflow", "IPython", "jupyter", "notebook", "pytest"],
    # gradio reads its own source files at runtime
    module_collection_mode={"gradio": "py", "gradio_client": "py"},
    noarchive=False,
)
pyz = PYZ(a.pure)
# UTF-8 mode: on Windows the app then reads and prints every text as UTF-8, whatever the console uses
exe = EXE(pyz, a.scripts, [("X utf8_mode=1", None, "OPTION")], exclude_binaries=True, name=NAME, console=True)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
if sys.platform == "darwin":
    app = BUNDLE(coll, name=f"{NAME}.app", bundle_identifier="io.github.ashirabench.branch",
                 info_plist={"CFBundleShortVersionString": "0.2.3", "NSHighResolutionCapable": True})

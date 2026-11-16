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
for sub in ("regions", "materials", "benchmark", "cff"):
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
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=True,
          icon=os.path.join(ROOT, "packaging", "icon.icns" if sys.platform == "darwin" else "icon.ico")
          if os.path.exists(os.path.join(ROOT, "packaging", "icon.ico")) else None)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
if sys.platform == "darwin":
    app = BUNDLE(coll, name=f"{NAME}.app", bundle_identifier="org.branch.openlca",
                 info_plist={"CFBundleShortVersionString": "0.2.1", "NSHighResolutionCapable": True})

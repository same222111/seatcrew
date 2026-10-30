# PyInstaller spec for the SeatCrew desktop app (Windows / macOS / Linux).
#   pip install ".[desktop]" pyinstaller  &&  pyinstaller packaging/seatcrew.spec --noconfirm
# Output: dist/SeatCrew/ (folder app; Linux/Windows) and dist/SeatCrew.app (macOS).
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
ROOT = Path(SPECPATH).parent
ICON = {"win32": "icon.ico", "darwin": "icon.icns"}.get(sys.platform, "icon.png")

datas = [(str(ROOT / "seatcrew" / d), f"seatcrew/{d}") for d in ("web", "locales", "templates", "assets")]
datas += [(str(ROOT / "examples" / "trading" / "tradecrew" / d), f"tradecrew/{d}") for d in ("web", "locales")]
for ex in ("trading", "content_review", "support_triage"):  # workflow files are loaded by path at runtime
    for f in (ROOT / "examples" / ex).rglob("*"):
        if f.is_file() and "tests" not in f.parts and "__pycache__" not in f.parts and f.suffix in (".py", ".yaml", ".json", ".md"):
            datas.append((str(f), str(Path("seatcrew_examples") / f.relative_to(ROOT / "examples").parent)))
datas += collect_data_files("webview")

hidden = collect_submodules("seatcrew") + collect_submodules("tradecrew") + ["seatcrew_examples", "yaml"]
if sys.platform.startswith("linux"): hidden += ["webview.platforms.qt", "qtpy", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore", "PyQt6.QtWebChannel"]
elif sys.platform == "win32": hidden += ["webview.platforms.edgechromium", "webview.platforms.winforms"]
else: hidden += ["webview.platforms.cocoa"]

a = Analysis([str(ROOT / "packaging" / "entry.py")], pathex=[str(ROOT), str(ROOT / "examples" / "trading")],
             datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "pytest", "playwright", "IPython", "matplotlib", "gi", "PyQt5", "PySide2", "PySide6"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SeatCrew", console=False, icon=str(ROOT / "packaging" / ICON))
coll = COLLECT(exe, a.binaries, a.datas, name="SeatCrew")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="SeatCrew.app", icon=str(ROOT / "packaging" / "icon.icns"), bundle_identifier="io.github.seatcrew",
                 info_plist={"CFBundleShortVersionString": "0.4.2", "NSHighResolutionCapable": True})

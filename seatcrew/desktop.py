"""SeatCrew desktop app: one double-click, its own window, no terminal.

* picks free ports, starts the local servers in background threads and stops them when the window closes
* first-run wizard (language + optional AI key) and a launcher to choose which workflow to open
* keeps config/state/.env in a per-user data folder (never next to the program)
* window = pywebview (Edge WebView2 on Windows, WebKit on macOS, Qt/GTK on Linux); falls back to the browser

Run:  seatcrew-desktop   |   seatcrew app   |   python -m seatcrew.desktop [--no-window] [--smoke SECONDS]"""
import argparse, json, os, socket, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import __version__, loader
from .config import LANGUAGES, load_env
from .llm import PROVIDERS, key_status

APP = "SeatCrew"
HERE = Path(__file__).parent
ICON = HERE / "assets" / "icon.png"

def data_dir():
    """Per-user folder for config.*.yaml, state/, workflows/ and .env. Override with SEATCREW_HOME."""
    if os.environ.get("SEATCREW_HOME"): d = Path(os.environ["SEATCREW_HOME"])
    elif sys.platform == "win32": d = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP
    elif sys.platform == "darwin": d = Path.home() / "Library" / "Application Support" / APP
    else: d = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "seatcrew"
    d.mkdir(parents=True, exist_ok=True); return d

def free_port(host="127.0.0.1"):
    with socket.socket() as s: s.bind((host, 0)); return s.getsockname()[1]

def workflows(home):
    """Bundled examples + the user's own workflows in <data>/workflows/."""
    out = [dict(name=n, kind="example") for n in loader.list_examples()]
    w = home / "workflows"
    if w.is_dir():
        out += [dict(name=x.name, kind="mine") for x in sorted(w.iterdir()) if x.is_dir() and any((x / f).exists() for f in ("workflow.yaml", "workflow.py"))]
    return out

def save_key(env_path, var, value):
    """Write/replace one KEY=value line in .env (value is never logged or returned)."""
    lines = [l for l in (env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []) if not l.startswith(var + "=")]
    lines.append(f"{var}={value.strip()}"); env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try: os.chmod(env_path, 0o600)
    except OSError: pass
    os.environ[var] = value.strip()

class App:
    def __init__(self, home=None):
        self.home = Path(home).resolve() if home else data_dir()
        self.home.mkdir(parents=True, exist_ok=True)
        os.chdir(self.home)                      # relative config./state/ paths land in the data folder
        load_env(str(self.home / ".env"))
        self.prefs_path = self.home / "desktop.json"
        self.prefs = json.loads(self.prefs_path.read_text(encoding="utf-8")) if self.prefs_path.exists() else {}
        self.open = {}                           # workflow name -> (wf, server, url)
        self.lock = threading.Lock()
        self.launcher = ThreadingHTTPServer(("127.0.0.1", free_port()), self.handler())
        self.url = f"http://127.0.0.1:{self.launcher.server_port}/"

    def save_prefs(self, **kw):
        self.prefs.update(kw); self.prefs_path.write_text(json.dumps(self.prefs, indent=1), encoding="utf-8")

    def info(self):
        return dict(first_run=not self.prefs.get("setup_done"), language=self.prefs.get("language", "en"), languages=LANGUAGES,
                    last=self.prefs.get("last"), workflows=workflows(self.home), data_dir=str(self.home), version=__version__,
                    providers={k: dict(label=v.get("label", k), key_env=v.get("key_env")) for k, v in PROVIDERS.items()},
                    keys=key_status(), running=list(self.open))

    def setup(self, b):
        lang = b.get("language", "en")
        if lang not in LANGUAGES: raise ValueError("unknown language")
        prov, key = b.get("provider"), (b.get("api_key") or "").strip()
        if key:
            env = PROVIDERS.get(prov, {}).get("key_env")
            if not env: raise ValueError("pick a provider for the key")
            save_key(self.home / ".env", env, key)
        self.save_prefs(language=lang, setup_done=True, default_provider=prov if key else None)
        return dict(ok=True, keys=key_status())

    def open_workflow(self, name):
        from .core import Runner
        from .server import serve
        with self.lock:
            if name in self.open: return self.open[name][2]
            if name not in {w["name"] for w in workflows(self.home)}: raise ValueError(f"unknown workflow {name}")
            first = not Path(f"config.{name}.yaml").exists()
            wf = loader.build(name)
            if first:                            # apply wizard choices once; the dashboard owns them afterwards
                patch = {"language": self.prefs.get("language", "en")}
                p = self.prefs.get("default_provider")
                if p: patch["seats"] = {s: {"provider": p} for s in wf.seat_map}
                try: wf.cfg.update(patch)
                except Exception: wf.cfg.update({"language": patch["language"]})
            srv = serve(wf, "127.0.0.1", free_port())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            Runner(wf).start()
            url = f"http://127.0.0.1:{srv.server_port}/?home={self.url}"
            self.open[name] = (wf, srv, url); self.save_prefs(last=name); return url

    def handler(app):
        page = (HERE / "web" / "launcher.html").read_bytes()
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def send(self, obj, code=200, ctype="application/json"):
                b = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False, default=str).encode()
                self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
            def do_GET(self):
                p = self.path.split("?")[0]
                if p in ("/", "/index.html"): return self.send(page, ctype="text/html; charset=utf-8")
                if p == "/icon.png": return self.send(ICON.read_bytes(), ctype="image/png")
                if p == "/api/home": return self.send(app.info())
                self.send({"error": "not found"}, 404)
            def do_POST(self):
                try:
                    b = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                    if self.path == "/api/setup": return self.send(app.setup(b))
                    if self.path == "/api/open": return self.send(dict(ok=True, url=app.open_workflow(b["workflow"])))
                    self.send({"error": "not found"}, 404)
                except (ValueError, KeyError, FileNotFoundError) as e: self.send(dict(ok=False, error=str(e)), 400)
                except Exception as e: self.send(dict(ok=False, error=f"{type(e).__name__}: {e}"), 500)
        return H

    def start(self):
        threading.Thread(target=self.launcher.serve_forever, daemon=True).start(); return self

    def stop(self):
        for wf, srv, _ in self.open.values():
            wf.stop.set(); srv.shutdown(); srv.server_close()
        self.open.clear(); self.launcher.shutdown(); self.launcher.server_close()

def gui_backend():
    """Linux: GTK if PyGObject is present, else Qt (bundled in the AppImage). Win/macOS: pywebview default."""
    if not sys.platform.startswith("linux"): return None
    try: import gi; return "gtk"  # noqa: F401
    except ImportError: return "qt"

def main(argv=None):
    ap = argparse.ArgumentParser(prog="seatcrew-desktop", description="SeatCrew desktop app")
    ap.add_argument("--no-window", action="store_true", help="open in the default browser instead of an app window")
    ap.add_argument("--smoke", type=float, default=0, help="quit automatically after N seconds (CI / tests)")
    ap.add_argument("--open", metavar="WORKFLOW", help="skip the launcher and open this workflow")
    ap.add_argument("--home", help="data folder (default: per-user app data)")
    a = ap.parse_args(argv)
    app = App(a.home).start()
    url = app.open_workflow(a.open) if a.open else app.url
    print(f"{APP} {__version__}  data: {app.home}  url: {url}", flush=True)
    webview = None
    if not a.no_window:
        try: import webview
        except ImportError: print("pywebview not installed - opening your browser instead (pip install pywebview)", flush=True)
    try:
        if webview:
            win = webview.create_window(APP, url, width=1360, height=900, min_size=(900, 600))
            def life():
                if a.smoke: time.sleep(a.smoke); win.destroy()
            webview.start(life, gui=gui_backend(), icon=str(ICON), private_mode=False, storage_path=str(app.home / "webview"))
        else:
            if not a.smoke: webbrowser.open(url)
            t0 = time.time()
            while not a.smoke or time.time() - t0 < a.smoke: time.sleep(0.2)
    except KeyboardInterrupt: pass
    finally:
        app.stop(); print("stopped", flush=True)
    return 0

if __name__ == "__main__": sys.exit(main())

"""SeatCrew desktop app: one double-click, its own window, no terminal.

* picks free ports, starts the local servers in background threads and stops them when the window closes
* first-run wizard (language + optional AI key) and a launcher to choose which workflow to open
* keeps config/state/.env in a per-user data folder (never next to the program)
* window = pywebview (Edge WebView2 on Windows, WebKit on macOS, Qt/GTK on Linux); falls back to the browser

Run:  seatcrew-desktop   |   seatcrew app   |   python -m seatcrew.desktop [--no-window] [--smoke SECONDS]"""
import argparse, json, os, socket, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler
from seatcrew.http import LocalHTTPServer as ThreadingHTTPServer
from pathlib import Path
from . import __version__, loader
from .config import LANGUAGES, load_env
from .llm import PROVIDERS, key_status, test_connection
from .assistant import KEY_LINKS
from . import cli_ai, setup_detect as SD
from .video import localvoice as LV

APP = "SeatCrew"
HERE = Path(__file__).parent
ICON = HERE / "assets" / "icon.png"
NEON = HERE / "web" / "neon.css"

def default_dir():
    """Platform default data folder (also where the pointer file lives)."""
    if sys.platform == "win32": return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP
    if sys.platform == "darwin": return Path.home() / "Library" / "Application Support" / APP
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "seatcrew"

def exe_dir(): return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None

def is_portable():
    d = exe_dir(); return bool(d and ((d / "portable").exists() or (d / "portable.txt").exists()))

def pointer_file():
    """Small JSON file remembering a custom data folder: next to the exe for the portable build, else in the default folder."""
    return (exe_dir() / "location.json") if is_portable() else default_dir() / "location.json"

MOVE_SKIP = {"location.json", "app", "webview"}   # app = install.sh venv on macOS/Linux; webview = browser cache

def data_location():
    """(folder, source). Order: SEATCREW_DATA_DIR env > SEATCREW_HOME (legacy) > pointer file > portable (next to exe) > default."""
    for var in ("SEATCREW_DATA_DIR", "SEATCREW_HOME"):
        if os.environ.get(var): return Path(os.environ[var]).expanduser(), "env"
    try:
        p = pointer_file()
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8")).get("data_dir")
            if d: return Path(d).expanduser(), "custom"
    except (OSError, ValueError): pass
    if is_portable(): return exe_dir() / "data", "portable"
    return default_dir(), "default"

def data_dir():
    """Per-user folder for config.*.yaml, state/, workflows/ (incl. profiles) and .env."""
    d, src = data_location()
    try:
        d.mkdir(parents=True, exist_ok=True)
        if src == "portable": (d / ".w").write_text("", encoding="utf-8"); (d / ".w").unlink()
    except OSError:
        if src != "portable": raise
        d = default_dir(); d.mkdir(parents=True, exist_ok=True)   # read-only portable folder -> fall back
    return d

def pretty(p):
    """Show paths with the home folder as ~ (keeps user names out of screenshots)."""
    try: return "~" + os.sep + str(Path(p).resolve().relative_to(Path.home().resolve()))
    except ValueError: return str(p)

def relocate(cur, new, move):
    """Point the app at a new data folder, optionally moving existing data there. Returns the new folder."""
    if os.environ.get("SEATCREW_DATA_DIR") or os.environ.get("SEATCREW_HOME"): raise ValueError("data folder is set by the SEATCREW_DATA_DIR environment variable")
    new = Path(str(new).strip()).expanduser()
    if not str(new).strip() or not new.is_absolute(): raise ValueError("please give a full folder path, e.g. D:\\SeatCrewData or /home/me/seatcrew")
    cur = Path(cur).resolve(); new = new.resolve()
    if new == cur: return new
    if move and (cur in new.parents): raise ValueError("the new folder cannot be inside the current data folder")
    new.mkdir(parents=True, exist_ok=True)
    probe = new / ".seatcrew-write-test"
    try: probe.write_text("ok", encoding="utf-8"); probe.unlink()
    except OSError as e: raise ValueError(f"cannot write to {new}: {e.strerror}")
    if move:
        import shutil
        for item in list(cur.iterdir()):
            if item.name in MOVE_SKIP or item.resolve() == new: continue
            dst = new / item.name
            if dst.exists(): raise ValueError(f"{dst} already exists - choose an empty folder or untick 'move'")
        for item in list(cur.iterdir()):
            if item.name in MOVE_SKIP or item.resolve() == new: continue
            shutil.move(str(item), str(new / item.name))
    ptr = pointer_file(); ptr.parent.mkdir(parents=True, exist_ok=True)
    natural = (exe_dir() / "data") if is_portable() else default_dir()
    if new == natural.resolve():
        if ptr.exists(): ptr.unlink()
    else: ptr.write_text(json.dumps({"data_dir": str(new)}, indent=1), encoding="utf-8")
    return new

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
        self.fixed_home = bool(home)
        self.open = {}                           # workflow name -> (wf, server, url)
        self.use_home(Path(home).resolve() if home else data_dir())
        self.lock = threading.Lock()
        self.launcher = ThreadingHTTPServer(("127.0.0.1", free_port()), self.handler())
        self.url = f"http://127.0.0.1:{self.launcher.server_port}/"

    def use_home(self, home):
        self.home = Path(home); self.home.mkdir(parents=True, exist_ok=True)
        os.chdir(self.home)                      # relative config./state/ paths land in the data folder
        load_env(str(self.home / ".env"))
        self.prefs_path = self.home / "desktop.json"
        self.prefs = json.loads(self.prefs_path.read_text(encoding="utf-8")) if self.prefs_path.exists() else {}
        self.apply_ai_env()
        from . import assistant as AS
        self.chat = AS.Assistant(self.home / "chat.json", lang=lambda: self.prefs.get("language", "en"), cfg=lambda: None,
                                 wf_dir=self.home / "workflows", taken=lambda: [w["name"] for w in workflows(self.home)],
                                 prefer=lambda: self.prefs.get("default_provider"), demo=lambda: self.prefs.get("ai_mode") == "demo")

    def apply_ai_env(self):
        """Tell every dashboard (same process) which provider CHIEF chat should use, or that demo mode is on."""
        os.environ["SEATCREW_DEMO"] = "1" if self.prefs.get("ai_mode") == "demo" else "0"
        if self.prefs.get("default_provider"): os.environ["SEATCREW_CHAT_PROVIDER"] = self.prefs["default_provider"]
        else: os.environ.pop("SEATCREW_CHAT_PROVIDER", None)

    def close_workflows(self):
        for wf, srv, _ in self.open.values():
            wf.stop.set(); srv.shutdown(); srv.server_close()
        self.open.clear()

    def change_data(self, path, move):
        if self.fixed_home: raise ValueError("data folder was given with --home")
        with self.lock:
            self.close_workflows(); old = self.home
            os.chdir(Path.home())                # release the folder (Windows cannot move the cwd)
            try: new = relocate(old, path, move)
            except Exception: os.chdir(old); raise
            self.use_home(new)
        return dict(ok=True, data_dir=pretty(new), moved=bool(move))

    def save_prefs(self, **kw):
        self.prefs.update(kw); self.prefs_path.write_text(json.dumps(self.prefs, indent=1), encoding="utf-8")

    def info(self):
        return dict(first_run=not self.prefs.get("setup_done"), language=self.prefs.get("language", "en"), languages=LANGUAGES,
                    last=self.prefs.get("last"), workflows=workflows(self.home), data_dir=pretty(self.home),
                    data_source="fixed" if self.fixed_home else data_location()[1], version=__version__,
                    providers={k: dict(label=v.get("label", k), key_env=v.get("key_env")) for k, v in PROVIDERS.items()},
                    keys=key_status(), running=list(self.open), animations=self.prefs.get("animations", True),
                    ai_mode=self.prefs.get("ai_mode", "rules"), default_provider=self.prefs.get("default_provider"), links=KEY_LINKS)

    def setup(self, b):
        lang = b.get("language", "en")
        if lang not in LANGUAGES: raise ValueError("unknown language")
        if b.get("data_dir") and Path(str(b["data_dir"])).expanduser().resolve() != self.home.resolve() and not self.fixed_home:
            self.change_data(b["data_dir"], True)
        prov, key = b.get("provider"), (b.get("api_key") or "").strip()
        mode = b.get("mode") or ("key" if key else "rules")
        if mode not in ("key", "ollama", "demo", "rules", "cli"): raise ValueError("mode must be key, cli, ollama, demo or rules")
        if key:
            env = PROVIDERS.get(prov, {}).get("key_env")
            if not env: raise ValueError("pick a provider for the key")
            save_key(self.home / ".env", env, key)
        chosen = "ollama" if mode == "ollama" else (prov if prov in ("codex_cli", "claude_cli") and key_status().get(prov) else None) if mode == "cli" else (prov if mode == "key" and prov in PROVIDERS and (key or key_status().get(prov)) else None)
        self.save_prefs(language=lang, setup_done=True, default_provider=chosen, ai_mode=mode if chosen or mode in ("demo", "rules") else "rules")
        self.apply_ai_env()
        return dict(ok=True, keys=key_status(), ai_mode=self.prefs["ai_mode"])

    def test_key(self, b):
        """Wizard 'Test connection': real minimal call. A typed key is used only for this call, never saved or returned."""
        prov = b.get("provider")
        if prov not in PROVIDERS: raise ValueError("pick a provider")
        env, key = PROVIDERS[prov]["key_env"], (b.get("api_key") or "").strip()
        with self.lock:
            old = os.environ.get(env) if env else None
            try:
                if env and key: os.environ[env] = key
                return test_connection(prov, {"providers": {}, "llm_limits": {"timeout_sec": 20}}, b.get("model") or None)
            finally:
                if env and key:
                    if old is None: os.environ.pop(env, None)
                    else: os.environ[env] = old

    def open_workflow(self, name):
        from .core import Runner
        from .server import serve
        with self.lock:
            if name in self.open: return self.open[name][2]
            if name not in {w["name"] for w in workflows(self.home)}: raise ValueError(f"unknown workflow {name}")
            first = not Path(f"config.{name}.yaml").exists()
            wf = loader.build(name, str(self.home / f"config.{name}.yaml"), str(self.home / "state" / name))
            if first:                            # apply wizard choices once; the dashboard owns them afterwards
                patch = {"language": self.prefs.get("language", "en")}
                p = self.prefs.get("default_provider")
                if p: patch["seats"] = {s: {"provider": p} for s in wf.seat_map}
                if self.prefs.get("ai_mode") == "demo" and "data" in wf.cfg.data:      # demo mode: offline demo prices
                    try: wf.cfg.update({"data": {"price_source": "demo", "news": []}})
                    except Exception: pass
                try: wf.cfg.update(patch)
                except Exception: wf.cfg.update({"language": patch["language"]})
            try: from tradecrew.seats import Crew          # only the trading example ships tradecrew; a source checkout may not have it on the path
            except ImportError: Crew = None
            if Crew is not None and isinstance(wf, Crew):
                from tradecrew.server import serve as serve_trading
                srv = serve_trading(wf.cfg, wf, "127.0.0.1", free_port())
            else:
                srv = serve(wf, "127.0.0.1", free_port())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            Runner(wf).start()
            url = f"http://127.0.0.1:{srv.server_port}/?home={self.url}"
            self.open[name] = (wf, srv, url); self.save_prefs(last=name); return url

    def detect(self):
        det = SD.detect(self.home); det["recommended"] = SD.recommend(det); return det

    def apply_recommended(self, b):
        """One click: use the recommended (or chosen) chat backend; falls back to demo so the app is usable with zero keys."""
        det = SD.detect(self.home); rec = SD.recommend(det); prov = b.get("provider") or rec["chat_provider"]
        if prov and prov not in PROVIDERS: raise ValueError("unknown provider")
        if prov and not key_status().get(prov): raise ValueError(f"{prov} is not ready - log in or install it first")
        mode = "cli" if prov in ("codex_cli", "claude_cli") else "ollama" if prov == "ollama" else "key" if prov else "demo"
        self.save_prefs(language=b.get("language") or self.prefs.get("language", "en"), setup_done=True, default_provider=prov, ai_mode=mode,
                        voice_backend=rec["voice"])
        self.apply_ai_env(); return dict(ok=True, ai_mode=mode, provider=prov, recommended=rec)

    def handler(app):
        page = (HERE / "web" / "launcher.html").read_bytes()
        from . import assistant as AS
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def send(self, obj, code=200, ctype="application/json"):
                b = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False, default=str).encode()
                self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
            def do_GET(self):
                p = self.path.split("?")[0]
                if p in ("/", "/index.html"): return self.send(page, ctype="text/html; charset=utf-8")
                if p == "/neon.css": return self.send(NEON.read_bytes(), ctype="text/css; charset=utf-8")
                if p == "/setup.js": return self.send((HERE / "web" / "setup.js").read_bytes(), ctype="text/javascript; charset=utf-8")
                if p == "/icon.png": return self.send(ICON.read_bytes(), ctype="image/png")
                if p == "/api/home": return self.send(app.info())
                try:
                    if p == "/api/detect": return self.send(app.detect())
                    if p.startswith("/api/cli-login/"): return self.send(cli_ai.login_job(p.rsplit("/", 1)[1]))
                    if p.startswith("/api/voice-engine/job/"): return self.send(LV.job(p.rsplit("/", 1)[1]))
                    if p == "/api/voice-engines": return self.send(dict(engines=LV.status_all(app.home), clones=LV.list_clones(app.home), consent=LV.CONSENT_TEXT))
                except (cli_ai.CLIError, LV.VoiceEngineError) as e: return self.send(dict(ok=False, error=str(e)), 400)
                st = AS.static(p)
                if st: return self.send(st[0], ctype=st[1])
                r = AS.route(app.chat, "GET", p)
                if r: return self.send(*r)
                self.send({"error": "not found"}, 404)
            def do_POST(self):
                try:
                    b = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                    if self.path == "/api/setup": return self.send(app.setup(b))
                    if self.path == "/api/test-connection": return self.send(app.test_key(b))
                    if self.path == "/api/recommend-apply": return self.send(app.apply_recommended(b))
                    if self.path == "/api/models/key":       # paste a video/voice key: saved to the data folder's .env, never echoed back
                        from .video import providers as PV
                        i = str(b.get("id", "")); val = str(b.get("value", "")).strip()
                        if not any(e["id"] == i for e in PV.CATALOG): raise ValueError("unknown model")
                        var = PV.key_var(i)
                        if not var: raise ValueError("this model needs no key")
                        if not val or len(val) < 8 or any(c.isspace() for c in val): raise ValueError("that does not look like a key")
                        save_key(app.home / ".env", var, val); return self.send(dict(ok=True, var=var, configured=True))
                    if self.path == "/api/cli-login":
                        if b.get("tool") not in cli_ai.TOOLS: raise ValueError("tool must be codex or claude")
                        return self.send(cli_ai.login(b["tool"], bool(b.get("device"))))
                    if self.path == "/api/cli-login/code": return self.send(cli_ai.login_send(b["id"], b.get("code", "")))
                    if self.path == "/api/voice-engine/install":
                        if b.get("engine") not in LV.ENGINES: raise ValueError("unknown engine")
                        return self.send(LV.install(b["engine"], app.home, "cuda" if (SD.gpu() or {}).get("cuda") else "cpu"))
                    if self.path == "/api/voice-engine/plan": return self.send(dict(steps=[" ".join(c)[:300] for c in LV.plan(b["engine"], app.home)]))
                    if self.path == "/api/voice-clone":
                        return self.send(LV.add_clone(app.home, b.get("name", "voice"), b.get("wav_path", ""), b.get("transcript", ""), b.get("consent") is True))
                    r = AS.route(app.chat, "POST", self.path, b)
                    if r: return self.send(*r)
                    if self.path == "/api/prefs":
                        kw = {}
                        if "animations" in b:
                            if not isinstance(b["animations"], bool): raise ValueError("animations must be true or false")
                            kw["animations"] = b["animations"]
                        if "language" in b:
                            if b["language"] not in LANGUAGES: raise ValueError("unknown language")
                            kw["language"] = b["language"]
                        if not kw: raise ValueError("nothing to save (animations or language)")
                        app.save_prefs(**kw); return self.send(dict(ok=True, **kw))
                    if self.path == "/api/datadir": return self.send(app.change_data(b.get("path", ""), bool(b.get("move"))))
                    if self.path == "/api/open": return self.send(dict(ok=True, url=app.open_workflow(b["workflow"])))
                    self.send({"error": "not found"}, 404)
                except (ValueError, KeyError, FileNotFoundError, cli_ai.CLIError, LV.VoiceEngineError) as e: self.send(dict(ok=False, error=str(e)), 400)
                except Exception as e: self.send(dict(ok=False, error=f"{type(e).__name__}: {e}"), 500)
        return H

    def start(self):
        threading.Thread(target=self.launcher.serve_forever, daemon=True).start(); return self

    def stop(self):
        self.close_workflows(); self.launcher.shutdown(); self.launcher.server_close()

def gui_backend():
    """Linux: GTK if PyGObject is present, else Qt (bundled in the AppImage). Win/macOS: pywebview default."""
    if not sys.platform.startswith("linux"): return None
    try: import gi; return "gtk"  # noqa: F401
    except ImportError: return "qt"

def main(argv=None):
    from .textio import utf8_stdio; utf8_stdio()
    ap = argparse.ArgumentParser(prog="seatcrew-desktop", description="SeatCrew desktop app")
    ap.add_argument("--no-window", action="store_true", help="open in the default browser instead of an app window")
    ap.add_argument("--smoke", type=float, default=0, help="quit automatically after N seconds (CI / tests)")
    ap.add_argument("--open", metavar="WORKFLOW", help="skip the launcher and open this workflow")
    ap.add_argument("--home", help="data folder (default: per-user app data)")
    a = ap.parse_args(argv)
    app = App(a.home).start()
    url = app.open_workflow(a.open) if a.open else app.url
    print(f"{APP} {__version__}  data: {app.home}  url: {url}", flush=True)
    if os.environ.get("SEATCREW_URL_FILE"):                   # windowed builds have no console: smoke tests read the url here
        Path(os.environ["SEATCREW_URL_FILE"]).write_text(url, encoding="utf-8")
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

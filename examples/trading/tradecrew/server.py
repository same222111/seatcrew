"""HTTP server: dashboard + JSON API. Binds to 127.0.0.1 by default (no auth - do not expose publicly)."""
import json, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import __version__
from .config import PROVIDERS, SEATS, LANGUAGES, DEFAULT_PROMPTS, key_status
from . import i18n
from .providers import test_connection
from .strategies import STRATEGIES
from . import backtest as BT

WEB = Path(__file__).parent / "web"
from seatcrew.server import NEON  # shared "Night Shift" stylesheet
from seatcrew import assistant as AS

def make_handler(cfg, team):
    lab = dict(running=False, result=None, error=None, log=[])
    import os
    chat = AS.Assistant(Path(getattr(team, "state_dir", "state")) / "chat.json", lang=lambda: cfg.data["language"], cfg=lambda: cfg.data, config=cfg,
                        wf_dir=Path("workflows"), taken=lambda: ["trading", "content_review", "support_triage"],
                        prefer=lambda: os.getenv("SEATCREW_CHAT_PROVIDER"), demo=lambda: os.getenv("SEATCREW_DEMO") == "1")

    def run_lab(kind, body):
        lab.update(running=True, result=None, error=None, log=[])
        try:
            if kind == "backtest": lab["result"] = BT.backtest(body["strategy"], cfg.data, float(body.get("years", 5)), body.get("params") or None)
            else: lab["result"] = BT.research(body["strategy"], cfg.data, int(body.get("rounds", 3)), float(body.get("years", 5)),
                                              log=lambda who, m: (lab["log"].append(f"{who}: {m}"), team.log("scan" if who == "PROPOSER" else "judge", who, m)))
        except Exception as e: lab["error"] = f"{type(e).__name__}: {e}"
        finally: lab["running"] = False

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def send(self, obj, code=200, ctype="application/json"):
            b = obj if isinstance(obj, bytes) else json.dumps(obj, default=str, ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
        def body(self):
            n = int(self.headers.get("Content-Length") or 0); return json.loads(self.rfile.read(n) or b"{}")
        def do_GET(self):
            p = self.path.split("?")[0]
            if p in ("/", "/index.html"): return self.send((WEB / "index.html").read_bytes(), ctype="text/html; charset=utf-8")
            if p == "/neon.css": return self.send(NEON.read_bytes(), ctype="text/css; charset=utf-8")
            if p == "/api/state": return self.send(team.snapshot())
            st = AS.static(p)
            if st: return self.send(st[0], ctype=st[1])
            r = AS.route(chat, "GET", p)
            if r: return self.send(*r)
            if p == "/api/config": return self.send(dict(config=cfg.data, keys=key_status(), providers=PROVIDERS, seats=SEATS, languages=LANGUAGES,
                                                          default_prompts=DEFAULT_PROMPTS, strategies={k: v["label"] for k, v in STRATEGIES.items()}, version=__version__))
            if p == "/api/lab": return self.send(lab)
            if p.startswith("/api/locale/"): return self.send(i18n.load(p.rsplit("/", 1)[1]))
            self.send({"error": "not found"}, 404)
        def do_POST(self):
            p = self.path
            try:
                b = self.body()
                r = AS.route(chat, "POST", p, b)
                if r: return self.send(*r)
                if p == "/api/config":
                    cfg.update(b); team.log("chief", "CONFIG", "settings saved: " + ", ".join(b)); team.wake.set(); return self.send(dict(ok=True, config=cfg.data))
                if p == "/api/test-connection": return self.send(test_connection(b["provider"], cfg.data, b.get("model") or None))
                if p in ("/api/backtest", "/api/research"):
                    if lab["running"]: return self.send(dict(ok=False, error="a lab job is already running"), 409)
                    threading.Thread(target=run_lab, args=(p.rsplit("/", 1)[1], b), daemon=True).start(); return self.send(dict(ok=True))
                if p == "/api/scan": team.wake.set(); return self.send(dict(ok=True))
                if p == "/api/reset": team.reset(); team.wake.set(); return self.send(dict(ok=True))
                self.send({"error": "not found"}, 404)
            except ValueError as e: self.send(dict(ok=False, error=str(e)), 400)
            except Exception as e: self.send(dict(ok=False, error=f"{type(e).__name__}: {e}"), 500)
    return H

def serve(cfg, team, host="127.0.0.1", port=8787):
    srv = ThreadingHTTPServer((host, port), make_handler(cfg, team)); return srv

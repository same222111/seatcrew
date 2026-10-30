"""Generic dashboard server for ANY workflow: seat grid, per-item check-chain timeline, live log, settings,
submit form and human approval. stdlib only; binds 127.0.0.1 (no auth - do not expose publicly)."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import __version__, i18n
from .config import LANGUAGES
from .llm import PROVIDERS, key_status, test_connection

WEB = Path(__file__).parent / "web"

def make_handler(wf):
    cfg = wf.cfg
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
            if p == "/api/state": return self.send(wf.snapshot())
            if p == "/api/config":
                c = cfg.data
                return self.send(dict(definition=wf.definition(), seats={k: c["seats"][k] for k in wf.seat_map}, language=c["language"],
                                      interval=c[wf.interval_key], auto_run=c.get("auto_run"), settings=c.get("settings", {}),
                                      providers=PROVIDERS, keys=key_status(), languages=LANGUAGES, version=__version__))
            if p.startswith("/api/locale/"): return self.send(i18n.load(p.rsplit("/", 1)[1], wf.locale_dirs))
            self.send({"error": "not found"}, 404)
        def do_POST(self):
            p = self.path
            try:
                b = self.body()
                if p == "/api/config":
                    patch = {k: v for k, v in b.items() if k in ("seats", "language", "settings", "auto_run")}
                    if "interval" in b: patch[wf.interval_key] = int(b["interval"])
                    cfg.update(patch); wf.log("chief", "CONFIG", "settings saved: " + ", ".join(patch)); return self.send(dict(ok=True))
                if p == "/api/test-connection": return self.send(test_connection(b["provider"], cfg.data, b.get("model") or None))
                if p == "/api/submit": it = wf.submit(data=b.get("data") or {}); return self.send(dict(ok=True, id=it["id"]))
                if p == "/api/decide": r = wf.decide(b["id"], b["approve"], b.get("note", "")); return self.send(dict(ok=True, result=r))
                if p == "/api/run": wf.wake.set(); return self.send(dict(ok=True))
                self.send({"error": "not found"}, 404)
            except (ValueError, KeyError, TypeError) as e: self.send(dict(ok=False, error=str(e)), 400)
            except Exception as e: self.send(dict(ok=False, error=f"{type(e).__name__}: {e}"), 500)
    return H

def serve(wf, host="127.0.0.1", port=8800):
    return ThreadingHTTPServer((host, port), make_handler(wf))

"""Generic dashboard server for ANY workflow: seat grid, per-item check-chain timeline, live log, settings,
submit form and human approval. stdlib only; binds 127.0.0.1 (no auth - do not expose publicly)."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import __version__, i18n, profiles as PF
from .config import LANGUAGES
from .llm import PROVIDERS, key_status, test_connection

WEB = Path(__file__).parent / "web"
NEON = WEB / "neon.css"

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
            if p == "/neon.css": return self.send(NEON.read_bytes(), ctype="text/css; charset=utf-8")
            if p == "/api/state": return self.send(wf.snapshot())
            if p == "/api/config":
                c = cfg.data
                return self.send(dict(definition=wf.definition(), seats={k: c["seats"][k] for k in wf.seat_map}, language=c["language"],
                                      interval=c[wf.interval_key], auto_run=c.get("auto_run"), settings=c.get("settings", {}), display=c.get("display", PF.DISPLAY_DEFAULTS),
                                      providers=PROVIDERS, keys=key_status(), languages=LANGUAGES, version=__version__))
            if p == "/api/profiles":
                return self.send(dict(profiles=PF.list_profiles(wf.name), current=PF.current(cfg), defaults=PF.defaults(cfg),
                                      folder=str(PF.folder(wf.name)), schema=PF.SCHEMA, themes=PF.THEMES, densities=PF.DENSITIES))
            if p.startswith("/api/locale/"): return self.send(i18n.load(p.rsplit("/", 1)[1], wf.locale_dirs))
            self.send({"error": "not found"}, 404)
        def do_POST(self):
            p = self.path
            try:
                b = self.body()
                if p == "/api/config":
                    patch = {k: v for k, v in b.items() if k in ("seats", "language", "settings", "auto_run", "display")}
                    if "interval" in b: patch[wf.interval_key] = int(b["interval"])
                    cfg.update(patch); wf.log("chief", "CONFIG", "settings saved: " + ", ".join(patch)); return self.send(dict(ok=True))
                if p == "/api/test-connection": return self.send(test_connection(b["provider"], cfg.data, b.get("model") or None))
                if p == "/api/submit": it = wf.submit(data=b.get("data") or {}); return self.send(dict(ok=True, id=it["id"]))
                if p == "/api/decide": r = wf.decide(b["id"], b["approve"], b.get("note", "")); return self.send(dict(ok=True, result=r))
                if p.startswith("/api/profiles/"):
                    op = p.rsplit("/", 1)[1]; name = (b.get("name") or "").strip()
                    if op == "apply": w = PF.apply(wf, b["data"]); wf.log("chief", "CONFIG", "settings applied from editor"); return self.send(dict(ok=True, warnings=w))
                    if op == "save":
                        w = PF.save(wf, name, b["data"]); PF.apply(wf, b["data"]); wf.log("chief", "CONFIG", f"profile '{name}' saved + applied")
                        return self.send(dict(ok=True, warnings=w, profiles=PF.list_profiles(wf.name)))
                    if op == "load": w = PF.apply(wf, PF.read(wf, name)); wf.log("chief", "CONFIG", f"profile '{name}' loaded"); return self.send(dict(ok=True, warnings=w))
                    if op == "delete": PF.delete(wf, name); return self.send(dict(ok=True, profiles=PF.list_profiles(wf.name)))
                    if op == "reset": PF.reset(wf); wf.log("chief", "CONFIG", "reset to defaults"); return self.send(dict(ok=True))
                    if op == "export":
                        data = PF.read(wf, name) if name and not b.get("data") else (b.get("data") or PF.current(cfg))
                        doc = PF.export(wf, data, name or "current", b.get("author", ""))
                        return self.send(dict(ok=True, file=doc, filename=f"{wf.name}-{PF.safe_name(name or 'current').replace(' ', '_')}.seatcrew.json", code=PF.to_code(doc)))
                    if op == "preview": return self.send(PF.preview(wf, b.get("text", "")))
                    if op == "import":
                        pv = PF.preview(wf, b.get("text", "")); nm = PF.safe_name(name or pv["name"])
                        PF.save(wf, nm, pv["data"])
                        if b.get("apply"): PF.apply(wf, pv["data"])
                        wf.log("chief", "CONFIG", f"profile '{nm}' imported" + (" + applied" if b.get("apply") else ""))
                        return self.send(dict(ok=True, name=nm, applied=bool(b.get("apply")), profiles=PF.list_profiles(wf.name)))
                    return self.send({"error": "not found"}, 404)
                if p == "/api/run": wf.wake.set(); return self.send(dict(ok=True))
                self.send({"error": "not found"}, 404)
            except (ValueError, KeyError, TypeError) as e: self.send(dict(ok=False, error=str(e)), 400)
            except Exception as e: self.send(dict(ok=False, error=f"{type(e).__name__}: {e}"), 500)
    return H

def serve(wf, host="127.0.0.1", port=8800):
    return ThreadingHTTPServer((host, port), make_handler(wf))

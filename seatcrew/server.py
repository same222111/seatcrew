"""Generic dashboard server for ANY workflow: seat grid, per-item check-chain timeline, live log, settings,
submit form and human approval. stdlib only; binds 127.0.0.1 (no auth - do not expose publicly)."""
import json
from http.server import BaseHTTPRequestHandler
from seatcrew.http import LocalHTTPServer as ThreadingHTTPServer
from pathlib import Path
import os
from . import __version__, i18n, profiles as PF, assistant as AS, loader
from .video import voices as VR, characters as CHS, studio_api as SA
from .config import LANGUAGES
from .llm import PROVIDERS, key_status, test_connection

WEB = Path(__file__).parent / "web"
NEON = WEB / "neon.css"

def chat_for(wf, on_change=None):
    """CHIEF chat bound to this workflow (history in its state folder)."""
    def taken():
        w = Path("workflows"); return loader.list_examples() + ([x.name for x in w.iterdir() if x.is_dir()] if w.is_dir() else [])
    return AS.Assistant(wf.state_dir / "chat.json", lang=lambda: wf.cfg.data["language"], cfg=lambda: wf.cfg.data, config=wf.cfg, wf=wf,
                        wf_dir=Path("workflows"), taken=taken, prefer=lambda: os.getenv("SEATCREW_CHAT_PROVIDER"),
                        demo=lambda: os.getenv("SEATCREW_DEMO") == "1", on_change=on_change)

def make_handler(wf):
    cfg = wf.cfg; chat = chat_for(wf)
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
            if p == "/api/sample":
                from .assistant import sample_for
                return self.send(dict(data=sample_for(wf, cfg.data.get("language") or "en")))
            st = AS.static(p)
            if st: return self.send(st[0], ctype=st[1])
            r = AS.route(chat, "GET", p)
            if r: return self.send(*r)
            if p == "/api/config":
                c = cfg.data
                return self.send(dict(definition=wf.definition(), seats={k: c["seats"][k] for k in wf.seat_map}, language=c["language"],
                                      interval=c[wf.interval_key], auto_run=c.get("auto_run"), settings=c.get("settings", {}), display=c.get("display", PF.DISPLAY_DEFAULTS),
                                      providers=PROVIDERS, keys=key_status(), languages=LANGUAGES, version=__version__))
            if p == "/api/profiles":
                return self.send(dict(profiles=PF.list_profiles(wf.name), current=PF.current(cfg), defaults=PF.defaults(cfg),
                                      folder=str(PF.folder(wf.name)), schema=PF.SCHEMA, themes=PF.THEMES, densities=PF.DENSITIES))
            if p.startswith("/api/locale/"): return self.send(i18n.load(p.rsplit("/", 1)[1], wf.locale_dirs))
            if p.startswith("/media/") and hasattr(wf, "media_file") and p.count("/") == 3:
                _, _, iid, name = p.split("/"); f = wf.media_file(iid, name)
                if f: return self.send_file(f)
            if p == "/api/voices" and getattr(wf, "studio", None) == "video": return self.send(VR.api_state(cfg.data.get("language")))
            if getattr(wf, "studio", None) == "video":
                if p in ("/characters", "/characters.html"): return self.send((WEB / "characters.html").read_bytes(), ctype="text/html; charset=utf-8")
                if p == "/characters.js": return self.send((WEB / "characters.js").read_bytes(), ctype="application/javascript; charset=utf-8")
                if p == "/vendor/model-viewer.min.js": return self.send((WEB / "vendor" / "model-viewer.min.js").read_bytes(), ctype="application/javascript; charset=utf-8")
                if p == "/api/characters": return self.send(SA.state(CHS.Store(), cfg.data.get("language")))
                if p.startswith("/cfile/"):
                    f = SA.get_file(CHS.Store(), p)
                    if f: return self.send_file(f)
            if p == "/studio.js" and getattr(wf, "studio", None): return self.send((WEB / "studio.js").read_bytes(), ctype="application/javascript; charset=utf-8")
            self.send({"error": "not found"}, 404)
        def send_file(self, f):
            """Static file with HTTP Range support (video seeking)."""
            size = f.stat().st_size; ct = {".mp4": "video/mp4", ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".glb": "model/gltf-binary"}.get(f.suffix, "application/octet-stream")
            rng = self.headers.get("Range"); start, end = 0, size - 1
            m = __import__("re").match(r"bytes=(\d*)-(\d*)", rng or "")
            if m and (m.group(1) or m.group(2)):
                if m.group(1): start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size - 1
                else: start = max(0, size - int(m.group(2)))
                end = min(end, size - 1)
                if start > end: self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
                self.send_response(206); self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else: self.send_response(200)
            self.send_header("Content-Type", ct); self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(end - start + 1)); self.send_header("Cache-Control", "no-store")
            if "download" in (self.path.split("?", 1) + [""])[1]: self.send_header("Content-Disposition", f'attachment; filename="{f.name}"')
            self.end_headers()
            with open(f, "rb") as fh:
                fh.seek(start); left = end - start + 1
                while left > 0:
                    b = fh.read(min(1 << 16, left))
                    if not b: break
                    try: self.wfile.write(b)
                    except (BrokenPipeError, ConnectionResetError): return
                    left -= len(b)
        def do_POST(self):
            p = self.path
            try:
                b = self.body()
                r = AS.route(chat, "POST", p, b)
                if r: return self.send(*r)
                if p == "/api/config":
                    patch = {k: v for k, v in b.items() if k in ("seats", "language", "settings", "auto_run", "display")}
                    if "interval" in b: patch[wf.interval_key] = int(b["interval"])
                    cfg.update(patch); wf.log("chief", "CONFIG", "settings saved: " + ", ".join(patch)); return self.send(dict(ok=True))
                if p == "/api/test-connection": return self.send(test_connection(b["provider"], cfg.data, b.get("model") or None))
                if p == "/api/submit": it = wf.submit(data=b.get("data") or {}); return self.send(dict(ok=True, id=it["id"]))
                if p == "/api/decide":
                    if type(b.get("pending")) is not int or b["pending"] < 0: raise ValueError("pending gate is required; refresh the item")
                    r = wf.decide(b["id"], b["approve"], b.get("note", ""), expected_pending=b["pending"])
                    return self.send(dict(ok=True, result=r))
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
                        if pv.get("voices"): VR.Library().merge_in(pv["voices"], overwrite=bool(b.get("overwrite_voices")))
                        if b.get("apply"): PF.apply(wf, pv["data"])
                        wf.log("chief", "CONFIG", f"profile '{nm}' imported" + (" + applied" if b.get("apply") else ""))
                        return self.send(dict(ok=True, name=nm, applied=bool(b.get("apply")), profiles=PF.list_profiles(wf.name)))
                    return self.send({"error": "not found"}, 404)
                if p.startswith("/api/voices/") and getattr(wf, "studio", None) == "video":
                    op = p.rsplit("/", 1)[1]; lib = VR.Library()
                    if op == "set":
                        f = {k: b.get(k) for k in VR.FIELDS if k in b}; pr = lib.set(str(b.get("name") or ""), **f)
                        wf.log("chief", "CONFIG", f"voice for {b.get('name')}: {pr['voice']} {pr['rate']:+d}% {pr['pitch']:+d}Hz {pr['style']}"); return self.send(dict(ok=True, profile=pr))
                    if op == "delete": lib.delete(str(b.get("name") or "")); return self.send(dict(ok=True))
                    if op == "audition":
                        f = VR.audition_file(lib, b.get("name"), b.get("preset"), b.get("text"), b.get("emotion"), cfg.data.get("language"))
                        return self.send(f.read_bytes(), ctype="audio/mpeg")
                    return self.send({"error": "not found"}, 404)
                if (p.startswith("/api/characters/") or p.startswith("/api/casts/")) and getattr(wf, "studio", None) == "video":
                    _, _, kind, op = p.split("/", 3); r = SA.post(CHS.Store(), kind, op, b, wf, cfg.data.get("language"))
                    if isinstance(r, tuple): return self.send(r[1], ctype="audio/mpeg")
                    if op in ("create", "sheet", "3d", "lock", "voice", "clone", "save", "import", "shoot"): wf.log("chief", "STUDIO", f"{kind[:-1]} {op}: {b.get('name', '')}")
                    return self.send(r)
                if p == "/api/run": wf.wake.set(); return self.send(dict(ok=True))
                self.send({"error": "not found"}, 404)
            except (ValueError, KeyError, TypeError, FileNotFoundError) as e: self.send(dict(ok=False, error=str(e)), 400)
            except Exception as e: self.send(dict(ok=False, error=f"{type(e).__name__}: {e}"), 500)
    return H

def serve(wf, host="127.0.0.1", port=8800):
    return ThreadingHTTPServer((host, port), make_handler(wf))

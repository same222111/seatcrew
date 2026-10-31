"""Character Studio HTTP API (used by seatcrew/server.py for video workflows). JSON in/out; images travel as data URLs.
Nothing here reads or returns keys - only which backends have one set (true/false)."""
import base64, os, re
from urllib.parse import unquote
from . import characters as CH, voices as VO, imagegen as IG, model3d as M3, lipsync as LS

def _data(url):
    m = re.fullmatch(r"data:[\w/+.-]+;base64,([A-Za-z0-9+/=\s]+)", str(url or ""))
    if not m: raise ValueError("expected a base64 data URL")
    return base64.b64decode(m.group(1))

def backends():
    return dict(image={b: all(bool(os.getenv(e)) for e in envs[:1]) or any(os.getenv(e) for e in envs) for b, envs in IG.ENV.items()},
                model3d={b: bool(os.getenv(e)) for b, e in M3.ENV.items()},
                lipsync={"kling": bool(os.getenv("KLING_API_KEY")), "replicate": bool(os.getenv("REPLICATE_API_TOKEN"))},
                clone={"elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")), "minimax": bool(os.getenv("MINIMAX_API_KEY")), "doubao": bool(os.getenv("VOLC_TTS_API_KEY"))})

def view(st, c):
    base = f"/cfile/{c['slug']}/"; sh = c.get("sheet") or {}
    url = lambda r: base + r if r else ""
    return dict(c, urls=dict(refs=[url(r) for r in c.get("refs") or []], front=url(sh.get("front") or (c.get("refs") or [""])[0]),
                             sheet={k: url(v) for k, v in sh.items() if k != "expressions"}, expressions={k: url(v) for k, v in (sh.get("expressions") or {}).items()},
                             model3d=url(c.get("model3d")), angles=[url(a) for a in c.get("angles") or []], locked=[url(r) for r in c.get("locked_refs") or []]))

def state(st, lang=None):
    lib = VO.Library(); voices = lib.all()
    return dict(characters=[dict(view(st, c), voice_profile=voices.get(c.get("voice") or "")) for c in st.list()], casts=st.casts(), max_cast=CH.MAX_CAST,
                roles=list(CH.ROLES), voices=sorted(n for n in voices if n != "narrator"), presets=[dict(id=p["id"]) for p in VO.presets(lang)], expressions=list(CH.EXPRESSIONS), backends=backends(), genders=list(VO.GENDERS), ages=list(VO.AGES))

def get_file(st, path):
    """/cfile/<slug>/<rel> -> Path (only files inside that character's folder)."""
    parts = unquote(path).split("/", 3)
    if len(parts) < 4: return None
    try: return st.file(parts[2], parts[3])
    except ValueError: return None

def post(st, kind, op, b, wf=None, lang=None):
    n = str(b.get("name") or "").strip()
    if kind == "characters":
        if op == "create":
            photos = [_data(ph) for ph in b.get("photos") or []]
            st.create(n, b.get("description", ""), b.get("gender", ""), b.get("age", ""), b.get("personality", ""), refs=(), photos=len(photos))
            for i, raw in enumerate(photos): st.add_ref(n, data=raw, fname=f"ref{i + 1}")
            return dict(ok=True, character=view(st, st.get(n)))
        if op == "update": return dict(ok=True, character=view(st, st.update(n, **{k: b.get(k) for k in ("description", "personality", "gender", "age")})))
        if op == "delete": st.delete(n); return dict(ok=True)
        if op == "photo": return dict(ok=True, character=view(st, st.add_ref(n, data=_data(b.get("photo")), fname=b.get("filename") or None)))
        if op == "sheet":
            c, info = st.make_sheet(n, b.get("backend") or "auto", b.get("model") or None, allow_draft=b.get("allow_draft", True))
            return dict(ok=True, character=view(st, c), backends=sorted({i["backend"] for i in info}), draft=any(i.get("draft") for i in info))
        if op == "3d": c, info = st.make_3d(n, b.get("backend") or "auto", allow_draft=b.get("allow_draft", True)); return dict(ok=True, character=view(st, c), info=info)
        if op == "angle": return dict(ok=True, character=view(st, st.save_angle(n, b.get("angle", 0), b.get("image"))))
        if op == "lock": return dict(ok=True, character=view(st, st.lock(n, refs=b.get("refs") or None, unlock=bool(b.get("unlock")))))
        if op == "voice":
            f = {k: b.get(k) for k in VO.FIELDS if k in b and k not in ("ref_image",)}
            c, prof = st.bind_voice(n, voice=b.get("voice_from") or None, **f); return dict(ok=True, character=view(st, c), profile=prof)
        if op == "clone":
            import tempfile, pathlib
            with tempfile.TemporaryDirectory() as td:
                p = pathlib.Path(td) / "sample.mp3"; p.write_bytes(_data(b.get("sample")))
                c, prof = st.clone_voice(n, b.get("backend"), p, b.get("voice_id") or None)
            return dict(ok=True, character=view(st, c), profile=prof)
        if op == "audition":
            c = st.get(n); f = VO.audition_file(VO.Library(), c.get("voice") or c["name"], None, b.get("text"), b.get("emotion"), lang)
            return ("audio", f.read_bytes())
    if kind == "casts":
        if op == "save": return dict(ok=True, cast=st.save_cast(n, b.get("members") or [], b.get("plot", ""), b.get("set_sheet", ""), b.get("language", ""), b.get("style", "")))
        if op == "delete": st.delete_cast(n); return dict(ok=True)
        if op == "export": return dict(ok=True, file=st.export_cast(n, images=b.get("images", True)), filename=f"{CH.slug(n)}.cast.json")
        if op == "import":
            try: return dict(ok=True, cast=st.import_cast(b.get("file") or b.get("text"), overwrite=bool(b.get("overwrite"))))
            except (ValueError, TypeError, AttributeError) as e:
                if isinstance(e, ValueError) and not type(e).__name__.startswith("JSON"): raise
                raise ValueError("not a SeatCrew cast file (damaged or not JSON)") from None
        if op == "shoot":
            c = st.cast(n)
            if wf is None: raise ValueError("no video workflow running")
            it = wf.submit(data=dict(topic=b.get("topic") or c.get("plot") or c["name"], notes=b.get("notes") or c.get("plot", ""), cast=c["name"],
                                     template=b.get("template") or "dialogue_scene"))
            return dict(ok=True, id=it["id"])
    raise KeyError(f"unknown {kind} op {op}")

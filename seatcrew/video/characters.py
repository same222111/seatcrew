"""Character Studio: characters (reference photos or a text description -> a consistent character sheet), optional 3D,
"lock" (locked refs go to every shot), a bound voice, and casts (剧组) of up to 5 characters you can save, load and share.

Data (in the data folder, next to voices/characters.yaml):
  characters/<slug>/character.yaml  + refs/*.jpg (your photos)  + sheet/*.png  + model.glb  + angles/*.png
  casts/<slug>.yaml
No keys are ever written here; exports contain no keys and no absolute paths."""
import base64, copy, json, re, shutil, time
from pathlib import Path
import yaml
from . import voices as VO

ROOT = Path("characters"); CASTS = Path("casts")
MAX_CAST = 5; MAX_REFS = 8; MAX_IMAGE = 15 * 1024 * 1024
VIEWS = {"front": "front view, head-and-shoulders portrait, looking at the camera, neutral expression",
         "side": "left side profile view, head-and-shoulders, neutral expression",
         "full": "full-body standing pose, front view, head to toe, arms relaxed"}
EXPRESSIONS = ("happy", "sad", "angry", "surprised", "laughing", "thinking")
ROLES = ("lead", "supporting", "comic", "antagonist", "narrator", "cameo")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")

def slug(name):
    s = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af-]+", "_", str(name).strip()).strip("_")[:40]
    if not s or not VO.NAME_RE.match(str(name).strip()): raise ValueError("name: 1-40 letters, digits, spaces or - (Chinese/Japanese/Korean OK)")
    return s

def _dir(name, root=None): return Path(root or ROOT) / slug(name)
def _clean_text(v, n=400): return re.sub(r"[\x00-\x08\x0b-\x1f]", "", str(v or "")).strip()[:n]

def _scrub(text):
    """Never let a key-looking string into a character/cast file or an export."""
    return re.sub(r"\b(sk-[A-Za-z0-9_\-]{12,}|r8_[A-Za-z0-9]{12,}|AIza[0-9A-Za-z_\-]{20,}|tsk_[A-Za-z0-9_\-]{12,}|msy_[A-Za-z0-9_\-]{12,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]+)", "REMOVED_KEY", text)

class Store:
    def __init__(self, root=None, casts=None, voices=None):
        self.root = Path(root or ROOT); self.casts_dir = Path(casts or CASTS); self.voices = voices
    def lib(self): return VO.Library(self.voices) if self.voices else VO.Library()
    # ---------------- characters ----------------
    def path(self, name): return self.root / slug(name)
    def list(self):
        if not self.root.is_dir(): return []
        return [c for c in (self._read(d) for d in sorted(self.root.iterdir()) if (d / "character.yaml").is_file()) if c]
    def _read(self, d):
        try: c = yaml.safe_load((Path(d) / "character.yaml").read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError): return None
        c["slug"] = Path(d).name; return c
    def get(self, name):
        d = self.path(name)
        if not (d / "character.yaml").is_file(): raise ValueError(f"no character '{name}'")
        return self._read(d)
    def _write(self, c):
        d = self.path(c["name"]); d.mkdir(parents=True, exist_ok=True)
        c = {k: v for k, v in c.items() if k != "slug"}
        (d / "character.yaml").write_text(_scrub(yaml.safe_dump(c, allow_unicode=True, sort_keys=False)), encoding="utf-8"); return self._read(d)
    def create(self, name, description="", gender="", age="", personality="", refs=(), overwrite=False, photos=0):
        name = str(name).strip(); d = self.path(name)
        if (d / "character.yaml").is_file() and not overwrite: raise ValueError(f"character '{name}' already exists")
        if not description and not refs and not photos: raise ValueError("give a text description or at least one reference photo")
        if gender and gender not in VO.GENDERS: raise ValueError(f"gender must be one of {VO.GENDERS}")
        if age and age not in VO.AGES: raise ValueError(f"age must be one of {VO.AGES}")
        c = dict(name=name, description=_clean_text(description, 800), personality=_clean_text(personality), gender=gender or "", age=age or "",
                 refs=[], sheet={}, model3d="", angles=[], locked=False, locked_refs=[], voice="", created=time.strftime("%Y-%m-%d"))
        self._write(c)
        for r in refs: self.add_ref(name, r)
        return self.get(name)
    def update(self, name, **f):
        c = self.get(name)
        for k in ("description", "personality"):
            if k in f and f[k] is not None: c[k] = _clean_text(f[k], 800)
        for k, opts in (("gender", VO.GENDERS), ("age", VO.AGES)):
            if f.get(k):
                if f[k] not in opts: raise ValueError(f"{k} must be one of {opts}")
                c[k] = f[k]
        return self._write(c)
    def delete(self, name):
        d = self.path(name)
        if not d.is_dir(): raise ValueError(f"no character '{name}'")
        shutil.rmtree(d)
    def _save_image(self, name, sub, fname, src=None, data=None):
        d = self.path(name) / sub; d.mkdir(parents=True, exist_ok=True)
        raw = Path(src).read_bytes() if src else data
        if not raw or len(raw) > MAX_IMAGE: raise ValueError("image missing or over 15 MB")
        ext = ".png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg" if raw[:3] == b"\xff\xd8\xff" else ".webp" if raw[8:12] == b"WEBP" else None
        if not ext: raise ValueError("image must be PNG, JPEG or WebP")
        p = d / (re.sub(r"[^\w-]", "_", Path(fname).stem)[:40] + ext); p.write_bytes(raw); return p
    def add_ref(self, name, src=None, data=None, fname=None):
        c = self.get(name)
        if len(c["refs"]) >= MAX_REFS: raise ValueError(f"at most {MAX_REFS} reference photos")
        p = self._save_image(name, "refs", fname or (Path(src).name if src else f"ref{len(c['refs']) + 1}"), src, data)
        rel = p.relative_to(self.path(name)).as_posix()
        if rel not in c["refs"]: c["refs"].append(rel)
        return self._write(c)
    def file(self, name, rel):
        """Absolute path of a character file (refs/, sheet/, angles/, model.glb) - nothing outside the folder."""
        d = self.path(name).resolve(); p = (d / str(rel)).resolve()
        if d not in p.parents or not p.is_file(): return None
        return p
    def abs_refs(self, c, which="locked"):
        d = self.path(c["name"]); lst = c.get("locked_refs") if which == "locked" else c.get("refs")
        return [d / r for r in (lst or []) if (d / r).is_file()]
    # ---------------- sheet / 3D / lock ----------------
    def prompt(self, c, view):
        base = c.get("description") or "the person in the reference photos"
        return (f"Character sheet image of {c['name']}: {base}. {view}. Photorealistic, cinematic lighting, plain light-grey studio background, "
                "same face, hairstyle, outfit and accessories as the reference images, consistent identity, sharp focus, no text, no watermark.")
    def make_sheet(self, name, pref="auto", model=None, expressions=EXPRESSIONS, allow_draft=True):
        """front -> side + full body + expressions, each conditioned on your photos + the front view (consistency)."""
        from . import imagegen as IG
        c = self.get(name); d = self.path(name) / "sheet"; d.mkdir(parents=True, exist_ok=True)
        refs = self.abs_refs(c, "refs"); sheet = {}; info = []
        p, i = IG.generate(self.prompt(c, VIEWS["front"]), d / "front.png", refs, "1:1", pref, model, allow_draft); sheet["front"] = "sheet/" + p.name; info.append(i)
        chain = (refs + [p])[-IG.ADAPTERS.get(i["backend"], IG.OpenAIImage).max_refs:] if i["backend"] != "draft" else refs or [p]
        for v in ("side", "full"):
            p2, i2 = IG.generate(self.prompt(c, VIEWS[v]), d / f"{v}.png", chain, "2:3" if v == "full" else "1:1", pref, model, allow_draft); sheet[v] = "sheet/" + p2.name; info.append(i2)
        sheet["expressions"] = {}
        for e in expressions:
            p3, i3 = IG.generate(self.prompt(c, f"close-up portrait, {e} expression, same lighting"), d / f"expr_{e}.png", chain, "1:1", pref, model, allow_draft)
            sheet["expressions"][e] = "sheet/" + p3.name; info.append(i3)
        c["sheet"] = sheet; c["sheet_backend"] = sorted({x["backend"] for x in info}); c["sheet_draft"] = any(x.get("draft") for x in info)
        return self._write(c), info
    def make_3d(self, name, pref="auto", allow_draft=True):
        from . import model3d as M3
        c = self.get(name); src = self.file(name, (c.get("sheet") or {}).get("full") or (c.get("sheet") or {}).get("front") or (c["refs"] or [""])[0])
        if not src: raise ValueError("make the character sheet (or add a photo) first")
        p, info = M3.make(src, self.path(name) / "model.glb", pref, allow_draft)
        c["model3d"] = "model.glb"; c["model3d_backend"] = info["backend"]; return self._write(c), info
    def save_angle(self, name, angle, data_url):
        """A still rendered from the 3D model in the viewer (posted by the page as a PNG data URL)."""
        m = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", str(data_url or ""))
        if not m: raise ValueError("expected a PNG/JPEG data URL")
        a = int(float(angle)) % 360; c = self.get(name)
        p = self._save_image(name, "angles", f"angle_{a:03d}", data=base64.b64decode(m.group(2))); rel = p.relative_to(self.path(name)).as_posix()
        if rel not in c["angles"]: c["angles"].append(rel)
        return self._write(c)
    def lock(self, name, refs=None, unlock=False):
        """Locked refs (front, side, full body by default) are passed to video providers that accept references, for every shot."""
        c = self.get(name)
        if unlock: c["locked"] = False; c["locked_refs"] = []; return self._write(c)
        sh = c.get("sheet") or {}
        lst = list(refs) if refs else [x for x in (sh.get("front"), sh.get("side"), sh.get("full")) if x] or list(c["refs"][:3])
        lst = [r for r in lst if self.file(name, r)]
        if not lst: raise ValueError("nothing to lock - add a photo or make the sheet first")
        c["locked"] = True; c["locked_refs"] = lst[:4]; c = self._write(c)
        lib = self.lib(); prof = lib.own().get(c.get("voice") or c["name"])
        if prof is not None: lib.set(c.get("voice") or c["name"], ref_image=str(self.path(name) / lst[0]))
        return c
    # ---------------- voice ----------------
    def bind_voice(self, name, voice=None, preset=None, **fields):
        """Bind a Voice Library entry (or a preset) to the character; the profile lives in voices/characters.yaml under the character name."""
        c = self.get(name); lib = self.lib(); vname = c["name"]
        if voice and voice != vname:
            src = lib.get(voice); f = {k: src.get(k) for k in VO.FIELDS if k in src and k != "name"}
            f.update({k: v for k, v in fields.items() if v is not None}); lib.set(vname, **f)
        else:
            if not preset and not fields.get("voice"):                 # no choice made: pick by the character's own gender/age
                for k in ("gender", "age"): fields.setdefault(k, c.get(k) or None)
                if "voice" not in (lib.get(vname) if vname in lib.all() else {}) or not lib.all().get(vname, {}).get("voice"):
                    ps = VO.presets(); g, a = fields.get("gender"), fields.get("age")
                    pick = next((x for x in ps if x.get("gender") == g and x.get("age") == a), None) or next((x for x in ps if x.get("gender") == g), None)
                    if pick: preset = pick["id"]
            lib.set(vname, preset=preset, **{k: v for k, v in fields.items() if v is not None})
        if c.get("locked") and c.get("locked_refs"): lib.set(vname, ref_image=str(self.path(name) / c["locked_refs"][0]))
        c["voice"] = vname; return self._write(c), lib.get(vname)
    def clone_voice(self, name, backend, sample, voice_id=None):
        from . import tts_cloud as TC
        vid = TC.clone(backend, slug(name), sample, voice_id)
        return self.bind_voice(name, backend=backend, **{f"{backend}_voice": vid})
    # ---------------- casts ----------------
    def cast_path(self, name): return self.casts_dir / (slug(name) + ".yaml")
    def casts(self):
        if not self.casts_dir.is_dir(): return []
        out = []
        for f in sorted(self.casts_dir.glob("*.yaml")):
            try: out.append(yaml.safe_load(f.read_text(encoding="utf-8")))
            except yaml.YAMLError: pass
        return [c for c in out if isinstance(c, dict)]
    def cast(self, name):
        f = self.cast_path(name)
        if not f.is_file(): raise ValueError(f"no cast '{name}'")
        return yaml.safe_load(f.read_text(encoding="utf-8"))
    def save_cast(self, name, members, plot="", set_sheet="", language="", style=""):
        name = str(name).strip(); slug(name)
        if not isinstance(members, list) or not members: raise ValueError("a cast needs at least one member")
        if len(members) > MAX_CAST: raise ValueError(f"a cast has at most {MAX_CAST} members")
        out, seen = [], set()
        for m in members:
            m = m if isinstance(m, dict) else dict(character=m); ch = str(m.get("character") or "").strip()
            self.get(ch)
            if ch in seen: raise ValueError(f"{ch} is in the cast twice")
            seen.add(ch); role = str(m.get("role") or "supporting")
            out.append(dict(character=ch, role=role[:40], notes=_clean_text(m.get("notes"), 300)))
        if set_sheet and not Path(set_sheet).is_file(): raise ValueError("set sheet image not found")
        doc = dict(name=name, members=out, plot=_clean_text(plot, 1500), set_sheet=str(set_sheet or ""), language=language or "", style=_clean_text(style, 200))
        self.casts_dir.mkdir(parents=True, exist_ok=True)
        self.cast_path(name).write_text(_scrub(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)), encoding="utf-8"); return doc
    def delete_cast(self, name):
        f = self.cast_path(name)
        if not f.is_file(): raise ValueError(f"no cast '{name}'")
        f.unlink()
    def cast_refs(self, cast):
        """{character: [locked ref paths]} + the set sheet - what VISUALS passes to the video provider."""
        refs = {}
        for m in cast["members"]:
            c = self.get(m["character"]); r = self.abs_refs(c, "locked") or self.abs_refs(c, "refs")
            if r: refs[c["name"]] = [str(x) for x in r]
        return refs
    def export_cast(self, name, images=True):
        """Shareable JSON: cast + characters + voice profiles. No keys, no absolute paths. images=False -> referenced by name only."""
        cast = copy.deepcopy(self.cast(name)); lib = self.lib(); chars = []
        for m in cast["members"]:
            c = self.get(m["character"]); d = self.path(c["name"]); files = {}
            rels = list(c.get("refs") or []) + [v for k, v in (c.get("sheet") or {}).items() if k != "expressions"] + list(((c.get("sheet") or {}).get("expressions") or {}).values()) + list(c.get("angles") or [])
            if images:
                for r in rels:
                    p = d / r
                    if p.is_file(): files[r] = base64.b64encode(p.read_bytes()).decode()
            prof = lib.own().get(c.get("voice") or c["name"]); prof = {k: v for k, v in (prof or {}).items() if k != "ref_image"}
            chars.append(dict(character={k: v for k, v in c.items() if k not in ("slug",)}, voice=prof, images=files))
        ss = cast.get("set_sheet"); set_img = None
        if ss and Path(ss).is_file() and images: set_img = dict(name=Path(ss).name, data=base64.b64encode(Path(ss).read_bytes()).decode())
        cast["set_sheet"] = Path(ss).name if ss else ""
        doc = dict(seatcrew_cast=1, exported=time.strftime("%Y-%m-%d"), images_included=bool(images), cast=cast, characters=chars, set_sheet_image=set_img)
        return json.loads(_scrub(json.dumps(doc, ensure_ascii=False)))
    def import_cast(self, doc, overwrite=False):
        if isinstance(doc, (str, bytes)): doc = json.loads(doc)
        if not isinstance(doc, dict) or doc.get("seatcrew_cast") != 1: raise ValueError("not a SeatCrew cast export")
        lib = self.lib(); names = []
        for ch in doc.get("characters") or []:
            c = dict(ch.get("character") or {}); n = str(c.get("name") or ""); d = self.path(n)
            if (d / "character.yaml").is_file() and not overwrite: names.append(n); continue
            d.mkdir(parents=True, exist_ok=True)
            for rel, b in (ch.get("images") or {}).items():
                rp = Path(rel)
                if rp.is_absolute() or ".." in rp.parts or rp.suffix.lower() not in IMG_EXT or len(rp.parts) != 2 or rp.parts[0] not in ("refs", "sheet", "angles"): continue
                (d / rp.parent).mkdir(parents=True, exist_ok=True); (d / rp).write_bytes(base64.b64decode(b))
            c = {k: c.get(k, v) for k, v in dict(name=n, description="", personality="", gender="", age="", refs=[], sheet={}, model3d="", angles=[], locked=False, locked_refs=[], voice="", created="").items()}
            c["model3d"] = ""; self._write(c)
            if ch.get("voice"): lib.merge_in({n: {k: v for k, v in ch["voice"].items() if k in VO.FIELDS}}, overwrite=overwrite)
            names.append(n)
        cast = doc["cast"]; ss = ""
        if doc.get("set_sheet_image"):
            sd = self.casts_dir / "sets"; sd.mkdir(parents=True, exist_ok=True); nm = re.sub(r"[^\w.-]", "_", doc["set_sheet_image"]["name"])[:60]
            if Path(nm).suffix.lower() in IMG_EXT: (sd / nm).write_bytes(base64.b64decode(doc["set_sheet_image"]["data"])); ss = str(sd / nm)
        return self.save_cast(cast["name"], cast["members"], cast.get("plot", ""), ss, cast.get("language", ""), cast.get("style", ""))

def cast_brief(store, cast):
    """Text block for the WRITER: who is in the cast, roles, personalities."""
    out = []
    for m in cast["members"]:
        c = store.get(m["character"])
        out.append(f"- {c['name']} ({m['role']}): {c.get('description', '')[:160]}. Personality: {c.get('personality') or m.get('notes') or '-'}")
    return "\n".join(out)

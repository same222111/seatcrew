"""`seatcrew video ...` - assemble a finished short from a folder of clips + voice + storyboard, run the quality check,
or scaffold a folder from a template.

  seatcrew video init  my_video --template knowledge_explainer --aspect 9:16
  seatcrew video assemble my_video [-o out.mp4] [--tts auto|elevenlabs|openai|edge] [--voice voice.wav --words words.json]
                                   [--bgm music.mp3] [--aspect 16:9] [--preset slow] [--crf 18] [--allow-draft]
  seatcrew video qc my_video/work/manifest.json
  seatcrew video character create Mia --description "..." --photo me.jpg ; character sheet Mia ; character lock Mia ; character 3d Mia
  seatcrew video cast save Family --member Mia:lead --member Leo:comic ; cast export Family -o family.json ; cast import family.json
  seatcrew video check any.mp4 --storyboard sb.yaml --cast Family [--set-sheet set.jpg]   (QC + continuity on any finished video)
"""
import argparse, json, sys
from pathlib import Path
from . import DRAFT_LABEL
from . import editor as ED, qc as QC, tts as TTS, visuals as VIS, voices as VO
from .ff import FFError, have_ffmpeg
from .storyboard import load_storyboard, find_clip
from .templates import TEMPLATES

def _sb_path(folder, given):
    if given: return Path(given)
    for n in ("storyboard.yaml", "storyboard.yml", "storyboard.json"):
        if (Path(folder) / n).is_file(): return Path(folder) / n
    raise SystemExit(f"no storyboard.yaml in {folder} (run: seatcrew video init {folder})")

INIT_SAMPLE = {   # a real, speakable first video - never placeholder text (it would be read aloud and burned into the frames)
    "en": ("Why is the sky blue?", ["Sunlight looks white, but it is a mix of every color.", "Air molecules scatter short blue waves much more than long red ones.",
            "So blue light reaches your eyes from every part of the sky.", "At sunset, light travels through more air and the blue is scattered away.",
            "That is why sunsets glow orange and red."]),
    "zh-CN": ("天空为什么是蓝色的？", ["阳光看起来是白色的，其实混合了所有颜色。", "空气分子更容易散射波长短的蓝光，红光则很少被散射。",
               "所以无论你看向天空哪里，都有蓝光进入眼睛。", "傍晚时阳光要穿过更厚的空气，蓝光在路上就被散射掉了。", "所以晚霞是橙色和红色的。"]),
}
def default_lang(env=None):
    """Chinese system locale -> Chinese sample + CJK font by default."""
    import os
    env = os.environ if env is None else env
    loc = " ".join(str(env.get(k) or "") for k in ("SEATCREW_LANG", "LC_ALL", "LC_MESSAGES", "LANG")).lower()
    if not loc.strip() and sys.platform == "win32":
        try: import locale; loc = (locale.getlocale()[0] or "").lower()
        except Exception: pass
    return "zh-CN" if ("zh" in loc or "chinese" in loc) else "en"

def init(a):
    d = Path(a.folder); (d / "clips").mkdir(parents=True, exist_ok=True); f = d / "storyboard.yaml"
    if f.exists(): print(f"{f} already exists"); return 1
    lang = a.lang or default_lang(); key = "zh-CN" if lang.startswith("zh") else "en"
    tp = TEMPLATES[a.template]; cams = tp["cameras"]; title, sents = INIT_SAMPLE[key]
    q = lambda x: json.dumps(x, ensure_ascii=False)
    lines = [f"# SeatCrew storyboard ({tp['label']}). One shot = one clip in clips/<id>.mp4|mov|png|jpg (missing clips become labeled DRAFT cards).",
             "# Replace the sample narration with your own sentences; duration is a minimum: the editor stretches a shot to fit its narration.",
             f"title: {q(title)}", f"aspect: \"{a.aspect}\"", f"language: {key}", f"template: {a.template}", "shots:"]
    for i, text in enumerate(sents, 1):
        lines += [f"  - id: s{i:02d}", f"    narration: {q(text)}", f"    caption: \"\"", f"    duration: {tp['shot_sec'][0]}",
                  f"    visual: {q(text)}", f"    camera: {cams[(i - 1) % len(cams)]}", f"    transition: {tp['transition']}"]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"created {f} and {d / 'clips'}/\nnext: seatcrew video assemble {d}   (makes a labeled DRAFT right away; add clips/ for the real one)"); return 0

def _caption_style(sb, a):
    """storyboard caption_style, overridden by --caption-position / --caption-scale."""
    from .subs import caption_style
    cs = dict(sb.get("caption_style") or {})
    if getattr(a, "caption_position", None): cs["position"] = a.caption_position
    if getattr(a, "caption_scale", None) is not None: cs["scale"] = a.caption_scale
    return caption_style(cs)

def assemble(a):
    if not have_ffmpeg(): print("ffmpeg not found"); return 2
    folder = Path(a.folder); sb = load_storyboard(_sb_path(folder, a.storyboard)); aspect = a.aspect or sb["aspect"]
    work = folder / "work"; work.mkdir(parents=True, exist_ok=True); draft = False; shots = []
    import re
    ph = [s["id"] for s in sb["shots"] if re.search(r"<[^<>\n]{3,}>", (s.get("narration") or "") + (s.get("caption") or ""))]
    if ph: print(f"shots {', '.join(ph)} still have template placeholders <...> - write the narration in storyboard.yaml first"); return 1
    a.allow_draft = not a.strict                      # beginners: the first run makes a labeled DRAFT without extra flags
    missing = [s["id"] for s in sb["shots"] if not (s.get("clip") or find_clip(folder, s["id"]))]
    if missing and not a.strict: print(f"no clip for {', '.join(missing)}: using labeled {DRAFT_LABEL} cards (add clips/<id>.mp4 for the real video, or --strict to stop)")
    for s in sb["shots"]:
        clip = Path(s["clip"]) if s.get("clip") else find_clip(folder, s["id"])
        if clip and not clip.is_absolute(): clip = (folder / clip) if not clip.is_file() else clip
        if not clip or not Path(clip).is_file():
            if a.strict: print(f"missing clip for shot {s['id']} (put clips/{s['id']}.mp4 or .png, or drop --strict)"); return 1
            clip = VIS.draft_card(s, work, aspect); draft = True
        shots.append(dict(id=s["id"], clip=str(clip), camera=s["camera"], transition=s["transition"], caption=s["caption"], duration=s["duration"]))
    voice = None; sync = "exact"; silent = False; lib = VO.Library(a.voices_lib, overlay=folder / "characters.yaml")
    if a.voice:
        words = json.loads(Path(a.words).read_text(encoding="utf-8")) if a.words else TTS.estimate(" ".join(s["narration"] for s in sb["shots"]), __import__("seatcrew.video.ff", fromlist=["x"]).duration(a.voice))
        if not a.words: sync = "estimated"
        voice = dict(path=a.voice, words=words)
    else:
        lib = VO.Library(a.voices_lib, overlay=folder / "characters.yaml")
        cast = any(l["speaker"] != "narrator" for s in sb["shots"] for l in s["lines"]) or (folder / "characters.yaml").is_file()
        for sh, s in zip(shots, sb["shots"]):
            if not s["narration"]: continue
            if cast:                                   # character voices: each line with its speaker's persistent profile
                try: p, words, infos = VO.render_lines(s["lines"], work / f"voice_{s['id']}.wav", lib, lang=sb["language"], pref=None if a.tts == "auto" else a.tts, allow_draft=a.allow_draft)
                except (TTS.TTSError, ValueError) as e: print(f"voice for {s['id']}: {e}"); return 1
                sh["audio"], sh["words"], sh["voices"] = p, words, infos
                draft |= any(i["draft"] for i in infos); silent |= any(i.get("voice") == "silent" for i in infos); sync = sync if all(i["sync"] == "exact" for i in infos) else "estimated"
                print(f"  voice {s['id']}: " + " | ".join(f"{i['speaker']}={i['voice']} {i['style']}" for i in infos)); continue
            try: p, words, info = TTS.synth(s["narration"], work / f"voice_{s['id']}", pref=a.tts, voice=a.tts_voice, lang=sb["language"], allow_draft=a.allow_draft, rate=a.tts_rate, pitch=a.tts_pitch)
            except TTS.TTSError as e: print(f"voice for {s['id']}: {e}"); return 1
            sh["audio"], sh["words"] = str(p), words; draft |= bool(info.get("draft")); silent |= info.get("voice") == "silent"; sync = sync if info["sync"] == "exact" else "estimated"
            print(f"  voice {s['id']}: {info['backend']} ({info['sync']} timing)")
    out = Path(a.output or folder / "final.mp4")
    man = ED.assemble(shots, out, work, aspect=aspect, voice=voice, bgm=a.bgm, draft=draft, lang=sb.get("language"), crf=a.crf, preset=a.preset or ("veryfast" if draft else "slow"), workers=4, bgm_gain_db=a.bgm_gain_db, fonts_dir=a.fonts_dir,
                      caption_style=_caption_style(sb, a),
                      speaker_colors={n: p["color"] for n, p in lib.all().items() if p.get("color") and n != "narrator"} if a.speaker_colors and not a.voice else None)
    tot = sum(s["duration"] for s in sb["shots"])
    rep = QC.check(man, dict(total_sec=(min(3, tot), max(600, tot * 2)), sync=sync, silent_draft=silent))
    if silent: print("note: no voice engine for this language - the DRAFT voice is silent. Install edge-tts (pip install edge-tts) for a free real voice.")
    (Path(man["output"]).parent / "quality_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\n{man['output']}  {man['size'][0]}x{man['size'][1]}  {man['total']:.1f}s" + (f"   [{DRAFT_LABEL}]" if draft else ""))
    _print(rep); return 0 if rep["passed"] else 1

def _print(rep):
    for c in rep["checks"]: print(f"  {'OK  ' if c['ok'] else ('FAIL' if c['severity'] == 'fail' else 'WARN')} {c['name']:<18} -> {c['seat']:<8} {c['detail']}")
    print(rep["summary"])

def qc(a):
    p = Path(a.manifest)
    if p.is_dir(): p = p / "work" / "manifest.json"
    elif p.suffix.lower() != ".json": p = p.parent / "work" / "manifest.json"   # final.mp4 -> its folder's manifest
    if not p.is_file(): raise ValueError(f"no manifest at {p} - run `seatcrew video assemble` first")
    man = json.loads(p.read_text(encoding="utf-8")); rep = QC.check(man); _print(rep); return 0 if rep["passed"] else 1

def voices(a):
    lib = VO.Library(a.lib)
    if a.op == "presets":
        for p in VO.presets(a.lang): print(f"  {p['id']:<30} {p['gender']:<7}{p['age']:<8} {p['voice']} rate {p['rate']:+d}% pitch {p['pitch']:+d}Hz {p['style']}")
        return 0
    if a.op == "list":
        for n, p in lib.all().items(): print(f"  {n:<12} {p['voice']} {p['rate']:+d}% {p['pitch']:+d}Hz vol {p['volume']:+d}% style {p['style']} [{p['backend']}] sig {VO.signature(p)}  {p['description']}")
        return 0
    if not a.name: raise ValueError("name a character (or a preset id for audition)")
    if a.op == "delete": lib.delete(a.name); print(f"deleted {a.name}"); return 0
    if a.op == "clone":
        from . import tts_cloud as TC, providers as PV
        if a.backend not in ("elevenlabs", "minimax", "doubao") or not a.sample: raise ValueError("clone needs --backend elevenlabs|minimax|doubao and --sample your_recording.wav (with the speaker's consent)")
        try: vid = TC.clone(a.backend, a.name, a.sample, a.voice_id)
        except PV.ProviderError as e: raise ValueError(str(e))
        p = lib.set(a.name, backend=a.backend, **{f"{a.backend}_voice": vid}); print(f"{a.name}: cloned {a.backend} voice {vid} saved (no key stored)"); return 0
    if a.op == "set":
        p = lib.set(a.name, preset=a.preset, voice=a.voice, backend=a.backend, rate=a.rate, pitch=a.pitch, volume=a.volume, style=a.style, description=a.description,
                    gender=a.gender, age=a.age, color=a.color, openai_voice=a.openai_voice, elevenlabs_voice=a.elevenlabs_voice, lang=a.lang,
                    minimax_voice=a.minimax_voice, doubao_voice=a.doubao_voice, azure_voice=a.azure_voice, ref_image=a.ref_image)
        print(f"{a.name}: {p}"); return 0
    prof = VO.preset(a.name) if "/" in a.name else lib.get(a.name)
    out, inf = VO.audition(VO.clean_profile("x", prof) if "/" in a.name else prof, a.output or f"audition_{a.name.replace('/', '_')}.wav", a.text, a.lang, a.emotion)
    print(f"{out}  ({inf[0]['backend']} {inf[0]['voice']})"); return 0

def models(a):
    from . import providers as PV
    if a.test: r = PV.test_key(a.test); print(("ok: " if r["ok"] else "failed: ") + r["message"]); return 0 if r["ok"] else 1
    rec = PV.recommended(); print(f"Recommended models (checked {PV.CHECKED}; prices are rough - check current pricing)")
    for k, tiers in rec.items():
        print(f"\n[{k}]")
        for t, es in tiers.items():
            for e in es: print(f"  {t:<13} {e['provider']:<28} {e['model']:<26} env {'+'.join(e['env']) or '-':<36} {'set' if e['configured'] and e['env'] else ''}\n                docs {e['docs']}\n                key  {e['key_url']}\n                price {e['pricing']}")
    return 0

def estimate(a):
    from . import providers as PV
    sb = load_storyboard(Path(a.folder) / "storyboard.yaml")
    e = PV.estimate(sb["shots"], a.backend)
    print(f"{a.backend}: {e['shots']} shots, {e['seconds']}s of video, ~${e['usd'] if e['usd'] is not None else '?'} , ~{e['minutes'] or '?'} min ({e['note']}: {e['pricing']})"); return 0

def character(a):
    from . import characters as CH
    st = CH.Store(a.root, a.casts, a.lib); op = a.op
    if op == "list":
        for c in st.list(): print(f"  {c['name']:<16} {'LOCKED ' if c.get('locked') else '       '}refs {len(c.get('refs') or [])} sheet {'yes' if c.get('sheet') else 'no '} 3d {c.get('model3d_backend') or '-':<9} voice {c.get('voice') or '-'}")
        return 0
    if not a.name: raise ValueError("give the character name")
    if op == "create": c = st.create(a.name, a.description or "", a.gender or "", a.age or "", a.personality or "", a.photo or [])
    elif op == "show": c = st.get(a.name)
    elif op == "delete": st.delete(a.name); print("deleted"); return 0
    elif op == "sheet": c, info = st.make_sheet(a.name, a.backend or "auto", a.model, allow_draft=a.allow_draft or True); print("backends:", ", ".join(sorted({i['backend'] for i in info})))
    elif op == "3d": c, info = st.make_3d(a.name, a.backend or "auto"); print("3d:", info["backend"], info.get("note", ""))
    elif op == "lock": c = st.lock(a.name, unlock=a.unlock)
    elif op == "voice": c, prof = st.bind_voice(a.name, voice=a.voice, preset=a.preset); print("voice:", prof.get("preset") or prof.get("backend"))
    elif op == "clone":
        if not (a.backend and a.sample): raise ValueError("clone needs --backend elevenlabs|minimax|doubao and --sample")
        c, prof = st.clone_voice(a.name, a.backend, a.sample, a.voice_id)
    print(json.dumps({k: v for k, v in c.items() if k != "slug"}, ensure_ascii=False, indent=1)); return 0

def cast(a):
    from . import characters as CH
    st = CH.Store(a.root, a.casts, a.lib)
    if a.op == "list":
        for c in st.casts(): print(f"  {c['name']:<16} " + ", ".join(f"{m['character']} ({m['role']})" for m in c["members"]))
        return 0
    if a.op == "import": c = st.import_cast(Path(a.name).read_text(encoding="utf-8"), overwrite=a.overwrite); print(f"imported {c['name']}"); return 0
    if a.op == "save":
        mem = [dict(zip(("character", "role", "notes"), (m.split(":", 2) + ["", ""])[:3])) for m in a.member or []]
        c = st.save_cast(a.name, mem, a.plot or "", a.set_sheet or "")
    elif a.op == "show": c = st.cast(a.name)
    elif a.op == "delete": st.delete_cast(a.name); print("deleted"); return 0
    elif a.op == "export":
        doc = st.export_cast(a.name, images=not a.no_images); out = Path(a.output or f"{CH.slug(a.name)}.cast.json")
        out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8"); print(f"exported -> {out} (no keys; images {'included' if doc['images_included'] else 'not included'})"); return 0
    print(json.dumps(c, ensure_ascii=False, indent=1)); return 0

def check(a):
    """QC any finished video (not made by EDITOR): format, loudness, black/frozen, sharpness + continuity."""
    from . import characters as CH
    from .storyboard import load_storyboard
    sb = load_storyboard(a.storyboard) if a.storyboard else None; refs = None; ss = a.set_sheet
    if a.cast:
        st = CH.Store(a.root, a.casts, a.lib); c = st.cast(a.cast); refs = st.cast_refs(c); ss = ss or c.get("set_sheet") or None
    for r in a.ref or []:
        n, _, p = r.partition("="); refs = refs or {}; refs.setdefault(n, []).append(p)
    rep = QC.check_external(a.video, sb, refs, ss); _print(rep)
    if a.json: Path(a.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0 if rep["passed"] else 1

def main(argv):
    from ..textio import utf8_stdio; utf8_stdio()
    ap = argparse.ArgumentParser(prog="seatcrew video", description="Short-video tools: init a storyboard folder, assemble a finished video, quality-check it.")
    sp = ap.add_subparsers(dest="c", required=True)
    i = sp.add_parser("init", help="create a folder with storyboard.yaml + clips/"); i.add_argument("folder")
    i.add_argument("--template", choices=list(TEMPLATES), default="knowledge_explainer"); i.add_argument("--aspect", choices=["9:16", "16:9"], default="9:16")
    i.add_argument("--lang", help="sample script language: en or zh-CN (zh, zh-TW... map to Chinese; default: your system language)")
    s = sp.add_parser("assemble", help="folder (storyboard.yaml + clips/) -> final.mp4 + quality_report.json"); s.add_argument("folder")
    s.add_argument("--storyboard"); s.add_argument("-o", "--output"); s.add_argument("--aspect", choices=["9:16", "16:9"])
    s.add_argument("--tts", default="auto", choices=["auto", "elevenlabs", "minimax", "doubao", "azure", "openai", "edge", "draft"]); s.add_argument("--tts-voice"); s.add_argument("--tts-rate", help="edge-tts speaking rate, e.g. -8%%"); s.add_argument("--tts-pitch", help="edge-tts pitch, e.g. -2Hz"); s.add_argument("--fonts-dir", help="extra fonts (e.g. Noto Sans SC for Chinese subtitles)")
    s.add_argument("--voices-lib", help="character voice library (default voices/characters.yaml in the data folder)"); s.add_argument("--speaker-colors", action="store_true", help="color subtitles per speaker")
    s.add_argument("--caption-position", choices=["top", "upper", "lower"], help="where shot titles (caption:) go; default top safe area, above faces")
    s.add_argument("--caption-scale", type=float, help="title size multiplier 0.6-2.0 (default 1.0)")
    s.add_argument("--voice", help="your own narration file (instead of TTS)"); s.add_argument("--words", help="word timings JSON [{w,start,end}] for --voice")
    s.add_argument("--bgm", help="background music (ducked under the voice)"); s.add_argument("--bgm-gain-db", type=float)
    s.add_argument("--crf", type=int, default=18); s.add_argument("--preset", help="x264 preset (default: slow, or veryfast for a DRAFT)"); s.add_argument("--allow-draft", action="store_true", help=f"(default now) fill gaps offline; output is labeled {DRAFT_LABEL}")
    s.add_argument("--strict", action="store_true", help="stop on a missing clip / voice instead of making a DRAFT")
    q = sp.add_parser("qc", help="re-run the quality check (video folder, final.mp4 or work/manifest.json)"); q.add_argument("manifest")
    v = sp.add_parser("voices", help="character voice library: presets, characters, audition")
    v.add_argument("op", choices=["presets", "list", "set", "delete", "audition", "clone"]); v.add_argument("name", nargs="?")
    v.add_argument("--lang"); v.add_argument("--preset"); v.add_argument("--voice"); v.add_argument("--backend"); v.add_argument("--rate"); v.add_argument("--pitch")
    v.add_argument("--volume"); v.add_argument("--style"); v.add_argument("--description"); v.add_argument("--gender"); v.add_argument("--age"); v.add_argument("--color")
    v.add_argument("--openai-voice"); v.add_argument("--elevenlabs-voice"); v.add_argument("--text"); v.add_argument("--emotion"); v.add_argument("-o", "--output")
    v.add_argument("--lib", help="library file (default voices/characters.yaml)"); v.add_argument("--minimax-voice"); v.add_argument("--doubao-voice")
    v.add_argument("--azure-voice"); v.add_argument("--ref-image", help="character reference image (for image-to-video consistency)")
    v.add_argument("--sample", help="clone: your recording of the speaker (with consent)"); v.add_argument("--voice-id", help="clone: voice id to create (minimax) / S_ speaker id (doubao)")
    m = sp.add_parser("models", help="recommended video + voice models (links, env vars); --test ID checks a key"); m.add_argument("--test")
    e = sp.add_parser("estimate", help="rough cost/time of generating a folder's shots with a video API"); e.add_argument("folder")
    e.add_argument("--backend", required=True, choices=["kling", "runway", "gemini", "minimax", "luma", "replicate"])
    for n, ops in (("character", ["list", "create", "show", "delete", "sheet", "3d", "lock", "voice", "clone"]), ("cast", ["list", "save", "show", "delete", "export", "import"])):
        c = sp.add_parser(n, help="Character Studio: " + ("characters (photos/description -> sheet, 3D, lock, voice)" if n == "character" else "casts of up to 5 characters"))
        c.add_argument("op", choices=ops); c.add_argument("name", nargs="?"); c.add_argument("--root", help="characters folder (default characters/)")
        c.add_argument("--casts", help="casts folder (default casts/)"); c.add_argument("--lib", help="voice library file")
        if n == "character":
            c.add_argument("--description"); c.add_argument("--personality"); c.add_argument("--gender"); c.add_argument("--age"); c.add_argument("--photo", action="append")
            c.add_argument("--backend"); c.add_argument("--model"); c.add_argument("--allow-draft", action="store_true"); c.add_argument("--unlock", action="store_true")
            c.add_argument("--voice"); c.add_argument("--preset"); c.add_argument("--sample"); c.add_argument("--voice-id")
        else:
            c.add_argument("--member", action="append", help="Name:role[:notes] (up to 5)"); c.add_argument("--plot"); c.add_argument("--set-sheet")
            c.add_argument("-o", "--output"); c.add_argument("--no-images", action="store_true"); c.add_argument("--overwrite", action="store_true")
    k = sp.add_parser("check", help="QC + continuity on any finished video"); k.add_argument("video"); k.add_argument("--storyboard"); k.add_argument("--cast")
    k.add_argument("--set-sheet"); k.add_argument("--ref", action="append", help="Name=image (extra character refs)"); k.add_argument("--json", help="write the report here")
    k.add_argument("--root"); k.add_argument("--casts"); k.add_argument("--lib")
    a = ap.parse_args(argv)
    try: return {"character": character, "cast": cast, "check": check, "init": init, "assemble": assemble, "qc": qc, "voices": voices, "models": models, "estimate": estimate}[a.c](a)
    except (ValueError, FFError) as e: print(f"error: {e}"); return 1
    except Exception as e:
        from .providers import ProviderError
        if isinstance(e, ProviderError): print(f"error: {e}"); return 1
        raise

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))

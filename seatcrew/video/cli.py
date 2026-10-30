"""`seatcrew video ...` - assemble a finished short from a folder of clips + voice + storyboard, run the quality check,
or scaffold a folder from a template.

  seatcrew video init  my_video --template knowledge_explainer --aspect 9:16
  seatcrew video assemble my_video [-o out.mp4] [--tts auto|elevenlabs|openai|edge] [--voice voice.wav --words words.json]
                                   [--bgm music.mp3] [--aspect 16:9] [--preset slow] [--crf 18] [--allow-draft]
  seatcrew video qc my_video/work/manifest.json
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

def init(a):
    d = Path(a.folder); (d / "clips").mkdir(parents=True, exist_ok=True); f = d / "storyboard.yaml"
    if f.exists(): print(f"{f} already exists"); return 1
    tp = TEMPLATES[a.template]; cams = tp["cameras"]
    lines = [f"# SeatCrew storyboard ({tp['label']}). One shot = one clip in clips/<id>.mp4|mov|png|jpg.",
             "# duration is a minimum: the editor stretches a shot to fit its narration.",
             f"title: My {tp['label'].lower()}", f"aspect: \"{a.aspect}\"", "language: en", f"template: {a.template}", "shots:"]
    for i, beat in enumerate(tp["arc"], 1):
        lines += [f"  - id: s{i:02d}", f"    narration: \"<{beat}: one short spoken sentence>\"", f"    caption: \"\"", f"    duration: {tp['shot_sec'][0]}",
                  f"    visual: \"<what the shot shows, for an AI generator>\"", f"    camera: {cams[(i - 1) % len(cams)]}", f"    transition: {tp['transition']}"]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8"); print(f"created {f} and {d / 'clips'}/"); return 0

def assemble(a):
    if not have_ffmpeg(): print("ffmpeg not found"); return 2
    folder = Path(a.folder); sb = load_storyboard(_sb_path(folder, a.storyboard)); aspect = a.aspect or sb["aspect"]
    work = folder / "work"; work.mkdir(parents=True, exist_ok=True); draft = False; shots = []
    for s in sb["shots"]:
        clip = Path(s["clip"]) if s.get("clip") else find_clip(folder, s["id"])
        if clip and not clip.is_absolute(): clip = (folder / clip) if not clip.is_file() else clip
        if not clip or not Path(clip).is_file():
            if not a.allow_draft: print(f"missing clip for shot {s['id']} (put clips/{s['id']}.mp4 or .png, or pass --allow-draft)"); return 1
            clip = VIS.draft_card(s, work, aspect); draft = True
        shots.append(dict(id=s["id"], clip=str(clip), camera=s["camera"], transition=s["transition"], caption=s["caption"], duration=s["duration"]))
    voice = None; sync = "exact"; lib = VO.Library(a.voices_lib, overlay=folder / "characters.yaml")
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
                draft |= any(i["draft"] for i in infos); sync = sync if all(i["sync"] == "exact" for i in infos) else "estimated"
                print(f"  voice {s['id']}: " + " | ".join(f"{i['speaker']}={i['voice']} {i['style']}" for i in infos)); continue
            try: p, words, info = TTS.synth(s["narration"], work / f"voice_{s['id']}", pref=a.tts, voice=a.tts_voice, lang=sb["language"], allow_draft=a.allow_draft, rate=a.tts_rate, pitch=a.tts_pitch)
            except TTS.TTSError as e: print(f"voice for {s['id']}: {e}"); return 1
            sh["audio"], sh["words"] = str(p), words; draft |= bool(info.get("draft")); sync = sync if info["sync"] == "exact" else "estimated"
            print(f"  voice {s['id']}: {info['backend']} ({info['sync']} timing)")
    out = Path(a.output or folder / "final.mp4")
    man = ED.assemble(shots, out, work, aspect=aspect, voice=voice, bgm=a.bgm, draft=draft, crf=a.crf, preset=a.preset, bgm_gain_db=a.bgm_gain_db, fonts_dir=a.fonts_dir,
                      speaker_colors={n: p["color"] for n, p in lib.all().items() if p.get("color") and n != "narrator"} if a.speaker_colors and not a.voice else None)
    tot = sum(s["duration"] for s in sb["shots"])
    rep = QC.check(man, dict(total_sec=(min(3, tot), max(600, tot * 2)), sync=sync))
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

def main(argv):
    ap = argparse.ArgumentParser(prog="seatcrew video", description="Short-video tools: init a storyboard folder, assemble a finished video, quality-check it.")
    sp = ap.add_subparsers(dest="c", required=True)
    i = sp.add_parser("init", help="create a folder with storyboard.yaml + clips/"); i.add_argument("folder")
    i.add_argument("--template", choices=list(TEMPLATES), default="knowledge_explainer"); i.add_argument("--aspect", choices=["9:16", "16:9"], default="9:16")
    s = sp.add_parser("assemble", help="folder (storyboard.yaml + clips/) -> final.mp4 + quality_report.json"); s.add_argument("folder")
    s.add_argument("--storyboard"); s.add_argument("-o", "--output"); s.add_argument("--aspect", choices=["9:16", "16:9"])
    s.add_argument("--tts", default="auto", choices=["auto", "elevenlabs", "minimax", "doubao", "azure", "openai", "edge", "draft"]); s.add_argument("--tts-voice"); s.add_argument("--tts-rate", help="edge-tts speaking rate, e.g. -8%%"); s.add_argument("--tts-pitch", help="edge-tts pitch, e.g. -2Hz"); s.add_argument("--fonts-dir", help="extra fonts (e.g. Noto Sans SC for Chinese subtitles)")
    s.add_argument("--voices-lib", help="character voice library (default voices/characters.yaml in the data folder)"); s.add_argument("--speaker-colors", action="store_true", help="color subtitles per speaker")
    s.add_argument("--voice", help="your own narration file (instead of TTS)"); s.add_argument("--words", help="word timings JSON [{w,start,end}] for --voice")
    s.add_argument("--bgm", help="background music (ducked under the voice)"); s.add_argument("--bgm-gain-db", type=float)
    s.add_argument("--crf", type=int, default=18); s.add_argument("--preset", default="slow"); s.add_argument("--allow-draft", action="store_true", help=f"fill gaps offline; output is labeled {DRAFT_LABEL}")
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
    a = ap.parse_args(argv)
    try: return {"init": init, "assemble": assemble, "qc": qc, "voices": voices, "models": models, "estimate": estimate}[a.c](a)
    except (ValueError, FFError) as e: print(f"error: {e}"); return 1

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))

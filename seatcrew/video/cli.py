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
from . import editor as ED, qc as QC, tts as TTS, visuals as VIS
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
    voice = None; sync = "exact"
    if a.voice:
        words = json.loads(Path(a.words).read_text(encoding="utf-8")) if a.words else TTS.estimate(" ".join(s["narration"] for s in sb["shots"]), __import__("seatcrew.video.ff", fromlist=["x"]).duration(a.voice))
        if not a.words: sync = "estimated"
        voice = dict(path=a.voice, words=words)
    else:
        for sh, s in zip(shots, sb["shots"]):
            if not s["narration"]: continue
            try: p, words, info = TTS.synth(s["narration"], work / f"voice_{s['id']}", pref=a.tts, voice=a.tts_voice, lang=sb["language"], allow_draft=a.allow_draft)
            except TTS.TTSError as e: print(f"voice for {s['id']}: {e}"); return 1
            sh["audio"], sh["words"] = str(p), words; draft |= bool(info.get("draft")); sync = sync if info["sync"] == "exact" else "estimated"
            print(f"  voice {s['id']}: {info['backend']} ({info['sync']} timing)")
    out = Path(a.output or folder / "final.mp4")
    man = ED.assemble(shots, out, work, aspect=aspect, voice=voice, bgm=a.bgm, draft=draft, crf=a.crf, preset=a.preset, bgm_gain_db=a.bgm_gain_db)
    tot = sum(s["duration"] for s in sb["shots"])
    rep = QC.check(man, dict(total_sec=(min(3, tot), max(600, tot * 2)), sync=sync))
    (Path(man["output"]).parent / "quality_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\n{man['output']}  {man['size'][0]}x{man['size'][1]}  {man['total']:.1f}s" + (f"   [{DRAFT_LABEL}]" if draft else ""))
    _print(rep); return 0 if rep["passed"] else 1

def _print(rep):
    for c in rep["checks"]: print(f"  {'OK  ' if c['ok'] else ('FAIL' if c['severity'] == 'fail' else 'WARN')} {c['name']:<18} -> {c['seat']:<8} {c['detail']}")
    print(rep["summary"])

def qc(a):
    man = json.loads(Path(a.manifest).read_text(encoding="utf-8")); rep = QC.check(man); _print(rep); return 0 if rep["passed"] else 1

def main(argv):
    ap = argparse.ArgumentParser(prog="seatcrew video", description="Short-video tools: init a storyboard folder, assemble a finished video, quality-check it.")
    sp = ap.add_subparsers(dest="c", required=True)
    i = sp.add_parser("init", help="create a folder with storyboard.yaml + clips/"); i.add_argument("folder")
    i.add_argument("--template", choices=list(TEMPLATES), default="knowledge_explainer"); i.add_argument("--aspect", choices=["9:16", "16:9"], default="9:16")
    s = sp.add_parser("assemble", help="folder (storyboard.yaml + clips/) -> final.mp4 + quality_report.json"); s.add_argument("folder")
    s.add_argument("--storyboard"); s.add_argument("-o", "--output"); s.add_argument("--aspect", choices=["9:16", "16:9"])
    s.add_argument("--tts", default="auto", choices=["auto", "elevenlabs", "openai", "edge", "draft"]); s.add_argument("--tts-voice")
    s.add_argument("--voice", help="your own narration file (instead of TTS)"); s.add_argument("--words", help="word timings JSON [{w,start,end}] for --voice")
    s.add_argument("--bgm", help="background music (ducked under the voice)"); s.add_argument("--bgm-gain-db", type=float)
    s.add_argument("--crf", type=int, default=18); s.add_argument("--preset", default="slow"); s.add_argument("--allow-draft", action="store_true", help=f"fill gaps offline; output is labeled {DRAFT_LABEL}")
    q = sp.add_parser("qc", help="re-run the quality check on a manifest.json"); q.add_argument("manifest")
    a = ap.parse_args(argv)
    try: return {"init": init, "assemble": assemble, "qc": qc}[a.c](a)
    except (ValueError, FFError) as e: print(f"error: {e}"); return 1

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))

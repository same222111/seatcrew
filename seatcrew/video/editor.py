"""EDITOR: assemble shots + voice (+ music) into a finished short video with ffmpeg.

* 1080x1920 (9:16, default) or 1920x1080 (16:9); 30 fps; H.264 High, CRF 18, preset slow, yuv420p, BT.709, +faststart
* stills get smooth camera motion (Ken Burns, eased, 2x supersampled to avoid jitter); video clips are cover-cropped
* crossfade / fade-through-black / cut between shots
* word-timed karaoke subtitles (ASS, bundled Montserrat ExtraBold, outline + shadow, safe margins) + optional headline captions
* background music ducked under the voice (sidechain compression), faded in/out
* two-pass EBU R128 loudness normalization to -14 LUFS integrated, -1.5 dBTP; AAC 192k 48 kHz
* draft inputs -> a "DRAFT PREVIEW - NOT FINAL QUALITY" banner is burned in and the file name ends in _DRAFT"""
import json, os, re, shutil
from pathlib import Path
from . import ff
from .storyboard import SIZES, is_image
from .subs import build_ass

FONTS = Path(__file__).parent / "fonts"
XF = {"crossfade": "fade", "fade_black": "fadeblack", "cut": "fade"}
LEAD, TAIL = 0.15, 0.35
DEFAULTS = dict(fps=30, crf=18, preset="slow", supersample=2, motion=0.10, transition_sec=0.5, bgm_gain_db=-18.0, lufs=-14.0, true_peak=-1.5, inter_crf=10, room_tone_db=None, reverb=0.0)

def timeline(shots, fps=30, transition_sec=0.5, voice=None):
    """Final duration D_i and start S_i of each shot, plus global word times. Narration never gets cut: a shot is
    stretched to its narration + lead + tail. With one global voice track the planned durations are used as-is."""
    frame = 1 / fps; D, S, t = [], [], 0.0
    for s in shots:
        need = (s.get("audio_dur", 0) + LEAD + TAIL) if s.get("audio") and not voice else 0
        D.append(round(max(float(s["duration"]), need), 3))
    if voice and voice.get("dur"):
        extra = voice["dur"] + 0.4 - sum(D)
        if extra > 0: D[-1] = round(D[-1] + extra, 3)
    for d in D: S.append(round(t, 3)); t += d
    T = [0.0 if i == len(shots) - 1 else (frame if s["transition"] == "cut" else min(transition_sec, D[i] / 3, D[i + 1] / 3)) for i, s in enumerate(shots)]
    words = []
    if voice:
        words = [dict(w, start=w["start"], end=w["end"], shot=_shot_at(S, w["start"])) for w in voice.get("words", [])]
    else:
        for i, s in enumerate(shots):
            off = S[i] + LEAD
            words += [dict(w=w["w"], start=round(off + w["start"], 3), end=round(off + w["end"], 3), shot=i, **({"speaker": w["speaker"]} if w.get("speaker") else {})) for w in s.get("words", [])]
    return dict(D=D, S=S, T=T, total=round(t, 3), words=words, lead=LEAD)

def _shot_at(S, t): return max([i for i, s in enumerate(S) if s <= t + 1e-6] or [0])

def _kb(cam, n, m):
    """zoompan expressions for an eased camera move over n frames."""
    p = f"(on/{max(1, n - 1)})"; e = f"({p}*{p}*(3-2*{p}))"; cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return {"push_in": (f"1+{m}*{e}", cx, cy), "pull_out": (f"{1 + m}-{m}*{e}", cx, cy),
            "pan_left": (f"{1 + m}", f"(iw-iw/zoom)*(1-{e})", cy), "pan_right": (f"{1 + m}", f"(iw-iw/zoom)*{e}", cy),
            "pan_up": (f"{1 + m}", cx, f"(ih-ih/zoom)*(1-{e})"), "pan_down": (f"{1 + m}", cx, f"(ih-ih/zoom)*{e}"),
            # a still image can't be truly static (QC would flag a frozen frame): give it a barely visible drift
            "static": (f"1+{round(m * 0.4, 4)}*{e}", cx, cy)}[cam]

def render_segment(shot, length, out, w, h, o, cwd):
    """One shot -> near-lossless intermediate of exactly `length` seconds. Returns info for QC."""
    fps = o["fps"]; n = max(2, int(round(length * fps))); src = Path(shot["clip"]).resolve(); info = dict(source=src.name)
    vs = ff.vstream(src) or {}; info["src_w"], info["src_h"] = int(vs.get("width", 0)), int(vs.get("height", 0))
    col = f"scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setsar=1"
    if is_image(src):
        ss = max(1, int(o["supersample"])); z, x, y = _kb(shot.get("camera", "push_in"), n, o["motion"])
        vf = (f"scale={w * ss}:{h * ss}:force_original_aspect_ratio=increase:flags=lanczos,crop={w * ss}:{h * ss},"
              f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={w}x{h}:fps={fps},{col}")
        ff.run(["-i", src, "-vf", vf, "-frames:v", n, "-c:v", "libx264", "-preset", "veryfast", "-crf", o["inter_crf"], "-an", out], cwd=cwd)
        info["kind"] = "image"
    else:
        cd = ff.duration(src); info.update(kind="video", clip_dur=round(cd, 3))
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},fps={fps},tpad=stop_mode=clone:stop_duration={max(0, length - cd) + 1:.3f},{col}"
        ff.run(["-i", src, "-vf", vf, "-frames:v", n, "-c:v", "libx264", "-preset", "veryfast", "-crf", o["inter_crf"], "-an", out], cwd=cwd)
        info["short_by"] = round(max(0.0, length - cd), 3)
    return info

def _loudnorm(src, dst, o, cwd):
    err = ff.run(["-i", src, "-af", f"loudnorm=I={o['lufs']}:TP={o['true_peak']}:LRA=11:print_format=json", "-f", "null", "-"], cwd=cwd)
    m = json.loads(re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", err)[-1])
    if m["input_i"] in ("-inf", "inf") or float(m["input_i"]) < -60:            # silence (draft): nothing to normalize
        shutil.copy(Path(cwd) / src, Path(cwd) / dst); return dict(measured=None)
    af = (f"loudnorm=I={o['lufs']}:TP={o['true_peak']}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
          f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
    ff.run(["-i", src, "-af", af, "-ar", "48000", "-ac", "2", dst], cwd=cwd); return dict(measured=float(m["input_i"]))

def assemble(shots, out, work, aspect="9:16", size=None, voice=None, bgm=None, draft=False, captions=True, **opts):
    """shots: [{id, clip, camera, transition, caption, duration, audio?, words?}] (per-shot voice) or pass voice={path, words}.
    Returns a manifest dict (timeline, cues, files) that the QUALITY CHECK reads."""
    o = dict(DEFAULTS, **{k: v for k, v in opts.items() if v is not None}); w, h = size or SIZES[aspect]
    work = Path(work).resolve(); work.mkdir(parents=True, exist_ok=True); out = Path(out).resolve()
    if not shots: raise ValueError("no shots")
    for s in shots:
        if not s.get("clip") or not Path(s["clip"]).is_file(): raise ValueError(f"shot {s.get('id')}: clip missing ({s.get('clip')})")
        if s.get("audio"): s["audio_dur"] = ff.duration(s["audio"])
    if voice: voice = dict(voice, dur=ff.duration(voice["path"]))
    tl = timeline(shots, o["fps"], o["transition_sec"], voice); D, S, T = tl["D"], tl["S"], tl["T"]
    seg_info = []
    for i, s in enumerate(shots):                                  # 1) shots -> segments
        seg_info.append(render_segment(s, D[i] + T[i], f"seg{i:02d}.mp4", w, h, o, str(work)))
    # 2) subtitles
    caps = [(S[i] + 0.1, S[i] + D[i] - 0.15, s.get("caption", "")) for i, s in enumerate(shots)] if captions else []
    from .typography import text_font
    selected_font, family = text_font(" ".join([x["w"] for x in tl["words"]] + [c[2] or "" for c in caps]), [o.get("fonts_dir")])
    ass, cues = build_ass(tl["words"], caps, w, h, tl["total"], font=family, speaker_colors=o.get("speaker_colors"))
    (work / "subs.ass").write_text(ass, encoding="utf-8")
    fd = work / "fonts"; fd.mkdir(exist_ok=True)
    extra = [Path(x) for x in (o.get("fonts_dir"), os.environ.get("SEATCREW_FONTS_DIR")) if x and Path(x).is_dir()]
    for d in [FONTS, *extra]:
        for f in [*d.glob("*.ttf"), *d.glob("*.otf"), *d.glob("*.ttc")]: shutil.copy(f, fd / f.name)
    shutil.copy(selected_font, fd / selected_font.name)
    # 3) audio: voice stem -> (+ducked music) -> loudness
    total = tl["total"]
    if voice:
        ff.run(["-i", voice["path"], "-af", f"aformat=sample_rates=48000:channel_layouts=mono,apad=whole_dur={total},atrim=0:{total}", "-t", f"{total:.3f}", "-ar", "48000", "voice.wav"], cwd=str(work))
    else:
        ins, fl = [], []
        for i, s in enumerate(shots):
            if s.get("audio"):
                ins += ["-i", Path(s["audio"]).resolve()]; ms = int(round((S[i] + LEAD) * 1000))
                fl.append(f"[{len(fl)}:a]aformat=sample_rates=48000:channel_layouts=mono,adelay={ms}:all=1[a{len(fl)}]")
        if fl:
            mix = "".join(f"[a{i}]" for i in range(len(fl)))
            ff.run([*ins, "-filter_complex", ";".join(fl) + f";{mix}amix=inputs={len(fl)}:normalize=0:dropout_transition=0,apad=whole_dur={total},atrim=0:{total}[v]", "-map", "[v]", "-t", f"{total:.3f}", "-ar", "48000", "voice.wav"], cwd=str(work))
        else: ff.run(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", total, "voice.wav"], cwd=str(work))
    if bgm:
        g = o["bgm_gain_db"]; fo = max(0.0, total - 1.5)
        ff.run(["-i", "voice.wav", "-stream_loop", "-1", "-i", Path(bgm).resolve(), "-filter_complex",
                f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v][sc];"
                f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total},volume={g}dB,afade=t=in:d=1,afade=t=out:st={fo}:d=1.5[b];"
                f"[b][sc]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=350[bd];[v][bd]amix=inputs=2:normalize=0:duration=first[m]",
                "-map", "[m]", "-t", total, "mix.wav"], cwd=str(work))
    else: ff.run(["-i", "voice.wav", "-af", "aformat=sample_rates=48000:channel_layouts=stereo", "mix.wav"], cwd=str(work))
    if o.get("room_tone_db") is not None or o.get("reverb"):
        # dialogue scenes: a quiet room bed (pink noise, low-passed) under the voices + a short small-room reflection
        fx = []; ins = ["-i", "mix.wav"]; rv = float(o.get("reverb") or 0)
        if rv > 0: fx.append(f"[0:a]aecho=0.8:{min(0.9, rv * 3):.2f}:23|41|67:{rv:.2f}|{rv * 0.7:.2f}|{rv * 0.45:.2f}[v]")
        else: fx.append("[0:a]anull[v]")
        if o.get("room_tone_db") is not None:
            ins += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anoisesrc=color=pink:amplitude=1:sample_rate=48000:seed=7"]
            fx.append(f"[1:a]lowpass=f=900,highpass=f=60,volume={float(o['room_tone_db']):.1f}dB,aformat=sample_rates=48000:channel_layouts=stereo[rt];[v][rt]amix=inputs=2:duration=first:normalize=0[m]")
        else: fx[-1] = fx[-1][:-3] + "[m]"
        ff.run([*ins, "-filter_complex", ";".join(fx), "-map", "[m]", "-t", f"{total:.3f}", "mix_room.wav"], cwd=str(work))
        (work / "mix_room.wav").replace(work / "mix.wav")
    ln = _loudnorm("mix.wav", "audio.wav", o, str(work))
    # 4) picture: transitions -> subtitles -> (draft banner) -> H.264
    n = len(shots); ins = sum((["-i", f"seg{i:02d}.mp4"] for i in range(n)), []); fl = []; last = "0:v"
    for i in range(1, n):
        fl.append(f"[{last}][{i}:v]xfade=transition={XF[shots[i - 1]['transition']]}:duration={T[i - 1]:.3f}:offset={S[i]:.3f}[x{i}]"); last = f"x{i}"
    chain = f"[{last}]ass=subs.ass:fontsdir=fonts"
    if draft:
        from .visuals import FONT
        chain += (f",drawtext=fontfile=fonts/{FONT.name}:text='DRAFT PREVIEW - NOT FINAL QUALITY':fontsize={round(min(w, h) * 0.034)}:fontcolor=white:"
                  f"box=1:boxcolor=0xff2d55@0.85:boxborderw={round(min(w, h) * 0.018)}:x=(w-tw)/2:y={round(h * 0.035)}")
    fl.append(chain + ",format=yuv420p[vout]")
    final = out if not draft or out.stem.endswith("_DRAFT") else out.with_name(out.stem + "_DRAFT" + out.suffix)
    final.parent.mkdir(parents=True, exist_ok=True)
    ff.run([*ins, "-i", "audio.wav", "-filter_complex", ";".join(fl), "-map", "[vout]", "-map", f"{n}:a", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", o["preset"], "-crf", o["crf"], "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", o["fps"], "-g", int(o["fps"]) * 2,
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", final], cwd=str(work))
    man = dict(output=str(final), size=[w, h], fps=o["fps"], aspect=aspect, total=total, draft=bool(draft), timeline=dict(D=D, S=S, T=T),
               shots=[dict(id=s["id"], start=S[i], dur=D[i], transition=s["transition"], camera=s.get("camera"), seg=str(work / f"seg{i:02d}.mp4"), **seg_info[i]) for i, s in enumerate(shots)],
               cues=cues, words=tl["words"], voice_stem=str(work / "voice.wav"), loudness=ln, settings={k: o[k] for k in ("crf", "preset", "lufs", "true_peak", "transition_sec")}, bgm=bool(bgm),
               voices=[dict(shot=s["id"], **v) for s in shots for v in s.get("voices", [])])
    (work / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return man

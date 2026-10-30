"""QUALITY CHECK: automated checks on the finished video. Every failed check names the seat responsible,
so the workflow can send the item back (VISUALS / VOICE / EDITOR / WRITER).

checks: format (resolution, H.264, yuv420p, fps), duration (vs plan and template range), source resolution (upscaling),
sharpness (Laplacian variance per shot), black frames, frozen frames, audio clipping (true peak), loudness (-14 LUFS +-1),
narration silence gaps, subtitle-voice sync (each cue starts on speech; cues inside the video), character voice consistency, draft label."""
from pathlib import Path
import re, subprocess
import numpy as np
from . import ff

DEFAULTS = dict(min_sharpness=12.0, min_source_scale=0.66, max_black_sec=0.4, max_freeze_sec=1.5, lufs=-14.0, lufs_tol=1.0,
                max_true_peak=-1.0, max_gap_sec=1.6, min_sync=0.9, min_sec=8.0, max_sec=180.0)

def _chk(name, ok, seat, detail, value=None, severity="fail"):
    return dict(name=name, ok=bool(ok), seat=seat, detail=detail, value=value, severity="ok" if ok else severity)

def sharpness(path, w, h, times):
    """Variance of the Laplacian on 540-px-wide grey frames at the given times (higher = sharper)."""
    sw = 540; sh = int(round(h * sw / w / 2) * 2); out = []
    for t in times:
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={sw}:{sh}:flags=area,format=gray",
                            "-f", "rawvideo", "-"], capture_output=True)
        if len(p.stdout) < sw * sh: out.append(None); continue
        a = np.frombuffer(p.stdout[:sw * sh], np.uint8).reshape(sh, sw).astype(np.float32)
        lap = a[1:-1, :-2] + a[1:-1, 2:] + a[:-2, 1:-1] + a[2:, 1:-1] - 4 * a[1:-1, 1:-1]
        out.append(round(float(lap.var()), 1))
    return out

def _intervals(err, start_key, end_key):
    s = [float(x) for x in re.findall(start_key + r":\s*([\d.]+)", err)]; e = [float(x) for x in re.findall(end_key + r":\s*([\d.]+)", err)]
    return list(zip(s, e + [None] * (len(s) - len(e))))

def check(manifest, plan=None, **opts):
    """manifest: from editor.assemble(). plan: dict(total_sec=(lo, hi), sync=exact|estimated). Returns the report."""
    o = dict(DEFAULTS, **{k: v for k, v in opts.items() if v is not None}); path = manifest["output"]; w, h = manifest["size"]
    R = []; shots = manifest["shots"]; S = [s["start"] for s in shots]
    def shot_of(t): return shots[max([i for i, s in enumerate(S) if s <= t + 1e-6] or [0])]["id"]
    # format
    d = ff.probe(path); v = next(s for s in d["streams"] if s["codec_type"] == "video"); a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    fps = (lambda n, m: n / m if m else 0)(*map(int, v.get("r_frame_rate", "0/1").split("/")))
    fmt_ok = (int(v["width"]), int(v["height"])) == (w, h) and v["codec_name"] == "h264" and v.get("pix_fmt") == "yuv420p" and abs(fps - manifest["fps"]) < 0.01 and a is not None
    R.append(_chk("format", fmt_ok, "editor", f"{v['width']}x{v['height']} {v['codec_name']}/{v.get('profile')} {v.get('pix_fmt')} {fps:g}fps, audio={'yes' if a else 'MISSING'}"))
    dur = float(d["format"]["duration"]); lo, hi = (plan or {}).get("total_sec") or (o["min_sec"], o["max_sec"])
    R.append(_chk("duration", abs(dur - manifest["total"]) < 0.25 and lo <= dur <= hi, "writer" if not lo <= dur <= hi else "editor",
                  f"{dur:.1f}s (planned {manifest['total']:.1f}s, allowed {lo:g}-{hi:g}s)", round(dur, 2)))
    # source resolution (no blurry upscales)
    small = [f"{s['id']} {s['src_w']}x{s['src_h']}" for s in shots if s.get("src_w") and min(s["src_w"] / w, s["src_h"] / h) < o["min_source_scale"]]
    R.append(_chk("source_resolution", not small, "visuals", ("upscaled too much: " + ", ".join(small)) if small else "all sources >= " + f"{int(o['min_source_scale'] * 100)}% of output"))
    short = [f"{s['id']} short by {s['short_by']:.1f}s" for s in shots if s.get("short_by", 0) > 0.5]
    R.append(_chk("clip_length", not short, "visuals", ("clips shorter than their shot (frozen tail): " + ", ".join(short)) if short else "every clip covers its shot"))
    # sharpness: middle of each shot
    # measured on each shot's own render (before subtitles, which would hide a blurry picture), else on the final video
    sh = [sharpness(s["seg"], w, h, [s["dur"] / 2])[0] if s.get("seg") and Path(s["seg"]).is_file() else sharpness(path, w, h, [s["start"] + s["dur"] / 2])[0] for s in shots]
    blurry = [f"{s['id']}={x}" for s, x in zip(shots, sh) if x is not None and x < o["min_sharpness"]]
    R.append(_chk("sharpness", not blurry, "visuals", ("blurry: " + ", ".join(blurry)) if blurry else "min " + str(min([x for x in sh if x is not None] or [0])), dict(zip([s["id"] for s in shots], sh))))
    # black / frozen frames (fade-through-black transitions are allowed)
    err = ff.run(["-i", path, "-vf", f"blackdetect=d={o['max_black_sec']}:pix_th=0.08,freezedetect=n=0.0015:d={o['max_freeze_sec']}", "-an", "-f", "null", "-"])
    fb = [s["start"] + s["dur"] for s in shots if s["transition"] == "fade_black"]
    blacks = [(a_, b_) for a_, b_ in _intervals(err, "black_start", "black_end") if not any(abs(a_ - t) < 1.0 for t in fb)]
    R.append(_chk("black_frames", not blacks, "visuals", ("black at " + ", ".join(f"{a_:.1f}s ({shot_of(a_)})" for a_, _ in blacks)) if blacks else "none"))
    frz = _intervals(err, "lavfi.freezedetect.freeze_start", "lavfi.freezedetect.freeze_end")
    R.append(_chk("frozen_frames", not frz, "visuals", ("frozen at " + ", ".join(f"{a_:.1f}s ({shot_of(a_)})" for a_, _ in frz)) if frz else "none"))
    # audio: loudness + true peak on the final mix
    err = ff.run(["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    I = re.findall(r"I:\s*(-?[\d.]+|-inf) LUFS", err); tp = re.findall(r"Peak:\s*(-?[\d.]+|-inf) dBFS", err)
    I = float(I[-1]) if I and I[-1] != "-inf" else -99.0; tp = float(tp[-1]) if tp and tp[-1] != "-inf" else -99.0
    R.append(_chk("loudness", abs(I - o["lufs"]) <= o["lufs_tol"], "editor", f"{I:.1f} LUFS (target {o['lufs']:g} +-{o['lufs_tol']:g})", I))
    R.append(_chk("clipping", tp <= o["max_true_peak"], "editor", f"true peak {tp:.1f} dBTP (max {o['max_true_peak']:g})", tp))
    # narration: silence gaps + subtitle sync on the voice stem
    vs = manifest.get("voice_stem"); words = manifest.get("words") or []
    if vs and words:
        err = ff.run(["-i", vs, "-af", "silencedetect=noise=-38dB:d=0.12", "-f", "null", "-"])
        sil = [(a_, b_ if b_ is not None else manifest["total"]) for a_, b_ in _intervals(err, "silence_start", "silence_end")]
        first, last = words[0]["start"], words[-1]["end"]
        gaps = [(a_, b_) for a_, b_ in sil if a_ > first and b_ < last and b_ - a_ > o["max_gap_sec"]]
        speech = sum(1 for a_, b_ in sil if a_ <= first and b_ >= last) == 0
        R.append(_chk("voice_present", speech, "voice", "narration audible" if speech else "voice track is silent"))
        R.append(_chk("silence_gaps", not gaps, "voice", ("gaps " + ", ".join(f"{a_:.1f}-{b_:.1f}s" for a_, b_ in gaps)) if gaps else f"no gap > {o['max_gap_sec']}s"))
        def in_speech(t): return not any(a_ + 0.15 < t < b_ - 0.15 for a_, b_ in sil)
        starts = [t for c in manifest.get("cues", []) for t in c["words"]]
        good = sum(in_speech(t) for t in starts) / max(1, len(starts)) if speech else 0.0
        inside = all(c["end"] <= manifest["total"] + 0.05 for c in manifest.get("cues", []))
        est = (plan or {}).get("sync") == "estimated"
        R.append(_chk("subtitle_sync", (good >= o["min_sync"] or est) and inside, "voice",
                      f"{good * 100:.0f}% of subtitle words start on speech" + (" (timings estimated - draft voice)" if est else ""), round(good, 3), "warn" if est else "fail"))
    else: R.append(_chk("voice_present", False, "voice", "no narration"))
    # character voices: every character keeps ONE voice (profile + backend + voice id) across all shots
    vc = manifest.get("voices") or []
    if vc:
        per = {}
        for v in vc: per.setdefault(v["speaker"], set()).add((v.get("signature"), v.get("backend"), v.get("voice")))
        bad = [f"{sp} uses {len(k)} voices" for sp, k in per.items() if len(k) > 1]
        same = {}
        for sp, k in per.items(): same.setdefault(next(iter(k))[1:], []).append(sp)
        clash = [" = ".join(v) for v in same.values() if len(v) > 1]
        R.append(_chk("voice_consistency", not bad, "voice", ("; ".join(bad)) if bad else f"{len(per)} character(s), one voice each" + (f" (same voice id: {', '.join(clash)} - differ by pitch/rate only)" if clash else ""),
                      {sp: sorted(map(list, k)) for sp, k in per.items()}))
    R.append(_chk("final_quality", not manifest.get("draft"), "visuals", "final backends" if not manifest.get("draft") else
                  "DRAFT PREVIEW - offline voice/visuals; not final quality", severity="draft"))
    fails = [c for c in R if not c["ok"] and c["severity"] == "fail"]
    order = ["writer", "voice", "visuals", "editor"]
    back = min((c["seat"] for c in fails), key=order.index) if fails else None
    return dict(passed=not fails, draft=bool(manifest.get("draft")), send_back=back, checks=R,
                summary=("PASS" if not fails else f"FAIL -> {back.upper()}: " + "; ".join(f"{c['name']}: {c['detail']}" for c in fails if c["seat"] == back)) + (" [DRAFT]" if manifest.get("draft") else ""))

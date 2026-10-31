"""Automated continuity QC for generated shots (character consistency, set/props/wardrobe vs a set sheet, intra-shot drift,
glitches/jumps, stray text). Uses CLIP (open_clip) and tesseract when installed; otherwise a numpy fallback
(colour histograms + perceptual hash + grid layout) that is much weaker - fallback results are warnings, never hard fails
for identity, and the report says which engine ran. Every detail that is about a shot names the shot id so QC can send it back."""
import shutil, subprocess, tempfile
from pathlib import Path
import numpy as np

W, H = 160, 90

def frames(video, times, w=W, h=H):
    """RGB frames (h, w, 3) uint8 at the given times (seconds) via ffmpeg."""
    out = []
    for t in times:
        try:
            seek = ["-ss", f"{t:.3f}"] if t and t > 0 else []
            # Convert before resizing: YUV-first video scaling and RGB-first PNG scaling
            # otherwise disagree enough to put identical colours in different histogram bins.
            r = subprocess.run(["ffmpeg", "-v", "error", *seek, "-i", str(video), "-frames:v", "1", "-vf", f"format=rgb24,scale={w}:{h}",
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired, UnicodeError): r = None
        out.append(np.frombuffer(r.stdout, np.uint8).reshape(h, w, 3) if r and len(r.stdout) == w * h * 3 else None)
    return out

def frame_diffs(video, w=64, h=36, max_s=600):
    """Every decoded frame (tiny grey) -> (fps, [mean abs diff to previous frame]). Catches 1-5 frame flashes that sparse samples miss."""
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-t", str(max_s), "-i", str(video), "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True, timeout=300)
        fps = 24.0
        p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", str(video)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        a, _, b = p.stdout.strip().partition("/"); fps = float(a) / float(b or 1) if a and float(b or 1) else fps
    except (OSError, subprocess.TimeoutExpired, ValueError): return 24.0, []
    n = len(r.stdout) // (w * h)
    if n < 2: return fps, []
    f = np.frombuffer(r.stdout[: n * w * h], np.uint8).reshape(n, h, w).astype(np.int16)
    return fps, [0.0] + [float(x) for x in np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))]

def image(path, w=W, h=H):
    return frames(path, [0], w, h)[0]

def duration(video):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired): return 0.0

# ---------------- features ----------------
def _hsv_hist(a, bins=(12, 4, 4)):
    x = a.reshape(-1, 3).astype(np.float32) / 255; mx = x.max(1); mn = x.min(1); d = mx - mn + 1e-6
    r, g, b = x.T; h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6
    s = np.where(mx > 0, d / (mx + 1e-6), 0)
    hist, _ = np.histogramdd(np.stack([h % 1, np.clip(s, 0, .999), np.clip(mx, 0, .999)], 1), bins=bins, range=((0, 1), (0, 1), (0, 1)))
    hist = hist.ravel(); return hist / (hist.sum() + 1e-9)

def _dhash(a, n=16):
    g = a.astype(np.float32).mean(2); ys = np.linspace(0, g.shape[0] - 1, n).astype(int); xs = np.linspace(0, g.shape[1] - 1, n + 1).astype(int)
    s = g[np.ix_(ys, xs)]; return (s[:, 1:] > s[:, :-1]).ravel()

def _grid(a, n=4):
    h, w = a.shape[:2]; return np.array([a[i*h//n:(i+1)*h//n, j*w//n:(j+1)*w//n].reshape(-1, 3).mean(0) for i in range(n) for j in range(n)]) / 255

def similarity(a, b):
    """0..1 fallback similarity: histogram intersection + structure (dHash) + layout (grid colours)."""
    if a is None or b is None: return 0.0
    hi = float(np.minimum(_hsv_hist(a), _hsv_hist(b)).sum())
    dh = 1 - float(np.mean(_dhash(a) != _dhash(b)))
    gr = 1 - min(1.0, float(np.abs(_grid(a) - _grid(b)).mean()) * 3)
    return round(0.45 * hi + 0.3 * dh + 0.25 * gr, 3)

def colour_sim(a, b):
    if a is None or b is None: return 0.0
    return round(float(np.minimum(_hsv_hist(a), _hsv_hist(b)).sum()), 3)

class _Clip:
    model = None
    @classmethod
    def load(cls):
        if cls.model is None:
            try:
                import open_clip, torch  # noqa: F401
                m, _, pre = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k"); m.eval(); cls.model = (m, pre)
            except Exception: cls.model = False
        return cls.model or None
    @classmethod
    def embed(cls, a):
        import torch
        from PIL import Image
        m, pre = cls.model
        with torch.no_grad(): v = m.encode_image(pre(Image.fromarray(a)).unsqueeze(0))[0]
        return (v / v.norm()).numpy()

def engine():
    return "clip" if _Clip.load() else "fallback"

def identity(a, b):
    if _Clip.load() and a is not None and b is not None: return round(float(_Clip.embed(a) @ _Clip.embed(b)), 3)
    return similarity(a, b)

def ocr_text(a):
    """Text found in the frame above the subtitle band, or None when tesseract is missing."""
    if not shutil.which("tesseract") or a is None: return None
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "f.ppm"; h, w = a.shape[:2]; top = a[: int(h * 0.78)]
        p.write_bytes(f"P6 {w} {top.shape[0]} 255\n".encode() + top.tobytes())
        try: r = subprocess.run(["tesseract", str(p), "-", "--psm", "11"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        except (OSError, subprocess.TimeoutExpired, UnicodeError): return None
        return "".join(ch for ch in r.stdout if ch.isalnum())

# ---------------- checks ----------------
def analyse(video, shots, refs=None, set_sheet=None, thresholds=None):
    """shots: [{id, start, dur, characters:[..], shot_type}] in the final video. refs: {character: [image paths]}.
    Returns a list of check dicts (name, ok, seat, detail, value, severity)."""
    t = dict(identity=0.62 if engine() == "fallback" else 0.22, set=0.40, drift=0.45, jump=0.38, glitch=60.0, local=55.0, flash=25.0)
    t.update(thresholds or {}); eng = engine(); out = []
    def chk(name, ok, detail, value=None, sev="fail", seat="visuals"):
        out.append(dict(name=name, ok=bool(ok), seat=seat, detail=detail, value=value, severity=sev))
    big = {}
    for s in shots:
        st, du = float(s["start"]), float(s["dur"]); n = max(4, min(10, int(du * 2)))
        ts = [st + du * (i + .5) / n for i in range(n)]; fr = frames(video, ts); big[s["id"]] = fr
    # 1) intra-shot drift + glitch/jump: compare consecutive samples; a person/prop vanishing or a morph shows as a dip
    bad_drift, bad_glitch, bad_local, vals = [], [], [], {}
    for s in shots:
        fr = [f for f in big[s["id"]] if f is not None]
        if len(fr) < 2: bad_glitch.append(f"{s['id']}(unreadable)"); continue
        sims = [similarity(fr[i], fr[i + 1]) for i in range(len(fr) - 1)]; end = similarity(fr[0], fr[-1])
        diffs = [float(np.abs(fr[i].astype(int) - fr[i + 1].astype(int)).mean()) for i in range(len(fr) - 1)]
        vals[s["id"]] = dict(min_step=min(sims), first_last=end, max_diff=round(max(diffs), 1))
        moving = s.get("camera") in ("pan", "orbit", "tracking", "dolly")
        a, b = fr[0].astype(float), fr[-1].astype(float); gh, gw = a.shape[0] // 6, a.shape[1] // 6
        cells = [float(np.abs(a[y:y + gh, x:x + gw] - b[y:y + gh, x:x + gw]).mean()) for y in range(0, gh * 6, gh) for x in range(0, gw * 6, gw)]
        loc = max(cells) - float(np.median(cells)); vals[s["id"]]["local_max"] = round(loc, 1)
        if loc > t["local"] and not moving: bad_local.append(f"{s['id']}(one area changed by {loc:.0f})")
        if end < t["drift"] and not moving: bad_drift.append(f"{s['id']}(first↔last {end:.2f})")
        if min(sims) < t["jump"] or (max(diffs) > t["glitch"] and max(diffs) > 3 * (np.median(diffs) + 1)): bad_glitch.append(f"{s['id']}(step {min(sims):.2f}, Δ{max(diffs):.0f})")
    chk("shot_drift", not bad_drift, "large change inside shot (person/prop vanished or scene morphed): " + ", ".join(bad_drift) if bad_drift else "no large change inside any shot", vals, "fail")
    fps, fd = frame_diffs(video)
    if fd:
        for s in shots:
            m = max(3, int(0.3 * fps))  # real cuts land a few frames off the planned boundary - ignore them
            a, b = int(float(s["start"]) * fps) + m, int((float(s["start"]) + float(s["dur"])) * fps) - m
            seg = fd[a:b]
            if len(seg) < 6: continue
            med = float(np.median(seg)); i = int(np.argmax(seg)); pk = seg[i]
            if pk > t["flash"] and pk > 6 * (med + 1) and f"{s['id']}(" not in " ".join(bad_glitch):
                bad_glitch.append(f"{s['id']}(flash/jump at {(a + i) / fps:.2f}s, Δ{pk:.0f})")
    chk("local_change", not bad_local, "one region changed a lot inside a static shot (prop/hand/accessory appeared or vanished?): " + ", ".join(bad_local)
        if bad_local else "no isolated region change inside shots", None, "warn")
    chk("glitch_jump", not bad_glitch, "glitch / jump cut inside shot: " + ", ".join(bad_glitch) if bad_glitch else "no glitches or jumps inside shots", None, "fail")
    # 2) character consistency vs locked refs (best ref, best frame)
    if refs:
        ref_img = {c: [image(p, 224, 224) for p in ps[:4]] for c, ps in refs.items()}
        low, scores = [], {}
        for s in shots:
            if not any(c in ref_img for c in s.get("characters") or []): continue
            fr = [f for f in frames(video, [s["start"] + s["dur"] * k for k in (.25, .5, .75)], 224, 224) if f is not None]
            for c in s.get("characters") or []:
                if c not in ref_img: continue
                sc = max((identity(f, r) for f in fr for r in ref_img[c] if r is not None), default=0)
                scores[f"{s['id']}/{c}"] = sc
                if sc < t["identity"]: low.append(f"{s['id']}:{c}({sc:.2f})")
        ok = not low
        chk("character_consistency", ok, (f"[{eng}] low match to locked refs: " + ", ".join(low)) if low else f"[{eng}] every tagged character matches their refs",
            scores, "fail" if eng == "clip" else "warn")
    else: chk("character_consistency", True, "no locked refs - skipped", None, "info")
    # 3) set continuity vs set sheet (colour palette / lighting / layout), and shot-to-shot palette stability for same set
    if set_sheet and Path(set_sheet).is_file():
        ss = image(set_sheet); low, sc = [], {}
        for s in shots:
            fr = [f for f in big[s["id"]] if f is not None]
            v = max((colour_sim(f, ss) for f in fr), default=0); sc[s["id"]] = v
            if v < t["set"]: low.append(f"{s['id']}({v:.2f})")
        chk("set_continuity", not low, ("set/wardrobe/props differ from the set sheet: " + ", ".join(low)) if low else "every shot matches the set sheet palette/lighting", sc, "warn")
    else: chk("set_continuity", True, "no set sheet - skipped", None, "info")
    # palette jump between consecutive shots (lighting/wardrobe continuity for one scene)
    pj = []
    for a, b in zip(shots, shots[1:]):
        fa = [f for f in big[a["id"]] if f is not None]; fb = [f for f in big[b["id"]] if f is not None]
        if fa and fb and colour_sim(fa[-1], fb[0]) < t["set"] * .8: pj.append(f"{b['id']}")
    chk("lighting_continuity", not pj, ("lighting/palette jumps at shots: " + ", ".join(pj)) if pj else "lighting/palette stable across cuts", None, "warn")
    # 4) stray text (signs, gibberish captions, watermarks) above the subtitle band
    if shutil.which("tesseract"):
        st = []
        for s in shots:
            txt = "".join(ocr_text(f) or "" for f in big[s["id"]][:: max(1, len(big[s['id']]) // 3)])
            if len(txt) >= 4: st.append(f"{s['id']}('{txt[:12]}')")
        chk("stray_text", not st, ("stray text/watermark in frame: " + ", ".join(st)) if st else "no stray text", None, "fail")
    else:
        chk("stray_text", False, "tesseract not installed - stray-text check skipped (install tesseract-ocr to enable)", None, "warn")
    return out

def storyboard_shots(storyboard, total=None):
    """Lay storyboard shots on a timeline from their durations (for external videos without an editor manifest)."""
    t, out = 0.0, []
    for s in storyboard["shots"]:
        out.append(dict(id=s["id"], start=t, dur=float(s["duration"]), characters=s.get("characters") or [], camera=s.get("camera"))); t += float(s["duration"])
    if total and out and abs(t - total) > 0.5:
        k = total / t
        for s in out: s["start"] *= k; s["dur"] *= k
    return out

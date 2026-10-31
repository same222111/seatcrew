"""Pluggable visuals: one image or video clip per shot.

  local       final  - your own clip/image in the clips folder (<shot id>.mp4/.mov/.png/.jpg/.webp). Always preferred.
  kling / runway / luma / gemini / minimax   final - direct video APIs (see providers.py; image-to-video when the shot has ref_image)
  sora        retired - OpenAI removed the Sora video API on 2026-09-24
  replicate   final  - any Replicate-hosted text-to-video model (Kling, Luma Ray, Runway-style, Wan, Veo ...): set video_model
                       to the model slug, e.g. "kwaivgi/kling-v2.1" (REPLICATE_API_TOKEN)
  openai      final  - gpt-image-1 high-quality stills (OPENAI_API_KEY); the EDITOR adds camera motion
  stability   final  - Stability AI Stable Image Ultra stills (STABILITY_API_KEY)
  draft       DRAFT  - offline gradient title cards. Labeled draft everywhere; never final quality.
  mock        tests only
Add another API by subclassing providers.Adapter (see docs/VIDEO.md)."""
import base64, json, os, time, urllib.request
from pathlib import Path
from . import ff
from .storyboard import find_clip
from . import providers as PV

FINAL = ("local", "replicate", "openai", "stability", "kling", "runway", "luma", "gemini", "minimax", "sora")
DIRECT = ("kling", "runway", "luma", "gemini", "minimax", "sora", "replicate")
class VisualError(RuntimeError): pass

def _http(url, headers, body=None, data=None, timeout=300, method=None):
    req = urllib.request.Request(url, data=data if data is not None else (json.dumps(body).encode() if body is not None else None), headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e: raise VisualError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
    except (urllib.error.URLError, TimeoutError, OSError) as e: raise VisualError(f"network: {e}")

def _need(env):
    k = os.getenv(env)
    if not k: raise VisualError(f"{env} is not set")
    return k

def prompt_for(shot, style=""):
    return ", ".join(x for x in (shot.get("visual") or shot.get("narration"), style, "no text, no watermark, no logos") if x)

def openai_image(shot, out_dir, aspect, model=None, style=""):
    key = _need("OPENAI_API_KEY"); size = "1024x1536" if aspect == "9:16" else "1536x1024"
    raw, _ = _http("https://api.openai.com/v1/images/generations", {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                   dict(model=model or "gpt-image-1", prompt=prompt_for(shot, style), size=size, quality="high", n=1))
    d = json.loads(raw)["data"][0]; p = Path(out_dir) / f"{shot['id']}.png"
    if d.get("b64_json"): p.write_bytes(base64.b64decode(d["b64_json"]))
    else: p.write_bytes(_http(d["url"], {})[0])
    return p

def stability_image(shot, out_dir, aspect, model=None, style=""):
    import uuid
    key = _need("STABILITY_API_KEY"); b = uuid.uuid4().hex; parts = b""
    for n, v in (("prompt", prompt_for(shot, style)), ("aspect_ratio", aspect), ("output_format", "png")):
        parts += f"--{b}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n".encode()
    parts += f"--{b}--\r\n".encode()
    raw, ct = _http(f"https://api.stability.ai/v2beta/stable-image/generate/{model or 'ultra'}", {"Authorization": f"Bearer {key}", "Accept": "image/*",
                    "Content-Type": f"multipart/form-data; boundary={b}"}, data=parts)
    if not ct.startswith("image/"): raise VisualError("stability: no image returned")
    p = Path(out_dir) / f"{shot['id']}.png"; p.write_bytes(raw); return p

FONT = Path(__file__).parent / "fonts" / "Montserrat-ExtraBold.ttf"
def draft_card(shot, out_dir, aspect, model=None, style="", size=None):
    """Offline DRAFT still: dark gradient + the shot's caption/visual text. Clearly not final."""
    from .storyboard import SIZES
    w, h = size or SIZES[aspect]; p = Path(out_dir) / f"{shot['id']}.png"
    txt = (shot.get("caption") or shot.get("visual") or shot["id"])[:110].replace("'", "").replace(":", " ").replace("%", " ").replace("\\", " ")
    hue = (sum(map(ord, shot["id"])) * 47) % 360
    import textwrap
    per = max(8, int(w * 0.84 / (h * 0.035 * 0.7)))
    txt = "\n".join(textwrap.wrap(txt, per)[:4]) if " " in txt else "\n".join(txt[i:i + per // 2] for i in range(0, len(txt), per // 2))[:200]
    tf = Path(out_dir) / f"{shot['id']}.card.txt"; tf.write_text(txt, encoding="utf-8")
    from .typography import text_font
    selected, _ = text_font(txt)
    import shutil
    local_font = Path(out_dir) / ("draft-font" + selected.suffix)
    shutil.copyfile(selected, local_font)
    font = local_font.name
    ff.run(["-f", "lavfi", "-i", f"gradients=s={w}x{h}:c0=0x101820:c1=0x1d3b4a:x0=0:y0=0:x1={w}:y1={h}:nb_colors=2,hue=h={hue},format=rgb24",
            "-vf", f"drawtext=fontfile='{font}':textfile='{tf.name}':fontsize={int(h*0.035)}:fontcolor=white:line_spacing=18:x=(w-tw)/2:y=(h-th)/2:box=1:boxcolor=black@0.35:boxborderw=24",
            "-frames:v", "1", p.name], cwd=str(out_dir))
    return p

def mock_image(shot, out_dir, aspect, model=None, style="", size=(540, 960)):
    p = Path(out_dir) / f"{shot['id']}.png"
    ff.run(["-f", "lavfi", "-i", f"testsrc2=s={size[0]}x{size[1]}:d=1", "-frames:v", "1", str(p)]); return p

def auto_order(pref="auto", video_model=""):
    if pref and pref != "auto": return [pref]
    o = [b for b in ("kling", "runway", "gemini", "minimax", "luma") if any(os.getenv(e) for e in PV.VIDEO_ENV[b])]
    if os.getenv("REPLICATE_API_TOKEN") and video_model and "/" in video_model: o.append("replicate")
    if os.getenv("OPENAI_API_KEY"): o.append("openai")
    if os.getenv("STABILITY_API_KEY"): o.append("stability")
    return o

def ref_for(shot, refs=None, base=None):
    """Reference image for consistent characters: the shot's ref_image, else the first speaker that has one in refs."""
    r = shot.get("ref_image") or next((refs[l["speaker"]] for l in shot.get("lines", []) if refs and l.get("speaker") in refs), None) \
        or next((refs[c] for c in shot.get("characters") or [] if refs and c in refs), None)
    if not r: return None
    p = Path(r) if Path(r).is_absolute() or not base else Path(base) / r
    return p if p.is_file() else None

def make(shot, out_dir, aspect, pref="auto", clips_dir=None, video_model="", image_model="", style="", allow_draft=True, refs=None, base=None):
    """Returns (path, info). Own clips win; then backends in order; then the labeled draft card if allowed."""
    if clips_dir:
        c = find_clip(clips_dir, shot["id"])
        if c: return c, dict(backend="local", source=str(Path(c).name))
    errs = []
    for b in auto_order(pref, video_model):
        try:
            if b in DIRECT:
                a = PV.VIDEO[b](); m = (video_model if b == "replicate" or (video_model and "/" not in video_model) else "") or a.default_model
                ref = ref_for(shot, refs, base)
                p = a.run(prompt_for(shot, style), Path(out_dir) / f"{shot['id']}.mp4", aspect, shot["duration"], m, ref)
                return p, dict(backend=b, model=m, **({"ref_image": Path(ref).name} if ref else {}))
            if b == "openai": return openai_image(shot, out_dir, aspect, image_model or None, style), dict(backend=b, model=image_model or "gpt-image-1")
            if b == "stability": return stability_image(shot, out_dir, aspect, image_model or None, style), dict(backend=b)
            if b == "mock": return mock_image(shot, out_dir, aspect), dict(backend=b)
            if b == "draft": break
            raise VisualError(f"unknown visuals backend {b}")
        except (VisualError, PV.ProviderError, ff.FFError) as e: errs.append(f"{b}: {e}")
    if allow_draft and pref in ("auto", "draft"):
        return draft_card(shot, out_dir, aspect), dict(backend="draft", draft=True, fallback_reasons=errs)
    raise VisualError("; ".join(errs) or "no visuals backend available (add clips, or set a key)")

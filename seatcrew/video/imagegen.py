"""Image-generation adapters for Character Studio: character sheets (front / side / full body / expressions), set sheets
and keyframes, with reference images for consistency. Keys come from the environment only, never stored or logged.

  openai     gpt-image-1  - /v1/images/edits with reference images (or /generations without)   OPENAI_API_KEY
  gemini     gemini-nano-banana-2.1 (Nano Banana 2.1) generateContent, up to 4 character refs    GEMINI_API_KEY
  minimax    image-01     - /v1/image_generation with subject_reference (character)             MINIMAX_API_KEY
  replicate  black-forest-labs/flux-kontext-pro (any slug) with input_image                     REPLICATE_API_TOKEN
  draft      offline placeholder (your reference photo + a DRAFT label). Never final quality.

Live-test status: mocked HTTP only (tests/test_characters.py). Endpoints checked against vendor docs on providers.CHECKED."""
import base64, json, os, uuid
from pathlib import Path
from . import providers as PV, ff

ASPECTS = ("1:1", "16:9", "9:16", "3:2", "2:3")

def _b64_out(out, b64):
    data = base64.b64decode(b64)
    if len(data) < 100: raise PV.ProviderError("image: empty image returned")
    Path(out).write_bytes(data); return Path(out)

def _multipart(fields, files):
    b = uuid.uuid4().hex; body = b""
    for k, v in fields.items(): body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, p in files:
        p = Path(p); mt = PV.image_b64(p)[1]
        body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{p.name}\"\r\nContent-Type: {mt}\r\n\r\n".encode() + p.read_bytes() + b"\r\n"
    return body + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"

class OpenAIImage:
    name = "openai"; default_model = "gpt-image-1"; max_refs = 10
    def generate(self, prompt, out, refs=(), aspect="1:1", model=None):
        k = PV.need("OPENAI_API_KEY"); size = {"16:9": "1536x1024", "3:2": "1536x1024", "9:16": "1024x1536", "2:3": "1024x1536"}.get(aspect, "1024x1024")
        m = model or self.default_model; refs = [r for r in refs if r][: self.max_refs]
        if refs:
            data, ct = _multipart(dict(model=m, prompt=prompt, size=size, quality="high", n="1"), [("image[]", r) for r in refs])
            raw, _ = PV.req("POST", "https://api.openai.com/v1/images/edits", {"Authorization": f"Bearer {k}", "Content-Type": ct}, data=data, timeout=300, what="openai image")
            d = json.loads(raw)
        else:
            d = PV.jreq("POST", "https://api.openai.com/v1/images/generations", {"Authorization": f"Bearer {k}"}, dict(model=m, prompt=prompt, size=size, quality="high", n=1), timeout=300, what="openai image")
        it = (d.get("data") or [{}])[0]
        if it.get("b64_json"): return _b64_out(out, it["b64_json"])
        if it.get("url"): Path(out).write_bytes(PV.req("GET", it["url"], {}, what="openai image download")[0]); return Path(out)
        raise PV.ProviderError("openai image: no image in response")

class GeminiImage:
    name = "gemini"; default_model = "gemini-nano-banana-2.1"; max_refs = 4
    def generate(self, prompt, out, refs=(), aspect="1:1", model=None):
        k = PV.need("GEMINI_API_KEY", "GOOGLE_API_KEY"); parts = []
        for r in [r for r in refs if r][: self.max_refs]:
            b, mt = PV.image_b64(r); parts.append(dict(inline_data=dict(mime_type=mt, data=b)))
        parts.append(dict(text=prompt))
        body = dict(contents=[dict(role="user", parts=parts)], generationConfig=dict(responseModalities=["IMAGE"], imageConfig=dict(aspectRatio=aspect)))
        d = PV.jreq("POST", f"https://generativelanguage.googleapis.com/v1beta/models/{model or self.default_model}:generateContent", {"x-goog-api-key": k}, body, timeout=300, what="gemini image")
        for c in d.get("candidates") or []:
            for p in (c.get("content") or {}).get("parts") or []:
                inl = p.get("inlineData") or p.get("inline_data")
                if inl and inl.get("data"): return _b64_out(out, inl["data"])
        raise PV.ProviderError("gemini image: no image in response (blocked or text-only answer)")

class MiniMaxImage:
    name = "minimax"; default_model = "image-01"; max_refs = 1
    def generate(self, prompt, out, refs=(), aspect="1:1", model=None):
        k = PV.need("MINIMAX_API_KEY"); body = dict(model=model or self.default_model, prompt=prompt[:1500], aspect_ratio=aspect, response_format="base64", n=1)
        refs = [r for r in refs if r]
        if refs: body["subject_reference"] = [dict(type="character", image_file=PV.data_uri(refs[0]))]
        d = PV.jreq("POST", "https://api.minimax.io/v1/image_generation", {"Authorization": f"Bearer {k}"}, body, timeout=300, what="minimax image")
        if (d.get("base_resp") or {}).get("status_code", 0) != 0: raise PV.ProviderError(f"minimax image: {d['base_resp'].get('status_msg')}")
        imgs = (d.get("data") or {}).get("image_base64") or []
        if not imgs: raise PV.ProviderError("minimax image: no image in response")
        return _b64_out(out, imgs[0])

class ReplicateImage:
    name = "replicate"; default_model = "black-forest-labs/flux-kontext-pro"; max_refs = 1
    def generate(self, prompt, out, refs=(), aspect="1:1", model=None, sleep=None):
        import time
        h = {"Authorization": f"Bearer {PV.need('REPLICATE_API_TOKEN')}", "Prefer": "wait"}; inp = dict(prompt=prompt, aspect_ratio=aspect, output_format="png")
        refs = [r for r in refs if r]
        if refs: inp["input_image"] = PV.data_uri(refs[0])
        j = PV.jreq("POST", f"https://api.replicate.com/v1/models/{model or self.default_model}/predictions", h, dict(input=inp), timeout=300, what="replicate image")
        for _ in range(150):
            if j.get("status") == "succeeded":
                o = j["output"]; u = o[0] if isinstance(o, list) else o
                Path(out).write_bytes(PV.req("GET", u, {}, what="replicate download")[0]); return Path(out)
            if j.get("status") in ("failed", "canceled"): raise PV.ProviderError(f"replicate image: {j.get('error') or j['status']}")
            (sleep or time.sleep)(2); j = PV.jreq("GET", j["urls"]["get"], h, what="replicate image")
        raise PV.ProviderError("replicate image: timed out")

ADAPTERS = dict(openai=OpenAIImage, gemini=GeminiImage, minimax=MiniMaxImage, replicate=ReplicateImage)
ENV = dict(openai=("OPENAI_API_KEY",), gemini=("GEMINI_API_KEY", "GOOGLE_API_KEY"), minimax=("MINIMAX_API_KEY",), replicate=("REPLICATE_API_TOKEN",))

def auto_order(pref="auto"):
    if pref and pref not in ("auto",): return [pref]
    return [b for b in ("openai", "gemini", "minimax", "replicate") if any(os.getenv(e) for e in ENV[b])] + ["draft"]

def draft_image(prompt, out, refs=(), aspect="1:1", label="DRAFT"):
    """Offline placeholder: the first reference photo (or a dark card) + the view name + a DRAFT banner."""
    from .visuals import FONT
    w, h = {"16:9": (1280, 720), "9:16": (720, 1280)}.get(aspect, (1024, 1024)); out = Path(out).resolve()
    txt = out.with_suffix(".txt"); txt.write_text(f"DRAFT - {label}"[:80].replace("%", " ").replace(":", " ").replace("'", " "), encoding="utf-8")
    src = next((Path(r) for r in refs if r and Path(r).is_file()), None)
    inp = ["-i", str(src)] if src else ["-f", "lavfi", "-i", f"color=c=0x141a2a:s={w}x{h}"]
    ff.run([*inp, "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x141a2a,"
            f"drawtext=fontfile='{FONT.as_posix()}':textfile='{txt.as_posix()}':fontsize={h // 22}:fontcolor=white:box=1:boxcolor=0xff2d55@0.85:boxborderw=12:x=(w-tw)/2:y=h*0.04",
            "-frames:v", "1", str(out)])
    txt.unlink(missing_ok=True); return out

def generate(prompt, out, refs=(), aspect="1:1", pref="auto", model=None, allow_draft=True):
    """Try backends in order -> (path, info). Falls back to a labeled DRAFT image only when allowed."""
    errs = []
    for b in auto_order(pref):
        if b == "draft":
            if not allow_draft: break
            return draft_image(prompt, out, refs, aspect, Path(out).stem), dict(backend="draft", draft=True, errors=errs)
        try: return ADAPTERS[b]().generate(prompt, out, refs, aspect, model), dict(backend=b, model=model or ADAPTERS[b].default_model, refs=len([r for r in refs if r]))
        except (PV.ProviderError, KeyError) as e: errs.append(f"{b}: {e}")
    raise PV.ProviderError("; ".join(errs) or "no image backend")

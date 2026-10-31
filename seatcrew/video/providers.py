"""Direct video-generation API adapters for the VISUALS seat + the provider catalog used by docs, the wizard,
the Video studio "Recommended models" panel and CHIEF chat.

Every adapter: submit -> async job -> poll (with timeout) -> download mp4. Transient HTTP errors (429/5xx/network)
are retried with backoff. Keys are read from the environment only, never stored, logged or echoed.
Model names / endpoints were checked against the vendors' official docs on CHECKED (see docs/VIDEO.md); vendors change
these often. Prices in the catalog are ROUGH planning numbers only - always check the linked official pricing page.

Live-test status: every adapter here is tested with mocked HTTP only (tests/test_providers.py), not against the real APIs."""
import base64, json, mimetypes, os, time, urllib.error, urllib.request
from pathlib import Path

CHECKED = "2026-10-30"
class ProviderError(RuntimeError): pass
RETRY = (429, 500, 502, 503, 504)

def _send(method, url, headers, data, timeout):
    """One raw HTTP call -> (status, bytes, content_type). Tests replace this function."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e: return e.code, e.read()[:2000], e.headers.get("Content-Type", "") if e.headers else ""
    except (urllib.error.URLError, TimeoutError, OSError) as e: raise ProviderError(f"network: {e}")

def req(method, url, headers=None, body=None, data=None, timeout=120, retries=3, backoff=2.0, what="api"):
    h = dict(headers or {})
    if body is not None: data = json.dumps(body).encode(); h.setdefault("Content-Type", "application/json")
    last = None
    for i in range(retries + 1):
        try: st, raw, ct = _send(method, url, h, data, timeout)
        except ProviderError as e:
            last = e
            if i < retries: time.sleep(backoff * 2 ** i); continue
            raise ProviderError(f"{what}: {e}")
        if st < 300: return raw, ct
        msg = raw[:300].decode("utf-8", "replace")
        if st in RETRY and i < retries: last = msg; time.sleep(backoff * 2 ** i); continue
        if st in (401, 403): raise ProviderError(f"{what}: HTTP {st} - key rejected or no access (check the key / billing)")
        raise ProviderError(f"{what}: HTTP {st}: {msg}")
    raise ProviderError(f"{what}: {last}")

def jreq(*a, **k):
    raw, _ = req(*a, **k)
    try: return json.loads(raw or b"{}")
    except ValueError: raise ProviderError(f"{k.get('what', 'api')}: response is not JSON")

def need(*envs):
    for e in envs:
        if os.getenv(e): return os.getenv(e)
    raise ProviderError(f"{' or '.join(envs)} is not set")

def image_b64(path):
    p = Path(path)
    if not p.is_file(): raise ProviderError(f"reference image not found: {p.name}")
    return base64.b64encode(p.read_bytes()).decode(), mimetypes.guess_type(p.name)[0] or "image/png"

def data_uri(path):
    b, mt = image_b64(path); return f"data:{mt};base64,{b}"

def clamp(x, lo, hi): return max(lo, min(hi, int(round(x))))

class Adapter:
    """submit(prompt, aspect, seconds, model, ref_image) -> job; poll(job) -> None | ('url', url, headers) | ('bytes', data)."""
    name = "video"; poll_every = 6; max_wait = 900; default_model = ""
    def submit(self, prompt, aspect, seconds, model, ref_image=None): raise NotImplementedError
    def poll(self, job): raise NotImplementedError
    def run(self, prompt, out, aspect="9:16", seconds=5, model=None, ref_image=None, sleep=time.sleep, clock=time.time):
        job = self.submit(prompt, aspect, seconds, model or self.default_model, ref_image); t0 = clock()
        while clock() - t0 < self.max_wait:
            r = self.poll(job)
            if r:
                if r[0] == "bytes": data = r[1]
                else: data, _ = req("GET", r[1], r[2] if len(r) > 2 else {}, timeout=300, what=f"{self.name} download")
                if len(data) < 1000: raise ProviderError(f"{self.name}: downloaded clip is empty")
                Path(out).write_bytes(data); return Path(out)
            sleep(self.poll_every)
        raise ProviderError(f"{self.name}: timed out after {self.max_wait}s (job {job.get('id', '?') if isinstance(job, dict) else job})")

class Kling(Adapter):
    """Kling 3.0 official API (new path-versioned design, API-key Bearer auth). https://kling.ai/document-api"""
    name = "kling"; default_model = "kling-3.0"; base = "https://api-singapore.klingai.com"
    def h(self): return {"Authorization": f"Bearer {need('KLING_API_KEY')}"}
    def submit(self, prompt, aspect, seconds, model, ref_image=None):
        st = dict(resolution="1080p", aspect_ratio=aspect if aspect in ("9:16", "16:9", "1:1") else "9:16", duration=clamp(seconds, 3, 15), audio="off", multi_shot=False)
        if ref_image:
            b, _ = image_b64(ref_image); st.pop("aspect_ratio")
            body = dict(contents=[dict(type="prompt", text=prompt), dict(type="first_frame", url=b)], settings=st)
            url = f"{self.base}/image-to-video/{model}"
        else: body, url = dict(prompt=prompt, settings=st), f"{self.base}/text-to-video/{model}"
        d = jreq("POST", url, self.h(), body, what="kling")
        if d.get("code", 0) != 0: raise ProviderError(f"kling: {d.get('message')}")
        return dict(id=d["data"]["id"])
    def poll(self, job):
        d = jreq("GET", f"{self.base}/tasks?task_ids={job['id']}", self.h(), what="kling")
        t = (d.get("data") or [{}])[0]; s = t.get("status")
        if s == "failed": raise ProviderError(f"kling: {t.get('message') or 'failed'}")
        if s == "succeeded":
            v = next((o for o in t.get("outputs", []) if o.get("type") == "video"), None)
            if not v: raise ProviderError("kling: no video in result")
            return ("url", v["url"])
        return None

class Runway(Adapter):
    """Runway API (gen4.5). text_to_video, or image_to_video with a reference image. https://docs.dev.runwayml.com"""
    name = "runway"; default_model = "gen4.5"; base = "https://api.dev.runwayml.com/v1"
    def h(self): return {"Authorization": f"Bearer {need('RUNWAYML_API_SECRET')}", "X-Runway-Version": "2024-11-06"}
    def submit(self, prompt, aspect, seconds, model, ref_image=None):
        body = dict(model=model, promptText=prompt[:1000], ratio="1280:720" if aspect == "16:9" else "720:1280", duration=clamp(seconds, 2, 10))
        ep = "text_to_video"
        if ref_image: body["promptImage"] = data_uri(ref_image); ep = "image_to_video"
        return dict(id=jreq("POST", f"{self.base}/{ep}", self.h(), body, what="runway")["id"])
    def poll(self, job):
        d = jreq("GET", f"{self.base}/tasks/{job['id']}", self.h(), what="runway"); s = d.get("status")
        if s in ("FAILED", "CANCELLED"): raise ProviderError(f"runway: {d.get('failure') or s} (moderated tasks are billed too)")
        return ("url", d["output"][0]) if s == "SUCCEEDED" else None

class Luma(Adapter):
    """Luma Agents API, Ray 3.2 (replaces the legacy Dream Machine ray-2 endpoint). https://docs.agents.lumalabs.ai"""
    name = "luma"; default_model = "ray-3.2"; base = "https://agents.lumalabs.ai/v1"
    def h(self): return {"Authorization": f"Bearer {need('LUMA_AGENTS_API_KEY', 'LUMAAI_API_KEY')}"}
    def submit(self, prompt, aspect, seconds, model, ref_image=None):
        v = dict(resolution="1080p", duration="10s" if seconds > 6 else "5s")
        if ref_image: b, mt = image_b64(ref_image); v["start_frame"] = dict(data=b, media_type=mt)
        d = jreq("POST", f"{self.base}/generations", self.h(), dict(model=model, type="video", prompt=prompt, aspect_ratio=aspect, video=v), what="luma")
        return dict(id=d["id"])
    def poll(self, job):
        d = jreq("GET", f"{self.base}/generations/{job['id']}", self.h(), what="luma"); s = d.get("state")
        if s == "failed": raise ProviderError(f"luma: {d.get('failure_reason') or 'failed'}")
        if s == "completed":
            v = next((o for o in d.get("output", []) if o.get("type") == "video"), None)
            if not v: raise ProviderError("luma: no video in result")
            return ("url", v["url"])
        return None

class Gemini(Adapter):
    """Google Gemini API video: Gemini Omni Flash via the Interactions API (Veo 3.1 Preview was shut down 2026-10-22).
    Vertex AI / Gemini Enterprise Veo GA models need Google Cloud auth and are not wired here."""
    name = "gemini"; default_model = "gemini-omni-1.1-flash"; base = "https://generativelanguage.googleapis.com/v1beta"
    def h(self): return {"x-goog-api-key": need("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    def _video(self, d):
        for st in d.get("steps") or []:
            for c in st.get("content") or []:
                if c.get("type") == "video":
                    if c.get("data"): return ("bytes", base64.b64decode(c["data"]))
                    if c.get("uri"): return ("url", c["uri"], self.h())
        return None
    def submit(self, prompt, aspect, seconds, model, ref_image=None):
        inp = prompt
        if ref_image: b, mt = image_b64(ref_image); inp = [dict(type="image", data=b, mime_type=mt), dict(type="text", text=prompt)]
        body = dict(model=model, input=inp, generation_config=dict(video_config=dict(task="image_to_video" if ref_image else "text_to_video")),
                    response_format=dict(type="video", aspect_ratio=aspect, duration=f"{clamp(seconds, 3, 10)}s", resolution="720p"), background=True)
        d = jreq("POST", f"{self.base}/interactions", self.h(), body, timeout=600, what="gemini")
        if d.get("status") == "failed": raise ProviderError(f"gemini: {d.get('error') or 'failed'}")
        return dict(id=d.get("id"), done=self._video(d))
    def poll(self, job):
        if job.get("done"): return job["done"]
        d = jreq("GET", f"{self.base}/interactions/{job['id']}", self.h(), what="gemini")
        if d.get("status") in ("failed", "cancelled"): raise ProviderError(f"gemini: {d.get('error') or d['status']}")
        return self._video(d) if d.get("status") == "completed" else None

class MiniMax(Adapter):
    """MiniMax Hailuo video, V2 endpoint (MiniMax-H3 family). Reference images -> reference-to-video (character consistency)."""
    name = "minimax"; default_model = "MiniMax-H3"; base = "https://api.minimax.io"
    def h(self): return {"Authorization": f"Bearer {need('MINIMAX_API_KEY')}"}
    def submit(self, prompt, aspect, seconds, model, ref_image=None):
        content = [dict(type="text", text=prompt)]
        if ref_image: content.append(dict(type="image_url", image_url=dict(url=data_uri(ref_image)), role="reference_image"))
        d = jreq("POST", f"{self.base}/v2/video_generation", self.h(), dict(model=model, content=content, duration=clamp(seconds, 5, 15),
                 resolution="768P", ratio=aspect), what="minimax")
        if (d.get("base_resp") or {}).get("status_code", 0) != 0: raise ProviderError(f"minimax: {d['base_resp'].get('status_msg')}")
        return dict(id=d["task_id"])
    def poll(self, job):
        d = jreq("GET", f"{self.base}/v2/query/video_generation/{job['id']}", self.h(), what="minimax")
        t = d.get("task") or d; s = str(t.get("status", "")).lower()
        if s in ("fail", "failed"): raise ProviderError(f"minimax: {t.get('error') or (d.get('base_resp') or {}).get('status_msg') or 'failed'}")
        if s in ("success", "succeeded"):
            u = (t.get("content") or {}).get("url")
            if not u: raise ProviderError("minimax: no video url in result")
            return ("url", u)
        return None

class Sora(Adapter):
    """OpenAI Sora video API (POST /v1/videos). OpenAI removed the Videos API and all Sora 2 models on 2026-09-24, so
    this adapter refuses with a clear message unless SEATCREW_SORA_BASE points at a compatible endpoint you still have."""
    name = "sora"; default_model = "sora-2"
    def h(self): return {"Authorization": f"Bearer {need('OPENAI_API_KEY')}"}
    def submit(self, prompt, aspect, seconds, model, ref_image=None):
        base = os.getenv("SEATCREW_SORA_BASE")
        if not base: raise ProviderError("sora: OpenAI discontinued the Sora video API on 2026-09-24 - pick kling, runway, luma, gemini or minimax")
        body = dict(model=model, prompt=prompt, seconds=str(min((4, 8, 12), key=lambda s: abs(s - seconds))), size="720x1280" if aspect == "9:16" else "1280x720")
        d = jreq("POST", f"{base}/videos", self.h(), body, what="sora"); return dict(id=d["id"], base=base)
    def poll(self, job):
        d = jreq("GET", f"{job['base']}/videos/{job['id']}", self.h(), what="sora")
        if d.get("status") == "failed": raise ProviderError(f"sora: {(d.get('error') or {}).get('message', 'failed')}")
        return ("url", f"{job['base']}/videos/{job['id']}/content", self.h()) if d.get("status") == "completed" else None

class Replicate(Adapter):
    name = "replicate"; default_model = ""
    def h(self): return {"Authorization": f"Bearer {need('REPLICATE_API_TOKEN')}"}
    def submit(self, prompt, aspect, seconds, model, ref_image=None):
        if not model or "/" not in model: raise ProviderError("set video_model to a Replicate model slug, e.g. kwaivgi/kling-v2.1")
        inp = dict(prompt=prompt, aspect_ratio=aspect, duration=5 if seconds <= 5.5 else 10)
        if ref_image: inp["start_image"] = data_uri(ref_image)
        return jreq("POST", f"https://api.replicate.com/v1/models/{model}/predictions", self.h(), dict(input=inp), what="replicate")
    def poll(self, job):
        j = jreq("GET", job["urls"]["get"], self.h(), what="replicate")
        if j["status"] == "succeeded": o = j["output"]; return ("url", o[0] if isinstance(o, list) else o)
        if j["status"] in ("failed", "canceled"): raise ProviderError(f"replicate: {j.get('error') or j['status']}")
        return None

VIDEO = dict(kling=Kling, runway=Runway, luma=Luma, gemini=Gemini, minimax=MiniMax, sora=Sora, replicate=Replicate)
VIDEO_ENV = dict(kling=("KLING_API_KEY",), runway=("RUNWAYML_API_SECRET",), luma=("LUMA_AGENTS_API_KEY", "LUMAAI_API_KEY"),
                 gemini=("GEMINI_API_KEY", "GOOGLE_API_KEY"), minimax=("MINIMAX_API_KEY",), sora=("OPENAI_API_KEY",), replicate=("REPLICATE_API_TOKEN",))

# ---------------- catalog: recommended models (checked CHECKED; prices are rough - check current pricing) ----------------
def _e(id, kind, provider, model, good, env, docs, key, pricing, usd, unit, minutes=None, ref=False, clone=False, emotion=False, status="ok", note=""):
    return dict(id=id, kind=kind, provider=provider, model=model, good_at=good, env=list(env), docs=docs, key_url=key, pricing=pricing,
                rough_usd=usd, unit=unit, minutes=minutes, ref_image=ref, clone=clone, emotion=emotion, status=status, note=note, checked=CHECKED)
CATALOG = [
    _e("kling", "video", "Kling AI (可灵)", "kling-3.0", "cinematic motion, people & faces, 3-15 s, 1080p/4K, first/last frame", ["KLING_API_KEY"],
       "https://kling.ai/document-api/guides/get-started/quick-start", "https://kling.ai/dev/api-key", "https://kling.ai/dev/pricing", 0.10, "per second", 3, ref=True),
    _e("runway", "video", "Runway", "gen4.5", "polished cinematic shots, strong prompt following, 2-10 s; one key also reaches partner models", ["RUNWAYML_API_SECRET"],
       "https://docs.dev.runwayml.com/guides/using-the-api/", "https://dev.runwayml.com/", "https://docs.dev.runwayml.com/guides/pricing/", 0.12, "per second", 2, ref=True),
    _e("gemini", "video", "Google Gemini API", "gemini-omni-1.1-flash", "fast text/image-to-video with native audio, character consistency, 3-10 s (Veo 3.1 Preview shut down 2026-10-22)",
       ["GEMINI_API_KEY"], "https://ai.google.dev/gemini-api/docs/omni", "https://aistudio.google.com/apikey", "https://ai.google.dev/gemini-api/docs/pricing", 0.10, "per second", 2, ref=True),
    _e("luma", "video", "Luma AI", "ray-3.2", "dreamy camera moves, HDR, keyframes, 5/10 s", ["LUMA_AGENTS_API_KEY"],
       "https://docs.agents.lumalabs.ai/guides/videos/generation/", "https://platform.lumalabs.ai/", "https://docs.agents.lumalabs.ai/guides/pricing/", 0.08, "per second", 2, ref=True),
    _e("minimax", "video", "MiniMax Hailuo (海螺)", "MiniMax-H3", "great value, physics, reference-to-video for consistent characters, 4-15 s", ["MINIMAX_API_KEY"],
       "https://platform.minimax.io/docs/guides/video-generation", "https://platform.minimax.io/console/keys", "https://platform.minimax.io/docs/pricing/overview", 0.05, "per second", 3, ref=True),
    _e("replicate", "video", "Replicate", "(any slug, e.g. kwaivgi/kling-v2.1)", "one key for many hosted models; price depends on the model", ["REPLICATE_API_TOKEN"],
       "https://replicate.com/docs", "https://replicate.com/account/api-tokens", "https://replicate.com/pricing", None, "varies", 3, ref=True),
    _e("sora", "video", "OpenAI Sora", "sora-2", "DISCONTINUED: OpenAI removed the Sora video API on 2026-09-24", ["OPENAI_API_KEY"],
       "https://developers.openai.com/api/docs/deprecations", "https://platform.openai.com/api-keys", "https://developers.openai.com/api/docs/pricing", None, "-", status="retired"),
    _e("elevenlabs", "tts", "ElevenLabs", "eleven_multilingual_v2 (default) / eleven_v3 / eleven_v4 via SEATCREW_ELEVEN_MODEL", "most expressive voices, instant voice cloning, exact word timestamps", ["ELEVENLABS_API_KEY"],
       "https://elevenlabs.io/docs/overview/models", "https://elevenlabs.io/app/developers/api-keys", "https://elevenlabs.io/pricing/api", 0.10, "per 1K chars", clone=True, emotion=True),
    _e("minimax_tts", "tts", "MiniMax Speech", "speech-2.8-hd", "very natural Chinese, emotion parameter, voice clone from 10 s+", ["MINIMAX_API_KEY"],
       "https://platform.minimax.io/docs/api-reference/speech-t2a-http", "https://platform.minimax.io/console/keys", "https://platform.minimax.io/docs/pricing/overview", 0.10, "per 1K chars", clone=True, emotion=True),
    _e("doubao", "tts", "ByteDance Doubao / Volcano Engine (豆包语音)", "seed-tts-2.0", "natural zh-CN voices with emotions, voice clone (seed-icl-2.0)", ["VOLC_TTS_API_KEY"],
       "https://docs.volcengine.com/docs/doubao-voice/http-chunked-sse-unidirectional-streaming-v3?lang=zh", "https://console.volcengine.com/speech/app", "https://docs.volcengine.com/docs/doubao-voice/billing-instructions?lang=zh", 0.04, "per 1K chars (approx, CNY billed)", clone=True, emotion=True),
    _e("azure", "tts", "Azure AI Speech", "Neural / HD voices (zh-CN-XiaoxiaoNeural ...)", "real SSML speaking styles (sad, gentle, cheerful ...) for zh-CN/en/ja voices", ["AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"],
       "https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice", "https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices", "https://azure.microsoft.com/en-us/pricing/details/speech/", 0.015, "per 1K chars", emotion=True),
    _e("openai_tts", "tts", "OpenAI TTS", "gpt-4o-mini-tts", "tone via instructions; whisper word timing (deprecated, shuts down 2027-01-06)", ["OPENAI_API_KEY"],
       "https://developers.openai.com/api/docs/guides/text-to-speech", "https://platform.openai.com/api-keys", "https://developers.openai.com/api/docs/pricing", 0.015, "per 1K chars (approx)", emotion=True),
    _e("edge", "tts", "Microsoft Edge neural voices (edge-tts)", "zh-CN-XiaoxiaoNeural etc.", "free, no key, good neural voices; styles only approximated", [],
       "https://github.com/rany2/edge-tts", "", "", 0.0, "free"),
    # Character Studio: character sheets (image), image-to-3D, lip-sync. Prices not verified here - see each pricing page.
    _e("openai_image", "image", "OpenAI Images", "gpt-image-1", "edits with up to 10 reference photos - strong identity keeping for character sheets", ["OPENAI_API_KEY"],
       "https://platform.openai.com/docs/guides/image-generation", "https://platform.openai.com/api-keys", "https://openai.com/api/pricing/", None, "see pricing page", ref=True),
    _e("gemini_image", "image", "Google Gemini image", "gemini-nano-banana-2.1", "multi-reference character consistency (up to 4 refs), fast", ["GEMINI_API_KEY"],
       "https://ai.google.dev/gemini-api/docs/image-generation", "https://aistudio.google.com/apikey", "https://ai.google.dev/gemini-api/docs/pricing", None, "see pricing page", ref=True),
    _e("minimax_image", "image", "MiniMax image-01", "image-01", "subject_reference keeps one face consistent, cheap", ["MINIMAX_API_KEY"],
       "https://platform.minimax.io/docs/api-reference/image-generation-t2i", "https://platform.minimax.io/console/keys", "https://platform.minimax.io/docs/pricing/overview", None, "see pricing page", ref=True),
    _e("replicate_image", "image", "Replicate FLUX Kontext", "black-forest-labs/flux-kontext-pro", "edit-from-reference (one ref) - same person, new pose/expression", ["REPLICATE_API_TOKEN"],
       "https://replicate.com/black-forest-labs/flux-kontext-pro", "https://replicate.com/account/api-tokens", "https://replicate.com/pricing", None, "see pricing page", ref=True),
    _e("meshy", "model3d", "Meshy image-to-3D", "meshy (latest)", "textured GLB from one image, good for characters", ["MESHY_API_KEY"],
       "https://docs.meshy.ai/en/api/image-to-3d", "https://www.meshy.ai/settings/api", "https://docs.meshy.ai/en/api/pricing", None, "see pricing page"),
    _e("tripo", "model3d", "Tripo3D", "v3 image-to-model", "fast textured GLB", ["TRIPO_API_KEY"],
       "https://platform.tripo3d.ai/docs", "https://platform.tripo3d.ai/api-keys", "https://platform.tripo3d.ai/pricing", None, "see pricing page"),
    _e("replicate_3d", "model3d", "Replicate TRELLIS / Hunyuan3D", "firtoz/trellis (SEATCREW_3D_MODEL)", "open models, pay per run", ["REPLICATE_API_TOKEN"],
       "https://replicate.com/firtoz/trellis", "https://replicate.com/account/api-tokens", "https://replicate.com/pricing", None, "see pricing page"),
    _e("kling_lipsync", "lipsync", "Kling advanced lip-sync", "advanced-lip-sync", "re-times mouths in a clip to a 2-60 s line; needs a public clip URL", ["KLING_API_KEY"],
       "https://kling.ai/document-api", "https://kling.ai/dev/api-key", "https://kling.ai/dev/pricing", None, "see pricing page"),
    _e("replicate_lipsync", "lipsync", "Replicate lip-sync", "sync/lipsync-2 (SEATCREW_LIPSYNC_MODEL)", "video + audio -> lip-synced video", ["REPLICATE_API_TOKEN"],
       "https://replicate.com/sync/lipsync-2", "https://replicate.com/account/api-tokens", "https://replicate.com/pricing", None, "see pricing page"),
    _e("draft", "video", "Offline draft cards", "-", "free, offline, labeled DRAFT - for checking timing only", [], "", "", "", 0.0, "free"),
]
TIERS = {"video": dict(best_quality=["kling", "runway", "gemini"], best_value=["minimax", "luma"], free_draft=["draft"]),
         "tts": dict(best_quality=["elevenlabs", "minimax_tts"], best_value=["doubao", "azure", "openai_tts"], free_draft=["edge"])}

def entry(i): return next(e for e in CATALOG if e["id"] == i)
_I18N = None
def i18n():
    """Translated descriptions/units for the Recommended models cards (seatcrew/video/models_i18n.json)."""
    global _I18N
    if _I18N is None:
        import json
        from pathlib import Path
        _I18N = json.loads((Path(__file__).resolve().parent / "models_i18n.json").read_text(encoding="utf-8"))
        _I18N.pop("_note", None)
    return _I18N
def key_var(i):
    """The env var a pasted key is saved under (first one listed), or None for key-free entries."""
    e = entry(i); return e["env"][0] if e["env"] and e["status"] != "retired" else None
def recommended():
    return {k: {t: [dict(entry(i), configured=configured(i)) for i in ids] for t, ids in tiers.items()} for k, tiers in TIERS.items()}
def configured(i):
    e = entry(i); return not e["env"] or any(os.getenv(x) for x in e["env"][:1])

def estimate(shots, provider):
    """Rough cost (USD) + wall-time (minutes) before a run. Never authoritative - shown with 'check current pricing'."""
    e = entry(provider) if any(x["id"] == provider for x in CATALOG) else None
    secs = sum(float(s.get("duration", 4)) for s in shots); n = len(shots)
    usd = None if not e or e["rough_usd"] is None else round(e["rough_usd"] * secs, 2)
    mins = None if not e or not e["minutes"] else round(e["minutes"] * n / 2 + 1, 1)   # ~2 jobs in flight
    return dict(provider=provider, shots=n, seconds=round(secs, 1), usd=usd, minutes=mins, note="rough estimate - check current pricing", pricing=e["pricing"] if e else "")

TEST_URLS = dict(kling=("GET", "https://api-singapore.klingai.com/tasks?page_size=1"), runway=("GET", "https://api.dev.runwayml.com/v1/organization"),
                 luma=("GET", "https://agents.lumalabs.ai/v1/generations?limit=1"), gemini=("GET", "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"),
                 minimax=("GET", "https://api.minimax.io/v1/get_voice?voice_type=system"), replicate=("GET", "https://api.replicate.com/v1/account"),
                 elevenlabs=("GET", "https://api.elevenlabs.io/v1/user"), openai_tts=("GET", "https://api.openai.com/v1/models"))
def test_key(i):
    """Cheap authenticated read (no generation, no cost) -> {ok, message}. Never returns or logs the key."""
    try:
        if i == "edge": return dict(ok=True, message="no key needed")
        if i == "azure":
            k = need("AZURE_SPEECH_KEY"); r = need("AZURE_SPEECH_REGION")
            req("GET", f"https://{r}.tts.speech.microsoft.com/cognitiveservices/voices/list", {"Ocp-Apim-Subscription-Key": k}, retries=0, timeout=20, what="azure")
        elif i == "doubao": need("VOLC_TTS_API_KEY", "VOLC_TTS_ACCESS_KEY"); return dict(ok=True, message="key is set (Volcano has no free key-check call; run an audition)")
        elif i == "sora": return dict(ok=False, message="Sora API discontinued 2026-09-24")
        else:
            m, u = TEST_URLS["minimax" if i == "minimax_tts" else i]; e = entry(i)["env"]; k = need(*e)
            h = {"x-goog-api-key": k} if i == "gemini" else {"xi-api-key": k} if i == "elevenlabs" else {"Authorization": f"Bearer {k}"}
            if i == "runway": h["X-Runway-Version"] = "2024-11-06"
            req(m, u, h, retries=0, timeout=20, what=i)
        return dict(ok=True, message="key works")
    except (ProviderError, StopIteration, KeyError) as ex: return dict(ok=False, message=str(ex))

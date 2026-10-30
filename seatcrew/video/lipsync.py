"""LIP-SYNC step (optional, after VOICE + VISUALS): re-time a clip's mouth to the character's line.

  kling      identify-face -> advanced-lip-sync (one face, audio 2-60 s). Kling needs the video as a URL it can fetch:
             set SEATCREW_PUBLIC_MEDIA_URL to where your clips are served, or use clips Kling generated (video_url kept).
  replicate  any lip-sync slug (default sync/lipsync-2) with video + audio as data URIs                REPLICATE_API_TOKEN
  none       keep the clip as-is (mouth movement is only whatever the video model produced)

Live-test status: mocked HTTP only (tests/test_characters.py). Without a lip-sync backend, lip-sync is approximate."""
import base64, os, time
from pathlib import Path
from . import providers as PV

def _audio_uri(p):
    p = Path(p); mt = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}.get(p.suffix.lower(), "audio/wav")
    return f"data:{mt};base64,{base64.b64encode(p.read_bytes()).decode()}"

class Kling:
    name = "kling"; base = "https://api-singapore.klingai.com"; poll_every = 6; max_wait = 900
    def h(self): return {"Authorization": f"Bearer {PV.need('KLING_API_KEY')}"}
    def run(self, video, audio, out, video_url=None, sleep=time.sleep, clock=time.time):
        url = video_url or (os.getenv("SEATCREW_PUBLIC_MEDIA_URL", "").rstrip("/") + "/" + Path(video).name if os.getenv("SEATCREW_PUBLIC_MEDIA_URL") else None)
        if not url: raise PV.ProviderError("kling lip-sync needs a public video URL (SEATCREW_PUBLIC_MEDIA_URL) or a Kling-generated clip")
        f = PV.jreq("POST", f"{self.base}/v1/videos/identify-face", self.h(), dict(video_url=url), what="kling identify-face")
        if f.get("code", 0) != 0: raise PV.ProviderError(f"kling identify-face: {f.get('message')}")
        d = f.get("data") or {}; faces = d.get("face_data") or []
        if not faces: raise PV.ProviderError("kling lip-sync: no face found in the clip")
        from . import ff
        ms = int(min(60.0, ff.duration(audio)) * 1000)
        if ms < 2000: raise PV.ProviderError("kling lip-sync: the line is shorter than 2 s (Kling minimum)")
        body = dict(session_id=d["session_id"], face_choose=[dict(face_id=str(faces[0]["face_id"]), sound_file=base64.b64encode(Path(audio).read_bytes()).decode(),
                    sound_start_time=0, sound_end_time=ms, sound_insert_time=0, sound_volume=1, original_audio_volume=0)])
        j = PV.jreq("POST", f"{self.base}/v1/videos/advanced-lip-sync", self.h(), body, what="kling lip-sync")
        if j.get("code", 0) != 0: raise PV.ProviderError(f"kling lip-sync: {j.get('message')}")
        tid = j["data"]["task_id"]; t0 = clock()
        while clock() - t0 < self.max_wait:
            r = (PV.jreq("GET", f"{self.base}/v1/videos/advanced-lip-sync/{tid}", self.h(), what="kling lip-sync").get("data") or {})
            if r.get("task_status") == "failed": raise PV.ProviderError(f"kling lip-sync: {r.get('task_status_msg') or 'failed'}")
            if r.get("task_status") == "succeed":
                v = ((r.get("task_result") or {}).get("videos") or [{}])[0].get("url")
                if not v: raise PV.ProviderError("kling lip-sync: no video url")
                Path(out).write_bytes(PV.req("GET", v, {}, timeout=300, what="kling download")[0]); return Path(out)
            sleep(self.poll_every)
        raise PV.ProviderError("kling lip-sync: timed out")

class Replicate:
    name = "replicate"; default_model = "sync/lipsync-2"; poll_every = 4; max_wait = 900
    def __init__(self, model=None): self.model = model or os.getenv("SEATCREW_LIPSYNC_MODEL") or self.default_model
    def run(self, video, audio, out, video_url=None, sleep=time.sleep, clock=time.time):
        h = {"Authorization": f"Bearer {PV.need('REPLICATE_API_TOKEN')}"}
        j = PV.jreq("POST", f"https://api.replicate.com/v1/models/{self.model}/predictions", h, dict(input=dict(video=video_url or _video_uri(video), audio=_audio_uri(audio))), what="replicate lip-sync")
        t0 = clock()
        while clock() - t0 < self.max_wait:
            if j.get("status") == "succeeded":
                o = j["output"]; u = o[0] if isinstance(o, list) else o
                Path(out).write_bytes(PV.req("GET", u, {}, timeout=300, what="replicate download")[0]); return Path(out)
            if j.get("status") in ("failed", "canceled"): raise PV.ProviderError(f"replicate lip-sync: {j.get('error') or j['status']}")
            sleep(self.poll_every); j = PV.jreq("GET", j["urls"]["get"], h, what="replicate lip-sync")
        raise PV.ProviderError("replicate lip-sync: timed out")

def _video_uri(p): return f"data:video/mp4;base64,{base64.b64encode(Path(p).read_bytes()).decode()}"

ADAPTERS = dict(kling=Kling, replicate=Replicate)

def apply(video, audio, out, pref="none", video_url=None):
    """-> (path, info). 'none' or a failure keeps the original clip and says so (lip-sync = approximate)."""
    if pref in (None, "", "none"): return Path(video), dict(lipsync="none", note="approximate - no lip-sync backend")
    try: return ADAPTERS[pref]().run(video, audio, out, video_url=video_url), dict(lipsync=pref)
    except (PV.ProviderError, KeyError) as e: return Path(video), dict(lipsync="failed", error=str(e), note="kept original clip - lip-sync approximate")

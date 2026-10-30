"""Cloud TTS backends with real emotion control + voice cloning: MiniMax Speech, ByteDance Doubao (Volcano Engine), Azure AI Speech,
plus ElevenLabs instant voice cloning. Same contract as tts.py backends: (audio_path, words, info).
Keys come from the environment only. Cloned voice ids are returned so the Character Voice Library can save them - keys never are.
All of these are tested with mocked HTTP only (tests/test_providers.py); see docs/VIDEO.md for live-test status."""
import base64, json, os, uuid
from pathlib import Path
from xml.sax.saxutils import escape
from . import ff
from .providers import req, jreq, need, ProviderError

# our line emotions -> each vendor's emotion / style vocabulary
MINIMAX_EMO = dict(gentle="calm", sad="sad", tender="calm", hesitant="fearful", cheerful="happy", excited="surprised", calm="calm",
                   serious="calm", tired="sad", whisper="whisper", worried="fearful")
DOUBAO_EMO = dict(gentle="tender", sad="sad", tender="tender", hesitant="shy", cheerful="happy", excited="excited", calm="neutral",
                  serious="coldness", tired="depressed", whisper="tender", worried="tension")
AZURE_STYLE = dict(gentle=("gentle", 1), sad=("sad", 1.2), tender=("affectionate", 1), hesitant=("sorry", 0.8), cheerful=("cheerful", 1),
                   excited=("cheerful", 1.6), calm=("calm", 1), serious=("serious", 1), tired=("sad", 0.6), whisper=("whisper", 1), worried=("fearful", 0.6))
MINIMAX_MODEL, DOUBAO_RESOURCE, DOUBAO_CLONE_RESOURCE = "speech-2.8-hd", "seed-tts-2.0", "seed-icl-2.0"
DOUBAO_VOICE = "zh_female_vv_uranus_bigtts"

def _timed(text, out, lang, backend, voice, extra=None):
    """Word timings: whisper-1 (exact) when OPENAI_API_KEY is set, else estimated from the audio length."""
    from . import tts as T
    sync, words = "estimated", None
    if os.getenv("OPENAI_API_KEY"):
        try: words = T.realign(text, T.whisper_words(out, os.getenv("OPENAI_API_KEY"), lang)); sync = "exact"
        except T.TTSError: words = None
    return out, words or T.estimate(text, ff.duration(out)), dict(backend=backend, voice=voice, sync=sync, **(extra or {}))

def _err(e):
    from .tts import TTSError
    return TTSError(str(e))

def minimax(text, out, voice=None, lang="zh-CN", model=None, style=None, speed=1.0, pitch=0, vol=1.0):
    try:
        v = voice or ("female-shaonv" if lang.startswith("zh") else "English_Graceful_Lady")
        vs = dict(voice_id=v, speed=round(max(0.5, min(2.0, speed)), 2), vol=round(max(0.1, min(10, vol)), 2), pitch=int(max(-12, min(12, pitch))))
        m = model or MINIMAX_MODEL; emo = MINIMAX_EMO.get(style or "")
        if emo == "whisper" and "2.8" in m: emo = "calm"            # speech-2.8 has no whisper emotion
        if emo: vs["emotion"] = emo
        d = jreq("POST", "https://api.minimax.io/v1/t2a_v2", {"Authorization": f"Bearer {need('MINIMAX_API_KEY')}"},
                 dict(model=m, text=text, stream=False, voice_setting=vs, audio_setting=dict(sample_rate=32000, format="mp3", channel=1),
                      language_boost="auto"), what="minimax tts")
        br = d.get("base_resp") or {}
        if br.get("status_code", 0) != 0: raise ProviderError(f"minimax tts: {br.get('status_msg')}")
        a = (d.get("data") or {}).get("audio")
        if not a: raise ProviderError("minimax tts: no audio")
        out = str(Path(out).with_suffix(".mp3")); Path(out).write_bytes(bytes.fromhex(a))
        return _timed(text, out, lang, "minimax", v, dict(emotion=emo or "auto"))
    except ProviderError as e: raise _err(e)

def _volc_headers(resource):
    k = os.getenv("VOLC_TTS_API_KEY")
    if k: return {"X-Api-Key": k, "X-Api-Resource-Id": resource}
    return {"X-Api-App-Id": need("VOLC_TTS_APPID"), "X-Api-Access-Key": need("VOLC_TTS_API_KEY", "VOLC_TTS_ACCESS_KEY"), "X-Api-Resource-Id": resource}

def doubao(text, out, voice=None, lang="zh-CN", model=None, style=None, speed=0, loudness=0):
    """Volcano Engine Doubao TTS 2.0, HTTP unidirectional streaming (NDJSON chunks of base64 audio). Cloned S_xxx voices use seed-icl-2.0."""
    try:
        v = voice or DOUBAO_VOICE; res = model or (DOUBAO_CLONE_RESOURCE if v.startswith("S_") else DOUBAO_RESOURCE)
        ap = dict(format="mp3", sample_rate=24000, speech_rate=int(max(-50, min(100, speed))), loudness_rate=int(max(-50, min(100, loudness))))
        emo = DOUBAO_EMO.get(style or "")
        if emo: ap["emotion"] = emo; ap["emotion_scale"] = 4
        raw, _ = req("POST", "https://openspeech.bytedance.com/api/v3/tts/unidirectional", _volc_headers(res),
                     dict(user=dict(uid="seatcrew"), req_params=dict(text=text, speaker=v, audio_params=ap)), timeout=120, what="doubao tts")
        audio = bytearray()
        for ln in raw.decode("utf-8", "replace").splitlines():
            if not ln.strip(): continue
            try: j = json.loads(ln)
            except ValueError: continue
            c = j.get("code", 0)
            if c not in (0, 20000000): raise ProviderError(f"doubao tts: {j.get('message') or c}")
            if j.get("data"): audio.extend(base64.b64decode(j["data"]))
        if not audio: raise ProviderError("doubao tts: no audio")
        out = str(Path(out).with_suffix(".mp3")); Path(out).write_bytes(bytes(audio))
        return _timed(text, out, lang, "doubao", v, dict(emotion=emo or "auto"))
    except ProviderError as e: raise _err(e)

def azure_ssml(text, voice, lang, style=None, rate=0, pitch=0, volume=0):
    st = AZURE_STYLE.get(style or "")
    body = escape(text)
    if rate or pitch or volume: body = f'<prosody rate="{rate:+d}%" pitch="{pitch:+d}Hz" volume="{volume:+d}%">{body}</prosody>'
    if st: body = f'<mstts:express-as style="{st[0]}" styledegree="{st[1]}">{body}</mstts:express-as>'
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{escape(lang)}">'
            f'<voice name="{escape(voice)}">{body}</voice></speak>')

def azure(text, out, voice=None, lang="zh-CN", model=None, style=None, rate=0, pitch=0, volume=0):
    """Azure AI Speech REST with real SSML <mstts:express-as> styles (voice must support the style; others ignore it)."""
    try:
        from .tts import EDGE_VOICES
        v = voice or EDGE_VOICES.get(lang, EDGE_VOICES["en"]); region = need("AZURE_SPEECH_REGION")
        raw, ct = req("POST", f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                      {"Ocp-Apim-Subscription-Key": need("AZURE_SPEECH_KEY"), "Content-Type": "application/ssml+xml",
                       "X-Microsoft-OutputFormat": "audio-48khz-192kbitrate-mono-mp3", "User-Agent": "seatcrew"},
                      data=azure_ssml(text, v, lang, style, rate, pitch, volume).encode("utf-8"), what="azure tts")
        if len(raw) < 200: raise ProviderError("azure tts: empty audio")
        out = str(Path(out).with_suffix(".mp3")); Path(out).write_bytes(raw)
        return _timed(text, out, lang, "azure", v, dict(style=(AZURE_STYLE.get(style or "") or ("none",))[0]))
    except ProviderError as e: raise _err(e)

def _multipart(fields, files):
    b = uuid.uuid4().hex; parts = []
    for n, v in fields: parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n".encode())
    for n, fn, data in files:
        parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{n}\"; filename=\"{fn}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{b}--\r\n".encode()); return b"".join(parts), f"multipart/form-data; boundary={b}"

def _sample(path):
    p = Path(path)
    if not p.is_file(): raise ProviderError(f"voice sample not found: {p.name}")
    if p.stat().st_size > 20 * 1024 * 1024: raise ProviderError("voice sample too large (max 20 MB)")
    return p

def clone(backend, name, sample, voice_id=None):
    """Clone a voice from your own recording (you must have the speaker's consent). Returns the new voice id (never a key)."""
    p = _sample(sample)
    if backend == "elevenlabs":
        data, ct = _multipart([("name", name), ("description", "SeatCrew character voice")], [("files", p.name, p.read_bytes())])
        d = jreq("POST", "https://api.elevenlabs.io/v1/voices/add", {"xi-api-key": need("ELEVENLABS_API_KEY"), "Content-Type": ct}, data=data, timeout=300, what="elevenlabs clone")
        return d["voice_id"]
    if backend == "minimax":
        h = {"Authorization": f"Bearer {need('MINIMAX_API_KEY')}"}
        data, ct = _multipart([("purpose", "voice_clone")], [("file", p.name, p.read_bytes())])
        up = jreq("POST", "https://api.minimax.io/v1/files/upload", dict(h, **{"Content-Type": ct}), data=data, timeout=300, what="minimax upload")
        fid = (up.get("file") or {}).get("file_id")
        if not fid: raise ProviderError("minimax clone: upload returned no file_id")
        vid = voice_id or f"SeatCrew{uuid.uuid4().hex[:10]}"
        d = jreq("POST", "https://api.minimax.io/v1/voice_clone", h, dict(file_id=fid, voice_id=vid), timeout=300, what="minimax clone")
        if (d.get("base_resp") or {}).get("status_code", 0) != 0: raise ProviderError(f"minimax clone: {d['base_resp'].get('status_msg')}")
        return vid
    if backend == "doubao":
        if not voice_id or not voice_id.startswith("S_"): raise ProviderError("doubao clone: pass the speaker id (S_...) you got in the Volcano console")
        d = jreq("POST", "https://openspeech.bytedance.com/api/v1/mega_tts/audio/upload",
                 {"Authorization": f"Bearer;{need('VOLC_TTS_ACCESS_KEY', 'VOLC_TTS_API_KEY')}", "Resource-Id": "seed-icl-2.0"},
                 dict(appid=need("VOLC_TTS_APPID"), speaker_id=voice_id, audios=[dict(audio_bytes=base64.b64encode(p.read_bytes()).decode(),
                      audio_format=p.suffix.lstrip(".") or "wav")], source=2, language=0, model_type=4), timeout=300, what="doubao clone")
        if (d.get("BaseResp") or {}).get("StatusCode", 0) != 0: raise ProviderError(f"doubao clone: {d['BaseResp'].get('StatusMessage')}")
        return voice_id
    raise ProviderError(f"voice cloning is not supported for {backend} (use elevenlabs, minimax or doubao)")

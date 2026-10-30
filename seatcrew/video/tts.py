"""Pluggable text-to-speech. Every backend returns (audio_path, words, info) where
words = [{"w": "word", "start": s, "end": s}, ...] relative to the start of that audio file.

Quality tiers
  elevenlabs   final  - character-level timestamps from the API (exact karaoke sync)
  openai       final  - gpt-4o-mini-tts / tts-1-hd voice; word times from whisper-1 word timestamps (exact), else estimated
  edge         final  - free Microsoft neural voices via the `edge-tts` package (pip install edge-tts); WordBoundary times
  draft        DRAFT  - offline: ffmpeg flite robot voice (or silence) + estimated timings. Labeled draft everywhere.
  mock         tests only
Keys come from the environment only (OPENAI_API_KEY, ELEVENLABS_API_KEY) and are never written anywhere."""
import base64, json, os, re, urllib.request, uuid
from pathlib import Path
from . import ff

EDGE_VOICES = {"en": "en-US-AndrewMultilingualNeural", "zh-CN": "zh-CN-XiaoxiaoNeural", "zh-TW": "zh-TW-HsiaoChenNeural", "ja": "ja-JP-NanamiNeural", "es": "es-ES-ElviraNeural"}
OPENAI_VOICE, OPENAI_MODEL = "alloy", "gpt-4o-mini-tts"
ELEVEN_VOICE, ELEVEN_MODEL = "21m00Tcm4TlvDq8ikWAM", "eleven_multilingual_v2"
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
FINAL = ("elevenlabs", "openai", "edge")

class TTSError(RuntimeError): pass

def tokens(text):
    """Words for subtitles: whitespace words for Latin scripts, single characters (keeping trailing punctuation) for CJK."""
    out = []
    for w in text.split():
        if CJK.search(w):
            for ch in re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff][^\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]*|[^\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]+", w): out.append(ch)
        else: out.append(w)
    return out

def estimate(text, dur, lead=0.0):
    """Spread words over the audio by character weight (used when a backend gives no timings)."""
    ws = tokens(text)
    if not ws: return []
    wt = [max(1, len(re.sub(r"\W", "", w))) + (2 if re.search(r"[,.;:!?，。！？；：]$", w) else 0) for w in ws]
    span = max(0.1, dur - lead - 0.05); t = lead; out = []
    for w, k in zip(ws, wt):
        d = span * k / sum(wt); out.append(dict(w=w, start=round(t, 3), end=round(t + d * 0.92, 3))); t += d
    return out

def _http(url, headers, body=None, data=None, timeout=120):
    req = urllib.request.Request(url, data=data if data is not None else (json.dumps(body).encode() if body is not None else None), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise TTSError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
    except (urllib.error.URLError, TimeoutError, OSError) as e: raise TTSError(f"network: {e}")

def _need(env):
    k = os.getenv(env)
    if not k: raise TTSError(f"{env} is not set")
    return k

def elevenlabs(text, out, voice=None, lang="en", model=None):
    key = _need("ELEVENLABS_API_KEY"); vid = voice or ELEVEN_VOICE
    raw, _ = _http(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/with-timestamps?output_format=mp3_44100_192",
                   {"xi-api-key": key, "Content-Type": "application/json"}, dict(text=text, model_id=model or ELEVEN_MODEL))
    j = json.loads(raw); Path(out).write_bytes(base64.b64decode(j["audio_base64"]))
    al = j.get("alignment") or j.get("normalized_alignment") or {}
    chars, st, en = al.get("characters", []), al.get("character_start_times_seconds", []), al.get("character_end_times_seconds", [])
    words, cur = [], None
    for c, s, e in zip(chars, st, en):
        if c.isspace():
            if cur: words.append(cur); cur = None
            continue
        if CJK.search(c):
            if cur: words.append(cur)
            cur = None; words.append(dict(w=c, start=s, end=e)); continue
        if cur is None: cur = dict(w=c, start=s, end=e)
        else: cur["w"] += c; cur["end"] = e
    if cur: words.append(cur)
    words = _attach_punct(words)
    return out, words or estimate(text, ff.duration(out)), dict(backend="elevenlabs", voice=vid, sync="exact" if words else "estimated")

def _attach_punct(words):
    out = []
    for w in words:
        if out and re.fullmatch(r"[^\w]+", w["w"]): out[-1]["w"] += w["w"]; out[-1]["end"] = w["end"]
        else: out.append(dict(w))
    return [dict(w=w["w"], start=round(float(w["start"]), 3), end=round(float(w["end"]), 3)) for w in out]

def openai(text, out, voice=None, lang="en", model=None):
    key = _need("OPENAI_API_KEY")
    raw, _ = _http("https://api.openai.com/v1/audio/speech", {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                   dict(model=model or OPENAI_MODEL, voice=voice or OPENAI_VOICE, input=text, response_format="wav"))
    Path(out).write_bytes(raw); sync = "estimated"
    try:
        words = whisper_words(out, key, lang); sync = "exact"
        words = realign(text, words)
    except TTSError: words = estimate(text, ff.duration(out))
    return out, words, dict(backend="openai", voice=voice or OPENAI_VOICE, sync=sync)

def whisper_words(path, key, lang="en"):
    """OpenAI whisper-1 word timestamps for an audio file."""
    b = uuid.uuid4().hex; parts = []
    def field(n, v): parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n".encode())
    field("model", "whisper-1"); field("response_format", "verbose_json"); field("timestamp_granularities[]", "word"); field("language", lang.split("-")[0])
    parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode() + Path(path).read_bytes() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    raw, _ = _http("https://api.openai.com/v1/audio/transcriptions", {"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={b}"}, data=b"".join(parts))
    ws = json.loads(raw).get("words") or []
    if not ws: raise TTSError("no word timestamps")
    return [dict(w=w["word"], start=float(w["start"]), end=float(w["end"])) for w in ws]

def realign(text, heard):
    """Keep the script's exact words (spelling/punctuation) but take times from the recognized words, in order."""
    ws = tokens(text)
    if not heard: return estimate(text, 1)
    out = []
    for i, w in enumerate(ws):
        j = min(len(heard) - 1, round(i * (len(heard) - 1) / max(1, len(ws) - 1))) if len(ws) != len(heard) else i
        out.append(dict(w=w, start=round(heard[j]["start"], 3), end=round(heard[j]["end"], 3)))
    for a, b in zip(out, out[1:]):                       # keep monotonic
        if b["start"] < a["start"]: b["start"] = a["start"]
        if b["end"] < b["start"]: b["end"] = b["start"] + 0.05
    return out

def edge(text, out, voice=None, lang="en", model=None, rate="+0%"):
    try: import edge_tts, asyncio
    except ImportError: raise TTSError("edge-tts is not installed (pip install edge-tts)")
    v = voice or EDGE_VOICES.get(lang, EDGE_VOICES["en"]); words = []; audio = bytearray()
    async def go():
        try: c = edge_tts.Communicate(text, v, rate=rate, boundary="WordBoundary")
        except TypeError: c = edge_tts.Communicate(text, v, rate=rate)
        async for ch in c.stream():
            if ch["type"] == "audio": audio.extend(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7; words.append(dict(w=ch["text"], start=round(s, 3), end=round(s + ch["duration"] / 1e7, 3)))
    import time
    for attempt in range(3):  # the free service drops requests now and then
        words.clear(); audio.clear()
        try: asyncio.run(go()); break
        except Exception as e:
            if attempt == 2: raise TTSError(f"edge-tts: {type(e).__name__}: {e}")
            time.sleep(1.5 * (attempt + 1))
    if not audio: raise TTSError("edge-tts returned no audio")
    Path(out).write_bytes(bytes(audio))
    if words: words = realign(text, words) if len(words) != len(tokens(text)) else [dict(w=t, start=w["start"], end=w["end"]) for t, w in zip(tokens(text), words)]
    return out, words or estimate(text, ff.duration(out)), dict(backend="edge", voice=v, sync="exact" if words else "estimated")

def draft(text, out, voice=None, lang="en", model=None):
    """Offline DRAFT voice: robotic flite (English only) or silence, timed by an estimate. Never final quality."""
    n = len(tokens(text)); dur = max(1.2, n / (2.6 if not CJK.search(text) else 4.5) + 0.4)
    out = str(Path(out).with_suffix(".wav"))
    if lang.startswith("en") and ff.has_filter("flite") and text:
        safe = re.sub(r"[^A-Za-z0-9 ,.!?'-]", " ", text)
        Path(out + ".txt").write_text(safe, encoding="utf-8")
        ff.run(["-f", "lavfi", "-i", f"flite=textfile='{Path(out).name}.txt':voice=slt", "-ar", "48000", "-ac", "1", Path(out).name], cwd=str(Path(out).parent))
        dur = ff.duration(out); kind = "flite"
    else:
        ff.run(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{dur:.2f}", out]); kind = "silent"
    return out, estimate(text, dur, 0.05), dict(backend="draft", voice=kind, sync="estimated", draft=True)

def mock(text, out, voice=None, lang="en", model=None):
    """Tests: a quiet tone per word so timings are known exactly."""
    ws = tokens(text); out = str(Path(out).with_suffix(".wav")); per = 0.35
    dur = max(0.8, len(ws) * per + 0.2)
    ff.run(["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur:.2f}", "-af", "volume=0.25", "-ac", "1", out])
    return out, [dict(w=w, start=round(0.1 + i * per, 3), end=round(0.1 + i * per + per * 0.9, 3)) for i, w in enumerate(ws)], dict(backend="mock", voice="sine", sync="exact")

BACKENDS = dict(elevenlabs=elevenlabs, openai=openai, edge=edge, draft=draft, mock=mock)

def auto_order(pref="auto"):
    if pref and pref != "auto": return [pref]
    order = [b for b, env in (("elevenlabs", "ELEVENLABS_API_KEY"), ("openai", "OPENAI_API_KEY")) if os.getenv(env)]
    try:
        import edge_tts  # noqa: F401
        order.append("edge")
    except ImportError: pass
    return order

def synth(text, out, pref="auto", voice=None, lang="en", allow_draft=True, model=None):
    """Try backends in order. Returns (path, words, info). Falls back to the labeled draft voice only if allowed."""
    errs = []
    for b in auto_order(pref):
        if b not in BACKENDS: raise TTSError(f"unknown TTS backend {b}")
        try:
            ext = ".wav" if b in ("openai", "draft", "mock") else ".mp3"
            return BACKENDS[b](text, str(Path(out).with_suffix(ext)), voice=voice, lang=lang, model=model)
        except (TTSError, ff.FFError) as e: errs.append(f"{b}: {e}")
    if allow_draft and pref in ("auto", "draft"):
        p, w, info = draft(text, out, lang=lang); info["fallback_reasons"] = errs; return p, w, info
    raise TTSError("; ".join(errs) or "no TTS backend available")

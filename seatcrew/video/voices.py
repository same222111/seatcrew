"""Character Voice Library: every character (name, description, gender, age) is bound to ONE persistent voice profile that
is reused for every line, every shot and every future video.

* library file: voices/characters.yaml in the data folder (a video folder may add its own characters.yaml on top)
* profile: backend (auto|edge|openai|elevenlabs), voice ids per backend, rate %, pitch Hz, volume %, default style, subtitle color
* emotion/style per line (gentle, sad, cheerful, ...). The free edge-tts endpoint does not accept Azure SSML <mstts:express-as>
  styles, so for edge a style is rendered as a prosody preset (rate/pitch/volume offsets); OpenAI gpt-4o-mini-tts gets it as
  spoken `instructions`; ElevenLabs gets lower stability for stronger emotion.
* no keys are ever stored here - backends read keys from the environment only."""
import copy, hashlib, json, re, wave
from pathlib import Path
import yaml
from . import ff, tts as TTS

LIB_REL = Path("voices") / "characters.yaml"
NAME_RE = re.compile(r"^[\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af][\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af \-]{0,39}$")
BACKENDS = ("auto", "edge", "azure", "minimax", "doubao", "openai", "elevenlabs")
GENDERS = ("female", "male", "neutral")
AGES = ("child", "teen", "young", "adult", "mature", "elderly")
OPENAI_VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse")
# style -> (rate %, pitch Hz, volume %, OpenAI instruction, ElevenLabs stability)
STYLES = {
    "neutral": (0, 0, 0, "", 0.5),
    "gentle": (-6, -2, -6, "Speak gently and warmly, softly, close to the listener.", 0.45),
    "sad": (-12, -4, -10, "Speak slowly with a sad, tender voice that almost breaks.", 0.3),
    "tender": (-8, -1, -8, "Speak with loving tenderness, quiet and warm.", 0.4),
    "hesitant": (-10, -2, -8, "Speak hesitantly, with small pauses, unsure.", 0.35),
    "cheerful": (6, 4, 0, "Speak cheerfully, smiling.", 0.4),
    "excited": (10, 6, 4, "Speak with excitement and energy.", 0.3),
    "calm": (-4, -1, -4, "Speak calmly and evenly.", 0.6),
    "serious": (-3, -3, 0, "Speak seriously and firmly.", 0.6),
    "tired": (-10, -3, -10, "Speak tiredly, low energy, a little sigh in the voice.", 0.4),
    "whisper": (-8, -2, -30, "Whisper softly.", 0.4),
    "worried": (-4, 2, -4, "Speak with gentle worry and care.", 0.35),
}
COLORS = ("#FFE500", "#7FD4FF", "#FF9EC4", "#B6F09C", "#FFB86B", "#C9A7FF")

# Curated presets: kind -> per-language (edge voice, rate %, pitch Hz, volume %, style, openai voice). Labels come from locales (vk_<kind>).
KINDS = {  # kind: (gender, age)
    "narrator_female": ("female", "adult"), "narrator_male": ("male", "adult"), "young_female_gentle": ("female", "young"),
    "young_female_lively": ("female", "young"), "young_male": ("male", "young"), "mature_female": ("female", "mature"),
    "mature_male": ("male", "mature"), "elderly_woman": ("female", "elderly"), "elderly_man": ("male", "elderly"),
    "child_girl": ("female", "child"), "child_boy": ("male", "child"), "news_anchor": ("male", "adult")}
_P = {
    "zh-CN": dict(narrator_female=("zh-CN-XiaoxiaoNeural", -6, -2, 0, "gentle"), narrator_male=("zh-CN-YunxiNeural", -8, -3, 0, "calm"),
                  young_female_gentle=("zh-CN-XiaoyiNeural", -8, -4, 0, "gentle"), young_female_lively=("zh-CN-XiaoyiNeural", 4, 2, 0, "cheerful"),
                  young_male=("zh-CN-YunxiNeural", 0, 0, 0, "neutral"), mature_female=("zh-CN-XiaoxiaoNeural", -8, -10, 0, "calm"),
                  mature_male=("zh-CN-YunjianNeural", -6, -6, 0, "calm"), elderly_woman=("zh-CN-XiaoxiaoNeural", -8, -16, -4, "tender"),
                  elderly_man=("zh-CN-YunyangNeural", -16, -14, -4, "calm"), child_girl=("zh-CN-XiaoyiNeural", 4, 14, 0, "cheerful"),
                  child_boy=("zh-CN-YunxiaNeural", 0, 4, 0, "cheerful"), news_anchor=("zh-CN-YunyangNeural", 0, 0, 0, "serious")),
    "zh-TW": dict(narrator_female=("zh-TW-HsiaoChenNeural", -6, -2, 0, "gentle"), narrator_male=("zh-TW-YunJheNeural", -6, -2, 0, "calm"),
                  young_female_gentle=("zh-TW-HsiaoYuNeural", -6, -2, 0, "gentle"), young_female_lively=("zh-TW-HsiaoYuNeural", 6, 3, 0, "cheerful"),
                  young_male=("zh-TW-YunJheNeural", 0, 2, 0, "neutral"), mature_female=("zh-TW-HsiaoChenNeural", -8, -10, 0, "calm"),
                  mature_male=("zh-TW-YunJheNeural", -8, -10, 0, "calm"), elderly_woman=("zh-TW-HsiaoChenNeural", -14, -18, -4, "tender"),
                  elderly_man=("zh-TW-YunJheNeural", -16, -18, -4, "calm"), child_girl=("zh-TW-HsiaoYuNeural", 4, 14, 0, "cheerful"),
                  child_boy=("zh-TW-YunJheNeural", 4, 16, 0, "cheerful"), news_anchor=("zh-TW-YunJheNeural", 0, 0, 0, "serious")),
    "en": dict(narrator_female=("en-US-AvaMultilingualNeural", -4, 0, 0, "gentle"), narrator_male=("en-US-AndrewMultilingualNeural", -4, -2, 0, "calm"),
               young_female_gentle=("en-US-EmmaNeural", -6, -2, 0, "gentle"), young_female_lively=("en-US-EmmaNeural", 6, 3, 0, "cheerful"),
               young_male=("en-US-BrianNeural", 0, 0, 0, "neutral"), mature_female=("en-GB-SoniaNeural", -6, -6, 0, "calm"),
               mature_male=("en-US-ChristopherNeural", -6, -4, 0, "calm"), elderly_woman=("en-GB-LibbyNeural", -14, -16, -4, "tender"),
               elderly_man=("en-GB-ThomasNeural", -16, -14, -4, "calm"), child_girl=("en-GB-MaisieNeural", 0, 4, 0, "cheerful"),
               child_boy=("en-US-AnaNeural", 0, -6, 0, "cheerful"), news_anchor=("en-US-GuyNeural", 0, 0, 0, "serious")),
    "ja": dict(narrator_female=("ja-JP-NanamiNeural", -6, -2, 0, "gentle"), narrator_male=("ja-JP-KeitaNeural", -6, -2, 0, "calm"),
               young_female_gentle=("ja-JP-NanamiNeural", -6, 2, 0, "gentle"), young_female_lively=("ja-JP-NanamiNeural", 6, 5, 0, "cheerful"),
               young_male=("ja-JP-KeitaNeural", 0, 2, 0, "neutral"), mature_female=("ja-JP-NanamiNeural", -8, -10, 0, "calm"),
               mature_male=("ja-JP-KeitaNeural", -8, -10, 0, "calm"), elderly_woman=("ja-JP-NanamiNeural", -14, -18, -4, "tender"),
               elderly_man=("ja-JP-KeitaNeural", -16, -18, -4, "calm"), child_girl=("ja-JP-NanamiNeural", 4, 16, 0, "cheerful"),
               child_boy=("ja-JP-KeitaNeural", 4, 22, 0, "cheerful"), news_anchor=("ja-JP-KeitaNeural", 0, 0, 0, "serious")),
    "es": dict(narrator_female=("es-ES-ElviraNeural", -4, 0, 0, "gentle"), narrator_male=("es-ES-AlvaroNeural", -4, -2, 0, "calm"),
               young_female_gentle=("es-ES-XimenaNeural", -6, -2, 0, "gentle"), young_female_lively=("es-MX-DaliaNeural", 6, 3, 0, "cheerful"),
               young_male=("es-MX-JorgeNeural", 0, 0, 0, "neutral"), mature_female=("es-ES-ElviraNeural", -8, -10, 0, "calm"),
               mature_male=("es-ES-AlvaroNeural", -8, -10, 0, "calm"), elderly_woman=("es-ES-ElviraNeural", -14, -18, -4, "tender"),
               elderly_man=("es-MX-JorgeNeural", -16, -16, -4, "calm"), child_girl=("es-ES-XimenaNeural", 4, 14, 0, "cheerful"),
               child_boy=("es-MX-JorgeNeural", 4, 22, 0, "cheerful"), news_anchor=("es-ES-AlvaroNeural", 0, 0, 0, "serious")),
}
_OA = dict(narrator_female="sage", narrator_male="ash", young_female_gentle="shimmer", young_female_lively="coral", young_male="verse", mature_female="nova",
           mature_male="onyx", elderly_woman="ballad", elderly_man="echo", child_girl="coral", child_boy="fable", news_anchor="alloy")
SAMPLE_TEXT = {"zh-CN": "你好，我是这个角色的声音。今天也辛苦了。", "zh-TW": "你好，我是這個角色的聲音。今天也辛苦了。",
               "en": "Hi, this is my voice. You did well today.", "ja": "こんにちは、このキャラクターの声です。今日もお疲れさま。", "es": "Hola, esta es mi voz. Hoy lo hiciste muy bien."}

def lang_key(lang):
    l = str(lang or "en"); return l if l in _P else ("zh-TW" if l.lower() in ("zh-tw", "zh-hk") else "zh-CN" if l.startswith("zh") else l.split("-")[0] if l.split("-")[0] in _P else "en")

def presets(lang=None):
    """[{id, kind, lang, gender, age, backend, voice, rate, pitch, volume, style, openai_voice}] - ids look like 'zh-CN/elderly_woman'."""
    out = []
    for lg, kinds in _P.items():
        if lang and lg != lang_key(lang): continue
        for k, (v, r, p, vol, st) in kinds.items():
            g, a = KINDS[k]
            out.append(dict(id=f"{lg}/{k}", kind=k, lang=lg, gender=g, age=a, backend="auto", voice=v, rate=r, pitch=p, volume=vol, style=st, openai_voice=_OA[k]))
    return out

def preset(pid):
    p = next((x for x in presets() if x["id"] == pid), None)
    if not p: raise ValueError(f"unknown voice preset {pid}")
    return p

def _int(v, lo, hi, what):
    if isinstance(v, str): v = re.sub(r"(%|hz)$", "", v.strip().lower()) or "0"
    try: v = int(round(float(v)))
    except (TypeError, ValueError): raise ValueError(f"{what} must be a number")
    if not lo <= v <= hi: raise ValueError(f"{what} must be {lo}..{hi}")
    return v

def clean_profile(name, d):
    """Validate one character. Raises ValueError. Never keeps unknown fields (so nothing secret can ride along)."""
    if not isinstance(name, str) or not NAME_RE.match(name.strip()): raise ValueError("character name: 1-40 letters/digits/CJK, space or -")
    d = dict(d or {})
    if d.get("preset"):
        p = preset(d["preset"]); base = {k: p[k] for k in ("voice", "rate", "pitch", "volume", "style", "openai_voice", "gender", "age", "lang")}
        base.update({k: v for k, v in d.items() if v not in (None, "")}); d = base
    out = dict(description=str(d.get("description") or "")[:200], gender=d.get("gender") or "neutral", age=d.get("age") or "adult",
               lang=lang_key(d.get("lang") or "zh-CN"), preset=str(d.get("preset") or ""), backend=d.get("backend") or "auto",
               voice=str(d.get("voice") or ""), openai_voice=str(d.get("openai_voice") or ""), elevenlabs_voice=str(d.get("elevenlabs_voice") or ""),
               rate=_int(d.get("rate", 0), -50, 50, "rate"), pitch=_int(d.get("pitch", 0), -50, 50, "pitch"), volume=_int(d.get("volume", 0), -50, 50, "volume"),
               style=d.get("style") or "neutral", color=str(d.get("color") or ""), minimax_voice=str(d.get("minimax_voice") or ""),
               doubao_voice=str(d.get("doubao_voice") or ""), azure_voice=str(d.get("azure_voice") or ""), ref_image=str(d.get("ref_image") or ""))
    for k in ("minimax_voice", "doubao_voice"):
        if out[k] and not re.fullmatch(r"[A-Za-z0-9_\-]{3,64}", out[k]): raise ValueError(f"{k}: 3-64 letters/digits/_/-")
    if out["azure_voice"] and not re.fullmatch(r"[A-Za-z]{2,3}-[A-Za-z]{2,4}(-[A-Za-z]+)?-[\w:]+", out["azure_voice"]): raise ValueError("azure voice id looks wrong (e.g. zh-CN-XiaoxiaoNeural)")
    if out["ref_image"] and (".." in out["ref_image"] or not re.search(r"\.(png|jpe?g|webp)$", out["ref_image"], re.I)): raise ValueError("ref_image: a .png/.jpg/.webp path inside the data folder")
    if out["gender"] not in GENDERS: raise ValueError(f"gender must be one of {GENDERS}")
    if out["age"] not in AGES: raise ValueError(f"age must be one of {AGES}")
    if out["backend"] not in BACKENDS: raise ValueError(f"backend must be one of {BACKENDS}")
    if out["style"] not in STYLES: raise ValueError(f"style must be one of {list(STYLES)}")
    if out["voice"] and not re.fullmatch(r"[A-Za-z]{2,3}-[A-Za-z]{2,4}(-[A-Za-z]+)?-\w+Neural", out["voice"]): raise ValueError("edge voice id looks wrong (e.g. zh-CN-XiaoxiaoNeural)")
    if out["openai_voice"] and out["openai_voice"] not in OPENAI_VOICES: raise ValueError(f"openai voice must be one of {OPENAI_VOICES}")
    if out["elevenlabs_voice"] and not re.fullmatch(r"[A-Za-z0-9]{8,40}", out["elevenlabs_voice"]): raise ValueError("ElevenLabs voice id: 8-40 letters/digits")
    if out["color"] and not re.fullmatch(r"#[0-9A-Fa-f]{6}", out["color"]): raise ValueError("color must look like #FFE500")
    if not out["voice"]: out["voice"] = TTS.EDGE_VOICES.get(out["lang"], TTS.EDGE_VOICES["en"])
    return out

def signature(p):
    """Identity of a voice (what must stay the same across shots). Emotion/style per line is allowed to vary."""
    key = {k: p.get(k) for k in ("backend", "voice", "openai_voice", "elevenlabs_voice", "rate", "pitch", "volume")}
    key.update({k: p[k] for k in ("minimax_voice", "doubao_voice", "azure_voice") if p.get(k)})
    return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:10]

class Library:
    """voices/characters.yaml (data folder), optionally overlaid by <video folder>/characters.yaml."""
    def __init__(self, path=None, overlay=None):
        self.path = Path(path or LIB_REL); self.overlay = Path(overlay) if overlay else None
    def _read(self, p):
        if not p or not p.is_file(): return {}
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        chars = d.get("characters", d) if isinstance(d, dict) else {}
        return {str(k): clean_profile(str(k), v) for k, v in (chars or {}).items()}
    def own(self): return self._read(self.path)
    def all(self):
        c = self.own(); c.update(self._read(self.overlay)); return c
    def get(self, name):
        c = self.all()
        if name in c: return c[name]
        raise KeyError(name)
    def _write(self, chars):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("# SeatCrew character voice library - one persistent voice per character (no keys here)\n" +
                             yaml.safe_dump(dict(characters=chars), allow_unicode=True, sort_keys=False), encoding="utf-8")
    def set(self, name, **fields):
        """Create or update a character (fields merge over the current profile). Returns the clean profile."""
        chars = self.own(); cur = chars.get(name.strip(), {})
        if fields.get("preset"): cur = {k: v for k, v in cur.items() if k in ("description", "color")}
        p = clean_profile(name.strip(), dict(cur, **{k: v for k, v in fields.items() if v is not None}))
        if not p["color"]: p["color"] = COLORS[len(chars) % len(COLORS)] if name.strip() not in chars else cur.get("color", "")
        chars[name.strip()] = p; self._write(chars); return p
    def delete(self, name):
        chars = self.own()
        if name not in chars: raise ValueError(f"no character {name}")
        del chars[name]; self._write(chars)
    def merge_in(self, chars, overwrite=False):
        """Import shared characters (from a share file). Existing ones are kept unless overwrite."""
        own = self.own(); added = []
        for n, p in (chars or {}).items():
            if n in own and not overwrite: continue
            own[n] = clean_profile(n, p); added.append(n)
        self._write(own); return added
    def ensure(self, name, lang="zh-CN"):
        """Unknown speaker -> narrator preset for the language (only 'narrator' gets an automatic voice)."""
        try: return self.get(name)
        except KeyError:
            if name != "narrator": raise ValueError(f"speaker '{name}' has no voice - add it to the character voice library")
            return clean_profile("narrator", dict(preset=f"{lang_key(lang)}/narrator_female", description="storyteller"))   # not saved

def resolve(profile, emotion=None):
    """Profile + line emotion -> TTS.synth kwargs."""
    st = emotion or profile.get("style") or "neutral"
    if st not in STYLES: raise ValueError(f"emotion '{st}' must be one of {list(STYLES)}")
    r, p, v, instr, stab = STYLES[st]
    rate, pitch, vol = profile["rate"] + r, profile["pitch"] + p, profile["volume"] + v
    return dict(pref=profile.get("backend") or "auto", voice=profile["voice"], openai_voice=profile.get("openai_voice") or None,
                elevenlabs_voice=profile.get("elevenlabs_voice") or None, rate=f"{rate:+d}%", pitch=f"{pitch:+d}Hz", volume=f"{vol:+d}%",
                instructions=instr, stability=stab, style=st, minimax_voice=profile.get("minimax_voice") or None,
                doubao_voice=profile.get("doubao_voice") or None, azure_voice=profile.get("azure_voice") or None,
                base=(profile["rate"], profile["pitch"], profile["volume"]))

# ---- adjustments for CHIEF chat ("make mom sound older") ----
ADJUST = {"older": dict(pitch=-6, rate=-6), "younger": dict(pitch=6, rate=4), "slower": dict(rate=-8), "faster": dict(rate=8),
          "lower": dict(pitch=-5), "higher": dict(pitch=5), "softer": dict(volume=-8), "louder": dict(volume=8)}
def adjusted(profile, how):
    p = dict(profile)
    for k, d in ADJUST[how].items(): p[k] = max(-50, min(50, p[k] + d))
    return p

# ---- rendering lines ----
def _pcm(path, sr=48000):
    tmp = Path(str(path) + ".pcm.wav"); ff.run(["-i", str(path), "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(tmp)])
    with wave.open(str(tmp)) as w: data = w.readframes(w.getnframes())
    tmp.unlink(); return data

def _trim(pcm, sr, keep_lead=0.04, keep_tail=0.12, db=-45):
    """Strip leading/trailing silence. Returns (pcm, seconds cut from the start)."""
    import numpy as np
    a = np.frombuffer(pcm, np.int16); thr = 32768 * 10 ** (db / 20); hop = int(sr * 0.01)
    if a.size < hop * 3: return pcm, 0.0
    env = np.abs(a[: a.size // hop * hop].reshape(-1, hop)).max(1); loud = np.nonzero(env > thr)[0]
    if not loud.size: return pcm, 0.0
    s0 = max(0, loud[0] * hop - int(sr * keep_lead)); s1 = min(a.size, (loud[-1] + 1) * hop + int(sr * keep_tail))
    return a[s0:s1].tobytes(), s0 / sr

def render_lines(lines, out, lib, lang="zh-CN", pref=None, allow_draft=False, gap=0.3):
    """lines: [{speaker, text, emotion?, pause?}] -> one mono wav with all lines, words tagged with speaker,
    and per-line info [{speaker, signature, backend, voice, style}]. Words keep exact edge/ElevenLabs timings."""
    sr = 48000; buf = bytearray(); words = []; info = []; out = Path(out); t = 0.0
    for i, ln in enumerate(lines):
        sp = ln.get("speaker") or "narrator"; prof = lib.ensure(sp, lang); kw = resolve(prof, ln.get("emotion"))
        p, ws, inf = TTS.synth(ln["text"], out.parent / f"{out.stem}_{i:02d}", pref=pref or kw["pref"], voice=kw["voice"], lang=lang, allow_draft=allow_draft,
                               rate=kw["rate"], pitch=kw["pitch"], volume=kw["volume"], instructions=kw["instructions"],
                               openai_voice=kw["openai_voice"], elevenlabs_voice=kw["elevenlabs_voice"], stability=kw["stability"], style=kw["style"],
                               minimax_voice=kw["minimax_voice"], doubao_voice=kw["doubao_voice"], azure_voice=kw["azure_voice"], base=kw["base"])
        if i:
            pause = float(ln.get("pause", gap)); buf += b"\0\0" * int(sr * pause); t += pause
        pcm, cut = _trim(_pcm(p, sr), sr, keep_lead=0.04 if i else 0.0)   # TTS adds ~0.5s of silence around each line
        words += [dict(w=w["w"], start=round(max(0.0, t + w["start"] - cut), 3), end=round(max(0.05, t + w["end"] - cut), 3), speaker=sp) for w in ws]
        buf += pcm; t = len(buf) / 2 / sr
        info.append(dict(speaker=sp, signature=signature(prof), backend=inf["backend"], voice=inf.get("voice"), style=kw["style"], sync=inf["sync"], draft=bool(inf.get("draft"))))
    with wave.open(str(out), "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(bytes(buf))
    return str(out), words, info

def audition(lib_or_profile, out, text=None, lang=None, emotion=None):
    """Short preview mp3/wav of a character or preset (for the UI audition button)."""
    prof = lib_or_profile; lg = lang or prof.get("lang") or "zh-CN"
    p, _, inf = render_lines([dict(speaker="__a", text=text or SAMPLE_TEXT[lang_key(lg)], emotion=emotion)], Path(out).with_suffix(".wav"),
                             _Single(prof), lang=lg)
    return p, inf

class _Single:
    def __init__(self, p): self.p = p
    def ensure(self, name, lang=None): return self.p

# ---- dashboard API ----
FIELDS = ("preset", "description", "gender", "age", "lang", "backend", "voice", "openai_voice", "elevenlabs_voice", "rate", "pitch", "volume", "style", "color",
          "minimax_voice", "doubao_voice", "azure_voice", "ref_image")

def api_state(lang=None):
    import os
    return dict(characters=Library().all(), presets=presets(), styles=list(STYLES), genders=list(GENDERS), ages=list(AGES), backends=list(BACKENDS),
                openai_voices=list(OPENAI_VOICES), lang=lang_key(lang), keys=dict(openai=bool(os.getenv("OPENAI_API_KEY")), elevenlabs=bool(os.getenv("ELEVENLABS_API_KEY")),
                minimax=bool(os.getenv("MINIMAX_API_KEY")), doubao=bool(os.getenv("VOLC_TTS_API_KEY")), azure=bool(os.getenv("AZURE_SPEECH_KEY"))))

def audition_file(lib, name=None, preset_id=None, text=None, emotion=None, lang=None):
    """Cached mp3 preview (voices/auditions/<hash>.mp3) of a character or a preset."""
    prof = clean_profile("x", preset(preset_id)) if preset_id else lib.get(str(name or ""))
    if emotion and emotion not in STYLES: raise ValueError("unknown emotion")
    lg = prof.get("lang") or lang_key(lang); txt = (str(text or "").strip() or SAMPLE_TEXT[lang_key(lg)])[:200]
    h = hashlib.sha1(json.dumps([signature(prof), prof.get("style"), emotion, txt], ensure_ascii=False).encode()).hexdigest()[:16]
    d = lib.path.parent / "auditions"; d.mkdir(parents=True, exist_ok=True); f = d / f"{h}.mp3"
    if not f.is_file():
        wav, _ = audition(prof, d / f"{h}_src.wav", txt, lg, emotion)
        ff.run(["-i", wav, "-c:a", "libmp3lame", "-b:a", "128k", str(f)]); Path(wav).unlink(missing_ok=True)
        for x in d.glob(f"{h}_src_*"): x.unlink(missing_ok=True)
    return f

"""Free local voice engines (optional). edge-tts stays the zero-setup default; these add offline voices and
per-character voice cloning from YOUR OWN or a CONSENTED recording.

Engines are installed on demand into <data folder>/voice_engines/<engine> (so a D:\\ data folder keeps the
multi-GB models off C:). Each runs in its own venv as a subprocess, so SeatCrew itself stays light.

Licences: CosyVoice code+weights Apache-2.0, GPT-SoVITS MIT. F5-TTS (CC-BY-NC weights) and Fish Speech
(CC-BY-NC-SA weights) are listed as NON-COMMERCIAL and are never installed by default.
Never clone a voice without the speaker's permission."""
import json, os, shutil, subprocess, sys, threading, time, urllib.request, uuid
from pathlib import Path

ENGINES = {
    "cosyvoice": dict(label="CosyVoice (Alibaba FunAudioLLM)", license="Apache-2.0", commercial=True, default=True,
                      repo="https://github.com/FunAudioLLM/CosyVoice.git", size_gb=6, python="3.10",
                      models={"sft": "FunAudioLLM/CosyVoice-300M-SFT", "clone": "FunAudioLLM/CosyVoice2-0.5B"},
                      speakers=["中文女", "中文男", "英文女", "英文男", "日语男", "粤语女", "韩语女"],
                      docs="https://github.com/FunAudioLLM/CosyVoice"),
    "gpt_sovits": dict(label="GPT-SoVITS", license="MIT", commercial=True, default=False,
                       repo="https://github.com/RVC-Boss/GPT-SoVITS.git", size_gb=8, python="3.10",
                       docs="https://github.com/RVC-Boss/GPT-SoVITS", api="http://127.0.0.1:9880",
                       run="python api_v2.py -a 127.0.0.1 -p 9880   (inside the GPT-SoVITS folder, after its own install script)"),
    "f5_tts": dict(label="F5-TTS", license="code MIT, weights CC-BY-NC-4.0 (NON-COMMERCIAL)", commercial=False, default=False, installable=False,
                   docs="https://github.com/SWivid/F5-TTS"),
    "fish_speech": dict(label="Fish Speech", license="CC-BY-NC-SA-4.0 weights (NON-COMMERCIAL)", commercial=False, default=False, installable=False,
                        docs="https://github.com/fishaudio/fish-speech"),
}
# CPU-friendly subset of CosyVoice's requirements (no compiler needed; training-only deps dropped).
COSY_REQS = ["numpy==1.26.4", "conformer==0.3.2", "diffusers==0.29.0", "hydra-core==1.3.2", "HyperPyYAML==1.2.3", "inflect==7.3.1",
             "librosa==0.10.2", "lightning==2.2.4", "modelscope==1.20.0", "omegaconf==2.3.0", "onnx==1.16.0", "onnxruntime==1.18.0",
             "openai-whisper==20250625", "protobuf==4.25", "soundfile==0.12.1", "transformers==4.51.3", "x-transformers==2.11.24",
             "wetext==0.0.4", "rich", "matplotlib", "gdown", "wget", "pyarrow", "huggingface_hub", "setuptools<70"]
CONSENT_TEXT = "I am this speaker, or I have the speaker's explicit permission to clone this voice, and I will not use it to deceive anyone."

class VoiceEngineError(RuntimeError): pass
_jobs = {}

def root(data_dir): return Path(data_dir) / "voice_engines"
def _py(d): return d / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

def status(engine, data_dir):
    e = ENGINES[engine]; d = root(data_dir) / engine; s = dict(engine=engine, label=e["label"], license=e["license"], commercial=e["commercial"],
                                                              path=str(d), docs=e["docs"], installable=e.get("installable", True))
    s["installed"] = (d / ".installed").exists()
    if engine == "gpt_sovits":
        s["api"] = os.getenv("SEATCREW_GPTSOVITS_URL", e["api"]); s["run"] = e["run"]
        try: urllib.request.urlopen(s["api"] + "/tts", timeout=1); s["running"] = True
        except urllib.error.HTTPError: s["running"] = True    # 400 without params = server is up
        except Exception: s["running"] = False
    if engine == "cosyvoice": s["speakers"] = e["speakers"]
    return s

def status_all(data_dir): return {k: status(k, data_dir) for k in ENGINES}

def plan(engine, data_dir, device="cpu"):
    """The exact commands install() will run - shown to the user before they click."""
    e = ENGINES[engine]
    if not e.get("installable", True): raise VoiceEngineError(f"{e['label']} weights are {e['license']} - not offered for one-click install")
    d = root(data_dir) / engine; uv = shutil.which("uv"); git = shutil.which("git")
    if not git: raise VoiceEngineError("git is required - install it from https://git-scm.com/downloads")
    steps = [[git, "clone", "--depth", "1", "--recursive", e["repo"], str(d / "src")]]
    if engine != "cosyvoice": return steps                               # GPT-SoVITS: clone + its own installer (guided)
    if uv: steps += [[uv, "venv", "--python", e["python"], str(d / "venv")]]
    else: steps += [[sys.executable, "-m", "venv", str(d / "venv")]]
    pip = [uv, "pip", "install", "--python", str(_py(d))] if uv else [str(_py(d)), "-m", "pip", "install"]
    idx = "https://download.pytorch.org/whl/" + ("cu121" if device == "cuda" else "cpu")
    steps += [pip + ["torch==2.3.1", "torchaudio==2.3.1", "--index-url", idx] + (["--extra-index-url", "https://pypi.org/simple", "--index-strategy", "unsafe-best-match"] if uv else ["--extra-index-url", "https://pypi.org/simple"]) + COSY_REQS]
    for name, repo in e["models"].items():
        steps += [[str(_py(d)), "-c", f"from huggingface_hub import snapshot_download as s; s({repo!r}, local_dir={str(d / 'models' / repo.split('/')[1])!r})"]]
    return steps

def install(engine, data_dir, device="cpu", runner=subprocess.run):
    steps = plan(engine, data_dir, device); d = root(data_dir) / engine; d.mkdir(parents=True, exist_ok=True)
    jid = uuid.uuid4().hex[:10]; job = dict(id=jid, engine=engine, step=0, steps=len(steps), log=[], done=False, ok=None, device=device,
                                            warning=None if device == "cuda" else "Running on CPU: works, but slow. A NVIDIA GPU (6 GB+) is recommended.")
    def go():
        try:
            for i, cmd in enumerate(steps):
                job["step"] = i + 1; job["log"] = (job["log"] + ["$ " + " ".join(Path(cmd[0]).name if j == 0 else c for j, c in enumerate(cmd))[:200]])[-30:]
                if cmd[1:3] == ["clone", "--depth"] and Path(cmd[-1]).exists(): continue
                r = runner(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7200)
                if r.returncode: raise VoiceEngineError((r.stderr or r.stdout or "")[-400:])
            if engine == "cosyvoice": (d / "seatcrew_cosy_run.py").write_text(RUNNER, encoding="utf-8")
            (d / ".installed").write_text(json.dumps(dict(at=time.strftime("%Y-%m-%d %H:%M"), device=device)), encoding="utf-8"); job["ok"] = True
        except Exception as ex: job["ok"] = False; job["log"].append(f"ERROR: {ex}"[:500])
        job["done"] = True
    threading.Thread(target=go, daemon=True).start(); _jobs[jid] = job; return dict(job)

def job(jid):
    if jid not in _jobs: raise VoiceEngineError("unknown install job")
    return dict(_jobs[jid])

# ---------- per-character clone profiles (consent required) ----------
def clones_dir(data_dir): return root(data_dir) / "clones"

def add_clone(data_dir, name, wav_path, transcript, consent, statement=CONSENT_TEXT):
    if consent is not True: raise VoiceEngineError("tick the consent box: only your own voice or a voice you have permission to clone")
    src = Path(wav_path)
    if not src.exists(): raise VoiceEngineError("recording not found")
    if not (transcript or "").strip(): raise VoiceEngineError("type exactly what is said in the recording (needed for cloning)")
    cid = uuid.uuid4().hex[:8]; d = clones_dir(data_dir); d.mkdir(parents=True, exist_ok=True)
    dst = d / f"{cid}{src.suffix.lower() or '.wav'}"; shutil.copyfile(src, dst)
    prof = dict(id=cid, name=str(name)[:60], wav=dst.name, transcript=transcript.strip()[:400],
                consent=dict(given=True, statement=statement, date=time.strftime("%Y-%m-%d")))
    (d / f"{cid}.json").write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding="utf-8"); return prof

def get_clone(data_dir, cid):
    p = clones_dir(data_dir) / f"{Path(str(cid)).name}.json"
    if not p.exists(): raise VoiceEngineError(f"unknown voice clone {cid}")
    prof = json.loads(p.read_text(encoding="utf-8"))
    if not (prof.get("consent") or {}).get("given"): raise VoiceEngineError("this clone has no recorded consent - refusing")
    prof["wav_path"] = str(clones_dir(data_dir) / prof["wav"]); return prof

def list_clones(data_dir):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(clones_dir(data_dir).glob("*.json"))] if clones_dir(data_dir).exists() else []

# ---------- synthesis ----------
def data_dir_default():
    try:
        from ..desktop import data_dir; return data_dir()
    except Exception: return Path(os.getenv("SEATCREW_DATA_DIR") or Path.home() / ".seatcrew")

def cosyvoice(text, out, voice=None, lang="en", data_dir=None, runner=subprocess.run, timeout=1800):
    """voice = built-in speaker name (e.g. 英文男) or 'clone:<id>'. Returns path of a .wav."""
    d = root(data_dir or data_dir_default()) / "cosyvoice"
    if not (d / ".installed").exists(): raise VoiceEngineError("CosyVoice is not installed - Setup > Voice engines > Install")
    req = dict(text=text, out=str(Path(out).with_suffix(".wav")), src=str(d / "src"))
    if voice and str(voice).startswith("clone:"):
        prof = get_clone(data_dir or data_dir_default(), voice[6:])
        req.update(mode="zero_shot", model=str(d / "models" / "CosyVoice2-0.5B"), prompt_wav=prof["wav_path"], prompt_text=prof["transcript"])
    else:
        spk = voice if voice in ENGINES["cosyvoice"]["speakers"] else ("中文女" if lang.startswith("zh") else "日语男" if lang == "ja" else "英文男")
        req.update(mode="sft", model=str(d / "models" / "CosyVoice-300M-SFT"), spk=spk)
    r = runner([str(_py(d)), str(d / "seatcrew_cosy_run.py")], input=json.dumps(req), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode or not Path(req["out"]).exists(): raise VoiceEngineError("CosyVoice failed: " + (r.stderr or r.stdout or "")[-300:])
    return req["out"]

def gpt_sovits(text, out, voice=None, lang="en", data_dir=None, opener=urllib.request.urlopen):
    """Talks to a GPT-SoVITS api_v2 server you run locally. voice = 'clone:<id>' (consented reference)."""
    if not (voice and str(voice).startswith("clone:")): raise VoiceEngineError("GPT-SoVITS needs a consented clone voice (clone:<id>)")
    prof = get_clone(data_dir or data_dir_default(), voice[6:]); base = os.getenv("SEATCREW_GPTSOVITS_URL", ENGINES["gpt_sovits"]["api"])
    tl = {"zh-CN": "zh", "zh-TW": "zh", "ja": "ja", "en": "en", "es": "en"}.get(lang, "en")
    body = dict(text=text, text_lang=tl, ref_audio_path=prof["wav_path"], prompt_text=prof["transcript"], prompt_lang="auto", media_type="wav")
    req = urllib.request.Request(base + "/tts", json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with opener(req, timeout=600) as r: data = r.read()
    except Exception as e: raise VoiceEngineError(f"GPT-SoVITS server not reachable at {base} ({type(e).__name__}) - start it: {ENGINES['gpt_sovits']['run']}")
    p = Path(out).with_suffix(".wav"); p.write_bytes(data); return str(p)

RUNNER = r'''import json, sys, os
req = json.load(sys.stdin)
sys.path[:0] = [req["src"], os.path.join(req["src"], "third_party", "Matcha-TTS")]
try: import pyworld  # noqa: F401  (only used by CosyVoice training code; needs a C++ compiler to build)
except ImportError:
    import types; sys.modules["pyworld"] = types.ModuleType("pyworld")
import torch, torchaudio
from cosyvoice.cli.cosyvoice import AutoModel
m = AutoModel(model_dir=req["model"])
if req["mode"] == "sft": gen = m.inference_sft(req["text"], req["spk"], stream=False)
else: gen = m.inference_zero_shot(req["text"], req["prompt_text"], req["prompt_wav"], stream=False)
wav = torch.cat([o["tts_speech"] for o in gen], dim=1)
torchaudio.save(req["out"], wav, m.sample_rate)
print(json.dumps(dict(ok=True, seconds=wav.shape[1] / m.sample_rate, device="cuda" if torch.cuda.is_available() else "cpu")))
'''

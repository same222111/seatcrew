"""Language-purity check for docs and UI strings.

English docs and the en locale must not contain Chinese/Japanese characters; Chinese docs and the zh-CN / zh-TW locales
must not contain stray English words. Allowed in Chinese text: proper names and product names (ALLOW), code, commands,
paths, URLs, env vars, file names, ALL-CAPS identifiers, {placeholders}, version numbers and units.

    python scripts/lang_purity.py            # report, exit 1 on problems
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HAN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
# English words that may appear in Chinese text: brands, products, models, standard tech terms
ALLOW = set("""SeatCrew TradeCrew CHIEF AI API Key Keys Token OpenAI Anthropic Claude ChatGPT Codex Cursor Gemini Grok xAI DeepSeek Ollama
Google Microsoft Azure Edge Windows macOS Linux Mac AppImage GitHub Releases Python YAML JSON CSV PDF MP4 GIF PNG CLI GPU CPU NVIDIA RAM
VRAM UI URL HTTP HTTPS SSML TTS LLM QC CI FFmpeg ffmpeg ffprobe Noto Sans CJK Heiti YaHei Kling Runway Luma MiniMax Hailuo ElevenLabs
Doubao ByteDance Volcano Engine Speech Replicate FLUX Meshy Tripo CosyVoice SoVITS GPT F5 Fish Apache MIT CC BY NC SA LUFS H.264 dBTP
Montserrat Pro Flash Ray Omni Veo Neural HD edge-tts pip pipx venv USB Esc Alt OK BLOCKED DRAFT REVIEW Runner Demo Douyin YouTube
TikTok Bilibili Qwen Kimi Zhipu GLM Moonshot SiliconFlow OpenRouter Groq Mistral Llama Meta Whisper Lip Sync Wav2Lip LatentSync
SadTalker MuseTalk Hedra Sync Labs zh en ja es ko CN TW Pixel iPhone iPad Android Chrome Safari Firefox Ken Burns Shift Night
Pika Hunyuan Wan Seedance Jimeng Vidu Higgsfield Ideogram Midjourney Stable Diffusion SDXL ComfyUI Fooocus Flux Imagen DALL Sora
LoRA ONNX CUDA ROCm Metal Apple Intel AMD M1 M2 M3 M4 x86 arm64 Docker Homebrew npm Node Git Wi-Fi PowerShell Terminal Bash Zsh
OTS VS Code VSCode Dev Studio env Ctrl px dB jieba Stability auto slow medium fast veryfast ultrafast narrator speaker emotion""".split())
TOKEN = re.compile(r"[A-Za-z][A-Za-z'-]*[A-Za-z]|[A-Za-z]")

def _strip_md(t):
    t = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), t, flags=re.S)   # keep line numbers                  # code blocks
    t = re.sub(r"`[^`\n]*`", " ", t)                               # code spans
    t = re.sub(r"<[^>\n]+>", " ", t)                               # html tags
    t = re.sub(r"\]\([^)]*\)", "]", t)                             # link targets
    t = re.sub(r"https?://\S+", " ", t)
    return t

def _strip_ui(t):
    t = re.sub(r"\{[^{}]*\}", " ", t)                              # {placeholders}
    t = re.sub(r"<[^>]+>", " ", t); t = re.sub(r"https?://\S+", " ", t); t = re.sub(r"`[^`]*`", " ", t)
    return t

def _stray_english(text):
    bad = []
    for w in TOKEN.findall(text):
        if w in ALLOW or w.upper() == w or w.lower() in {a.lower() for a in ALLOW}: continue   # ALL-CAPS ids, names
        if re.search(r"[A-Z].*[A-Z]|\d", w): continue                                          # CamelCase / mixed ids
        bad.append(w)
    return bad

def _scan_line_zh(line):
    t = re.sub(r"\b[\w-]+(?:/[\w.-]+)+", " ", line)                                                            # paths / model ids
    t = re.sub(r"(?<![\w-])--?[\w-]+", " ", t)                                                              # flags
    t = re.sub(r"[\w.-]+\.(?:py|md|yaml|yml|json|txt|mp4|png|exe|dmg|zip|sh|ps1|ttf|otf|wav)\b", " ", t)   # file names
    t = re.sub(r"\b\w+_\w+\b", " ", t)
    t = re.sub(r"[\w.-]*\d[\w.-]*", " ", t)                                                              # versions, model ids
    return _stray_english(t)

def scan_md(path, lang):
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"^\[(?:English|简体中文|繁體中文)\]\([^)\n]+\)(?: · \[[^\]\n]+\]\([^)\n]+\))+ *$", " ", raw, flags=re.M)   # language-switch line
    out = []; text = _strip_md(raw)
    for n, line in enumerate(text.splitlines(), 1):
        if lang == "en":
            if HAN.search(line): out.append((n, "Chinese/Japanese text in an English doc", line.strip()[:120]))
        elif HAN.search(line) or not line.strip():
            bad = _scan_line_zh(line)
            if bad: out.append((n, "English words in a Chinese doc: " + ", ".join(sorted(set(bad))), line.strip()[:120]))
        elif re.search(r"[a-z]{3,} [a-z]{3,} [a-z]{3,}", line) and not line.lstrip().startswith(("|", "#!", "<")):
            out.append((n, "English sentence in a Chinese doc", line.strip()[:120]))
    return out

def _walk(d, pre=""):
    if isinstance(d, dict):
        for k, v in d.items(): yield from _walk(v, f"{pre}.{k}" if pre else k)
    elif isinstance(d, list):
        for i, v in enumerate(d): yield from _walk(v, f"{pre}[{i}]")
    elif isinstance(d, str): yield pre, d

def scan_locale(path, lang):
    out = []; data = json.loads(path.read_text(encoding="utf-8"))
    for key, val in _walk(data):
        t = _strip_ui(val)
        if lang == "en" or lang == "es":
            if HAN.search(t): out.append((key, "CJK text in the " + lang + " locale", val[:120]))
        elif lang.startswith("zh"):
            bad = _scan_line_zh(t)
            if bad: out.append((key, "English words in the " + lang + " locale: " + ", ".join(sorted(set(bad))), val[:120]))
    return out

def targets(root=ROOT):
    md = [(p, "en") for p in [*root.glob("*.md"), *root.glob("docs/*.md"), *root.glob("examples/*/README.md")]
          if not re.search(r"\.zh(-CN|-TW)?\.md$", p.name) and p.name not in ("AGENTS.md",)]
    md += [(p, "zh") for p in [*root.glob("*.zh*.md"), *root.glob("docs/*.zh*.md"), *root.glob("examples/*/README.zh*.md")]]
    loc = [(p, p.stem) for p in [*root.glob("seatcrew/locales/*.json"), *root.glob("examples/*/locales/*.json")] if p.stem in ("en", "es", "zh-CN", "zh-TW")]
    return md, loc


UI_LANGS = ("en", "zh-CN", "zh-TW", "ja", "es")
SUBJECTS = {"content_review": ["post"]}          # sample-data subjects shown in the UI

def _choices(ex):
    """Option values a workflow shows in <select>s: CHOICES in workflow.py, options of submit fields in workflow.yaml."""
    vals = set(); py = ex / "workflow.py"; ym = ex / "workflow.yaml"
    if py.exists():
        import runpy
        if str(ex.parents[1]) not in sys.path: sys.path.insert(0, str(ex.parents[1]))
        try: vals |= {str(v) for l in (runpy.run_path(str(py)).get("CHOICES") or {}).values() for v in l}
        except Exception as e: return None, f"cannot load {py.name}: {e}"
    if ex.name == "short_video":                       # Character Studio voice backends use the same opt_ keys
        try:
            from seatcrew.video.voices import BACKENDS; vals |= set(BACKENDS)
        except Exception as e: return None, f"cannot load voice backends: {e}"
    if ym.exists():
        import yaml
        d = yaml.safe_load(ym.read_text(encoding="utf-8")) or {}
        for f in d.get("submit") or []:
            if isinstance(f, dict): vals |= {str(o) for o in f.get("options") or []}
    return vals, None

def _settings(ex):
    """Setting names the Settings tab labels (the workflow's real default config), or [] for a bare test folder."""
    if not ((ex / "workflow.py").exists() or (ex / "workflow.yaml").exists()) or ex.parents[1] != ROOT: return [], None
    import tempfile
    if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
    try:
        from seatcrew import loader
        with tempfile.TemporaryDirectory() as d:
            wf = loader.build(ex.name, str(Path(d) / "config.yaml"), d); return sorted(wf.cfg.data.get("settings") or {}), None
    except Exception as e: return None, f"cannot build {ex.name}: {type(e).__name__}: {e}"

def scan_options(root=ROOT):
    """Every option value, sample subject and setting must have opt_<v> / subj_<v> / set_<k> in every UI language (workflow or app locale)."""
    out = []; app = {l: (json.loads(f.read_text(encoding="utf-8")) if (f := root / "seatcrew/locales" / f"{l}.json").exists() else {}) for l in UI_LANGS}
    if not (root / "examples").is_dir(): return out
    for ex in sorted(p for p in (root / "examples").iterdir() if (p / "locales").is_dir()):
        vals, err = _choices(ex)
        if err: out.append((ex.relative_to(root).as_posix(), "-", err, "")); continue
        keys, err = _settings(ex)
        if err: out.append((ex.relative_to(root).as_posix(), "-", err, "")); continue
        need = [f"opt_{v}" for v in sorted(vals)] + [f"subj_{v}" for v in SUBJECTS.get(ex.name, [])] + [f"set_{k}" for k in keys]
        for l in UI_LANGS:
            lp = ex / "locales" / f"{l}.json"; loc = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {}
            if not lp.exists(): out.append((lp.relative_to(root).as_posix(), "-", "missing locale file", "")); continue
            miss = [k for k in need if not (loc.get(k) or app[l].get(k))]
            if miss: out.append((lp.relative_to(root).as_posix(), "-", "untranslated option values: " + ", ".join(miss), ""))
    return out

def scan(root=ROOT):
    md, loc = targets(root); problems = []
    for p, l in md: problems += [(p.relative_to(root).as_posix(), *x) for x in scan_md(p, l)]
    for p, l in loc: problems += [(p.relative_to(root).as_posix(), *x) for x in scan_locale(p, l)]
    problems += scan_options(root)
    return problems

if __name__ == "__main__":
    probs = scan()
    for f, where, why, text in probs: print(f"{f}:{where}: {why}\n    {text}")
    print(f"{len(probs)} problem(s)"); sys.exit(1 if probs else 0)

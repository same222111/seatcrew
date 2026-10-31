"""First-run detection: hardware, installed AI CLIs, local models and keys -> one recommended setup.
Only booleans / versions / sizes are collected. Nothing leaves the machine; no key or login token is ever read."""
import json, os, platform, shutil, subprocess, sys, urllib.request
from pathlib import Path
from . import cli_ai, llm

def _run(args, timeout=6):
    try: return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception: return ""

def ram_gb():
    try:
        if sys.platform.startswith("linux"):
            for l in open("/proc/meminfo"):
                if l.startswith("MemTotal"): return round(int(l.split()[1]) / 1048576, 1)
        if sys.platform == "darwin": return round(int(_run(["sysctl", "-n", "hw.memsize"]) or 0) / 2**30, 1)
        if os.name == "nt":
            import ctypes
            class M(ctypes.Structure): _fields_ = [("l", ctypes.c_ulong), ("p", ctypes.c_ulong), ("t", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong)] + [(f"x{i}", ctypes.c_ulonglong) for i in range(5)]
            m = M(); m.l = ctypes.sizeof(M); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); return round(m.t / 2**30, 1)
    except Exception: pass
    return None

def gpu():
    """NVIDIA via nvidia-smi (name + VRAM), Apple Silicon via platform. None = CPU only."""
    smi = shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe" if os.name == "nt" and Path(r"C:\Windows\System32\nvidia-smi.exe").exists() else None)
    if smi:
        out = _run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        rows = [r.split(",") for r in out.strip().splitlines() if "," in r]
        if rows:
            name, mem = rows[0][0].strip(), rows[0][1].strip()
            return dict(vendor="nvidia", name=name, vram_gb=round(int(mem) / 1024, 1) if mem.isdigit() else None, cuda=True)
    if sys.platform == "darwin" and platform.machine() == "arm64":
        return dict(vendor="apple", name="Apple Silicon", vram_gb=None, cuda=False, mps=True)
    return None

def ollama(base="http://localhost:11434"):
    path = shutil.which("ollama"); models, running = [], False
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=1.5) as r:
            models = [m["name"] for m in json.loads(r.read()).get("models", [])]; running = True
    except Exception: pass
    return dict(installed=bool(path or running), running=running, models=models, version=(_run([path, "--version"]).strip()[:60] if path else None),
                install="https://ollama.com/download", pull="ollama pull qwen2.5:3b")

def detect(data_dir=None):
    d = Path(data_dir or Path.home()); free = None
    try: free = round(shutil.disk_usage(d if d.exists() else d.anchor or "/").free / 2**30, 1)
    except Exception: pass
    keys = {n: v for n, v in llm.key_status().items() if llm.PROVIDERS[n]["key_env"] and n != "custom"}
    try: import edge_tts; edge = True  # noqa: F401
    except ImportError: edge = False
    from .video import localvoice
    return dict(os=dict(system=platform.system(), release=platform.release(), machine=platform.machine(), python=platform.python_version()),
                cpu_count=os.cpu_count(), ram_gb=ram_gb(), disk_free_gb=free, data_dir=str(d), gpu=gpu(),
                cli=cli_ai.all_status(), ollama=ollama(), keys=keys, node=bool(shutil.which("npm")), edge_tts=edge,
                voice_engines=localvoice.status_all(d))

def recommend(det):
    """Pick a chat backend that works right now (never needs a key), a voice, and an optional local clone engine."""
    why = []
    key = next((p for p, ok in det["keys"].items() if ok), None)
    if key: chat, why = key, [f"API key found for {key}"]
    elif det["cli"]["codex"]["logged_in"]: chat, why = "codex_cli", ["signed in to Codex CLI (your ChatGPT plan)"]
    elif det["cli"]["claude"]["logged_in"]: chat, why = "claude_cli", ["signed in to Claude Code (your Claude plan)"]
    elif det["ollama"]["running"] and det["ollama"]["models"]: chat, why = "ollama", [f"Ollama running with {det['ollama']['models'][0]}"]
    else: chat, why = None, ["no account or local model yet - starting in free demo mode; log in with ChatGPT or Claude any time"]
    g = det.get("gpu") or {}; ram = det.get("ram_gb") or 0
    if g.get("cuda") and (g.get("vram_gb") or 0) >= 6: clone, device, warn = "cosyvoice", "cuda", None
    elif g.get("mps"): clone, device, warn = "cosyvoice", "cpu", "Apple GPU is not used by CosyVoice yet - CPU is slow (about 5-20x realtime)"
    else: clone, device, warn = ("cosyvoice" if ram >= 8 else None), "cpu", "No NVIDIA GPU found - local voice cloning will run on CPU and be slow; edge-tts stays the default"
    if (det.get("disk_free_gb") or 99) < 8: clone, warn = None, "Less than 8 GB free in the data folder - local voice engine not recommended"
    return dict(chat_provider=chat, ai_mode=("cli" if chat in ("codex_cli", "claude_cli") else "ollama" if chat == "ollama" else "key" if chat else "demo"),
                voice="edge" if det.get("edge_tts") else "draft", clone_engine=clone, clone_device=device, warning=warn, why=why)

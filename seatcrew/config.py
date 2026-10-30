"""Config = workflow defaults + <config>.yaml (user settings, edited from the Settings UI) + .env (API keys only).
API keys are never written to the YAML file."""
import copy, os, threading
from pathlib import Path
import yaml
from .llm import PROVIDERS

LANGUAGES = {"en": "English", "zh-CN": "简体中文", "zh-TW": "繁體中文", "ja": "日本語", "es": "Español"}
LLM_LIMITS = {"timeout_sec": 20, "max_calls_per_hour": 60, "max_daily_usd": 0.5, "cost_per_call_usd": 0.002}
_lock = threading.Lock()

def merge(base, over):
    """Deep merge `over` onto a copy of `base`."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out

def load_env(path=".env"):
    """Load KEY=value lines into os.environ (existing environment wins)."""
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def base_defaults(seats, prompts=None, settings=None):
    """Standard config skeleton for a workflow with these seat names."""
    prompts = prompts or {}
    return {"language": "en", "run_interval_sec": 300, "auto_run": True,
            "providers": {k: {"model": v["model"], "base_url": v["base_url"]} for k, v in PROVIDERS.items()},
            "llm_limits": dict(LLM_LIMITS),
            "seats": {s: {"provider": "rules", "model": "", "prompt": prompts.get(s, f"You are the {s.upper()} seat.")} for s in seats},
            "settings": copy.deepcopy(settings or {})}

class Config:
    """A YAML-backed settings dict. update() deep-merges a partial patch, validates and saves atomically."""
    def __init__(self, path, defaults, validate=None):
        self.path = Path(path); self.defaults = defaults; self._validate = validate; self.data = self.load()
    def load(self):
        user = yaml.safe_load(self.path.read_text()) if self.path.exists() else {}
        return merge(self.defaults, user or {})
    def save(self):
        with _lock:
            tmp = self.path.with_suffix(".tmp"); tmp.write_text(yaml.safe_dump(self.data, sort_keys=False, allow_unicode=True)); os.replace(tmp, self.path)
    def update(self, patch):
        bad = [k for k in (patch or {}) if k not in self.defaults]
        if bad: raise ValueError(f"unknown settings: {bad}")
        new = merge(self.data, patch); self.validate(new); self.data = new; self.save(); return self.data
    def validate(self, c):
        if c.get("language") not in LANGUAGES: raise ValueError(f"unknown language {c.get('language')}")
        for s, v in c["seats"].items():
            if s not in self.defaults["seats"]: raise ValueError(f"unknown seat {s}")
            if v["provider"] not in ["rules", *PROVIDERS]: raise ValueError(f"unknown provider {v['provider']} for seat {s}")
        if float(c.get("run_interval_sec", 1)) <= 0: raise ValueError("run_interval_sec must be > 0")
        if self._validate: self._validate(c)
    def __getitem__(self, k): return self.data[k]

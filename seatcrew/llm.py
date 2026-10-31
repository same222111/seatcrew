"""Multi-provider LLM layer (stdlib HTTP only): OpenAI, Anthropic, Gemini, xAI, DeepSeek, any OpenAI-compatible
endpoint (OpenRouter, Groq, LM Studio, vLLM...) and local Ollama. Keys come from environment variables only and are
never logged, stored or returned.

The one function seats use is ask_role(seat, prompt, labels, cfg): it asks the AI assigned to that seat for a JSON
{"label", "reason"} restricted to `labels`. Anything that goes wrong (no key, timeout, bad JSON, budget) returns an
abstaining result so the seat's rules stay in control."""
import json, os, re, threading, time, urllib.error, urllib.request

PROVIDERS = {  # kind, default base_url, default model, env var for key. Add an OpenAI-compatible provider = one line.
    "openai":    dict(kind="openai",    base_url="https://api.openai.com/v1", model="gpt-4o-mini", key_env="OPENAI_API_KEY"),
    "anthropic": dict(kind="anthropic", base_url="https://api.anthropic.com/v1", model="claude-3-5-haiku-latest", key_env="ANTHROPIC_API_KEY"),
    "gemini":    dict(kind="gemini",    base_url="https://generativelanguage.googleapis.com/v1beta", model="gemini-2.0-flash", key_env="GEMINI_API_KEY"),
    "xai":       dict(kind="openai",    base_url="https://api.x.ai/v1", model="grok-3-mini", key_env="XAI_API_KEY"),
    "deepseek":  dict(kind="openai",    base_url="https://api.deepseek.com/v1", model="deepseek-chat", key_env="DEEPSEEK_API_KEY"),
    "custom":    dict(kind="openai",    base_url="http://localhost:1234/v1", model="local-model", key_env="CUSTOM_API_KEY"),
    "ollama":    dict(kind="ollama",    base_url="http://localhost:11434", model="llama3.2", key_env=""),
    # Your own ChatGPT / Claude subscription via the vendors' official CLIs (no API key; SeatCrew never sees a token).
    "codex_cli":  dict(kind="cli", base_url="", model="", key_env="", tool="codex", label="ChatGPT (Codex CLI login)"),
    "claude_cli": dict(kind="cli", base_url="", model="", key_env="", tool="claude", label="Claude (Claude Code login)"),
}

class LLMError(Exception): pass

def _post(url, headers, body, timeout):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise LLMError(f"HTTP {e.code}: {_scrub(detail)}") from None
    except urllib.error.URLError as e:
        raise LLMError(f"connection failed: {e.reason}") from None

def _scrub(s):
    for p in PROVIDERS.values():
        k = os.getenv(p["key_env"]) if p["key_env"] else None
        if k: s = s.replace(k, "***")
    return re.sub(r"(sk-|xai-|AIza)[A-Za-z0-9_\-]{8,}", r"\1***", s)

def resolve(name, cfg):
    if name not in PROVIDERS: raise LLMError(f"unknown provider '{name}'")
    base = dict(PROVIDERS[name]); base.update({k: v for k, v in (cfg.get("providers", {}).get(name) or {}).items() if v})
    return base

def chat(name, system, user, cfg, model=None, max_tokens=200, timeout=None):
    """Return (text, model). Raises LLMError with a readable message on any failure."""
    p = resolve(name, cfg); model = model or p["model"]; base = p["base_url"].rstrip("/")
    timeout = timeout or cfg.get("llm_limits", {}).get("timeout_sec", 20)
    key = os.getenv(p["key_env"]) if p["key_env"] else None
    if p["key_env"] and not key and name != "custom":
        raise LLMError(f"no API key: set {p['key_env']} in .env or the environment")
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        if p["kind"] == "openai":
            h = {"Authorization": f"Bearer {key}"} if key else {}
            r = _post(f"{base}/chat/completions", h, dict(model=model, temperature=0, max_tokens=max_tokens, messages=msgs), timeout)
            return r["choices"][0]["message"]["content"] or "", model
        if p["kind"] == "anthropic":
            r = _post(f"{base}/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"},
                      dict(model=model, max_tokens=max_tokens, system=system, messages=msgs[1:]), timeout)
            return "".join(b.get("text", "") for b in r["content"]), model
        if p["kind"] == "gemini":
            r = _post(f"{base}/models/{model}:generateContent", {"x-goog-api-key": key},
                      dict(systemInstruction={"parts": [{"text": system}]}, contents=[{"role": "user", "parts": [{"text": user}]}],
                           generationConfig={"temperature": 0, "maxOutputTokens": max_tokens}), timeout)
            return r["candidates"][0]["content"]["parts"][0]["text"], model
        if p["kind"] == "cli":
            from . import cli_ai
            try: return cli_ai.ask(p["tool"], system, user, model=model or None, timeout=max(timeout, 90)), model or p["tool"]
            except cli_ai.CLIError as e: raise LLMError(str(e)) from None
        if p["kind"] == "ollama":
            model = ollama_model(base, model)
            r = _post(f"{base}/api/chat", {}, dict(model=model, stream=False, messages=msgs, options={"temperature": 0, "num_predict": max_tokens}),
                      max(timeout, 120))                            # local CPU models are slow - give them time
            return r["message"]["content"], model
    except LLMError: raise
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"unexpected response shape ({type(e).__name__})") from None
    except Exception as e:
        raise LLMError(_scrub(f"{type(e).__name__}: {e}")) from None
    raise LLMError(f"unsupported kind {p['kind']}")

_OL = {}
def ollama_model(base, model):
    """Use the configured model if Ollama has it; if it is the untouched default and missing, use the first installed model."""
    if model != PROVIDERS["ollama"]["model"]: return model
    if base not in _OL or time.time() - _OL[base][0] > 60:
        try:
            with urllib.request.urlopen(base + "/api/tags", timeout=2) as r: names = [m["name"] for m in json.loads(r.read()).get("models", [])]
        except Exception: names = []
        _OL[base] = (time.time(), names)
    names = _OL[base][1]
    if not names or any(n == model or n.split(":")[0] == model for n in names): return model
    return names[0]

def test_connection(name, cfg, model=None):
    """Real minimal call. Returns dict(ok, provider, model, latency_ms, reply|error)."""
    t = time.time()
    try:
        txt, m = chat(name, "You are a connectivity check.", "Reply with the single word: pong", cfg, model=model, max_tokens=10)
        return dict(ok=True, provider=name, model=m, latency_ms=int((time.time() - t) * 1000), reply=txt.strip()[:60])
    except LLMError as e:
        return dict(ok=False, provider=name, model=model or resolve(name, cfg)["model"] if name in PROVIDERS else model,
                    latency_ms=int((time.time() - t) * 1000), error=str(e))

class Budget:
    def __init__(self): self.lock = threading.Lock(); self.calls = []; self.day = ""; self.usd = 0.0
    def take(self, lim):
        with self.lock:
            t = time.time(); d = time.strftime("%Y-%m-%d")
            if d != self.day: self.day, self.usd = d, 0.0
            self.calls = [c for c in self.calls if t - c < 3600]
            if len(self.calls) >= lim["max_calls_per_hour"]: return "hourly call limit reached"
            if self.usd + lim["cost_per_call_usd"] > lim["max_daily_usd"]: return "daily cost limit reached"
            self.calls.append(t); self.usd += lim["cost_per_call_usd"]; return None
BUDGET = Budget()

def ask_role(role, user, labels, cfg):  # role = seat name
    """Ask the provider assigned to `role` for a JSON {label, reason}. Returns None when the role is rules-only,
    or dict(label, reason, provider, model, ok). Failures abstain (ok=False) so rules always stay in control."""
    rc = dict(cfg["seats"][role])
    if rc["provider"] == "rules": return None
    rc["model"] = rc.get("model") or resolve(rc["provider"], cfg)["model"]
    why = BUDGET.take(cfg["llm_limits"])
    if why: return dict(ok=False, label="abstain", reason=why, provider=rc["provider"], model=rc.get("model") or "")
    system = rc["prompt"] + f'\nReply ONLY with JSON: {{"label": one of {list(labels)}, "reason": "<one short sentence>"}}'
    try:
        txt, model = chat(rc["provider"], system, user, cfg, model=rc.get("model") or None)
        m = re.search(r"\{.*\}", txt, re.S)
        try: j = json.loads(m.group(0)) if m else {}
        except ValueError: j = {}                                     # small/local models often emit almost-JSON
        if not isinstance(j, dict): j = {}
        if not j:
            lm = re.search(r'"?label"?\s*:\s*"?(\w+)', txt); rm = re.search(r'"?reason"?\s*:\s*"([^"]*)', txt)
            j = dict(label=lm.group(1) if lm else "", reason=rm.group(1) if rm else "")
        lab = str(j.get("label", "")).lower()
        if lab not in labels: return dict(ok=False, label="abstain", reason=f"unparseable: {txt[:80]}", provider=rc["provider"], model=model)
        return dict(ok=True, label=lab, reason=str(j.get("reason", ""))[:200], provider=rc["provider"], model=model)
    except LLMError as e:
        return dict(ok=False, label="abstain", reason=str(e)[:160], provider=rc["provider"], model=rc.get("model") or "")

def write(role, user, cfg, max_tokens=600):
    """Free-text generation for producer seats (e.g. a drafter). Returns (text, provider/model) or None (rules-only / failure)."""
    rc = dict(cfg["seats"][role])
    if rc["provider"] == "rules" or BUDGET.take(cfg["llm_limits"]): return None
    try:
        txt, model = chat(rc["provider"], rc["prompt"], user, cfg, model=rc.get("model") or None, max_tokens=max_tokens)
        return (txt.strip(), f"{rc['provider']}/{model}") if txt.strip() else None
    except LLMError: return None

def key_status():
    """Which provider keys are present (booleans only - keys are never returned)."""
    out = {n: (True if not p["key_env"] else bool(os.getenv(p["key_env"]))) for n, p in PROVIDERS.items()}
    from . import cli_ai
    for n, p in PROVIDERS.items():
        if p["kind"] == "cli":
            st = cli_ai.status(p["tool"]); out[n] = bool(st["installed"] and st["logged_in"])
    return out

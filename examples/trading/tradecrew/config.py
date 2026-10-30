"""Configuration: defaults + config.yaml (user settings) + .env (API keys, never written to config.yaml)."""
import copy, os, threading
from pathlib import Path
import yaml

# The eight seats (+ REVIEW). Each seat owns exactly one job; see AGENTS.md for the architecture map.
SEATS = ["chief", "quant", "stocks", "scan", "judge", "risk", "size", "fills", "review"]
ROLES = SEATS  # backwards-compatible alias
LANGUAGES = {"en": "English", "zh-CN": "简体中文", "zh-TW": "繁體中文", "ja": "日本語", "es": "Español"}

DEFAULT_PROMPTS = {
    "chief": "You are CHIEF, the commander of a paper-trading crew. Given the cycle plan (session, risk dial, number of orders), answer proceed or hold.",
    "quant": "You are QUANT, who sets the overall risk dial. Given market regime stats, choose normal, cautious or defensive.",
    "stocks": "You are STOCKS, the universe and information desk. Classify the near-term (1-5 day) impact of these headlines on the stock.",
    "scan": "You are SCAN, the research seat. Given technical stats for a ticker (or a strategy parameter grid in the lab), pick the best idea.",
    "judge": "You are JUDGE. An idea is not a trigger. Evaluate this trade idea and its evidence; reject weak or contradicted ideas, otherwise approve. (In the lab you judge train vs out-of-sample robustness.)",
    "risk": "You are RISK, a strict risk officer for a small paper account. You may only VETO an entry the rules approved. Veto only for concrete reasons (imminent binary event, severe negative news, extreme gap risk). Otherwise approve.",
    "size": "You are SIZE. Given the rule-based position size, answer keep or halve.",
    "fills": "You are FILLS, the order desk. Given the session and order, answer now or wait.",
    "review": "You are REVIEW, the post-trade replay seat. Given intended vs actual fill, answer ok or flag.",
}
LEGACY_ROLE_MAP = {"scanner": "scan", "news": "stocks", "risk": "risk", "sizer": "size", "executor": "fills", "logger": "review", "proposer": "scan", "validator": "judge"}

from seatcrew.llm import PROVIDERS, key_status  # the multi-provider LLM layer lives in the framework
from seatcrew.config import merge as _merge, load_env  # noqa: F401

DEFAULTS = {
    "setup_complete": False,
    "capital": 200.0,
    "watchlist": ["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "AMD", "TSLA", "UBER", "FCX", "SOFI", "PFE"],
    "scan_interval_sec": 300,
    "providers": {k: {"model": v["model"], "base_url": v["base_url"]} for k, v in PROVIDERS.items()},
    "language": "en",
    "seats": {r: {"provider": "rules", "model": "", "prompt": DEFAULT_PROMPTS[r]} for r in SEATS},
    "risk_dial": "auto",  # auto (QUANT decides) | normal | cautious | defensive
    "llm_limits": {"timeout_sec": 20, "max_calls_per_hour": 60, "max_daily_usd": 0.5, "cost_per_call_usd": 0.002},
    "strategies": {
        "short_term_team": {"enabled": True, "risk_per_trade": 0.01, "max_positions": 3, "atr_mult": 3.0, "min_day_change": 0.005},
        "vol_managed_qqq": {"enabled": True, "symbol": "QQQ", "cash_symbol": "BIL", "target_vol": 0.20, "lookback": 20, "max_weight": 1.0},
        "trend_rsi2": {"enabled": True, "symbol": "QQQ", "sma": 150, "rsi_entry": 5},
        "momentum_swing": {"enabled": True, "take_profit": 0.06, "stop_loss": 0.035, "trail": 0.04, "max_hold": 10, "max_positions": 2, "min_5d_gain": 0.03},
        "rotation": {"enabled": True, "universe": ["NVDA", "UBER", "FCX", "SOFI", "PFE"], "trail": 0.06, "ma_trend": 20, "ma_exit": 10, "two_slot_equity": 300.0},
    },
    "risk": {"daily_loss_cap": 6.0, "max_orders_per_day": 6, "kill_switch": False},
    "data": {
        "price_source": "yfinance",  # yfinance | alpaca | polygon | demo
        "sources": {
            "yfinance": {"enabled": True},
            "alpaca": {"enabled": False, "key_env": "ALPACA_API_KEY", "secret_env": "ALPACA_API_SECRET"},
            "polygon": {"enabled": False, "key_env": "POLYGON_API_KEY"},
            "demo": {"enabled": True},
        },
        "news": [
            {"name": "Yahoo Finance", "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US", "enabled": True},
            {"name": "Google News", "url": "https://news.google.com/rss/search?q={symbol}+stock+when:2d&hl=en-US&gl=US&ceid=US:en", "enabled": True},
        ],
        "earnings_calendar": True,
    },
    "broker": {"mode": "paper", "live_adapter": None},
    "display": {"theme": "dark", "font_size": 13, "density": "normal", "animations": True, "simple": True},
}

_lock = threading.Lock()



class Config:
    defaults = DEFAULTS
    def __init__(self, path="config.yaml"):
        self.path = Path(path); self.data = self.load()

    def validate(self, c): validate(c)

    def load(self):
        user = yaml.safe_load(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        user = migrate(user or {})
        return _merge(DEFAULTS, user or {})

    def save(self):
        with _lock:
            tmp = self.path.with_suffix(".tmp"); tmp.write_text(yaml.safe_dump(self.data, sort_keys=False, allow_unicode=True), encoding="utf-8")
            os.replace(tmp, self.path)

    def update(self, patch):
        """Deep-merge a partial dict from the UI/CLI, validate, persist."""
        patch = migrate(dict(patch or {}))
        bad = [k for k in patch if k not in DEFAULTS]
        if bad: raise ValueError(f"unknown settings: {bad}")
        new = _merge(self.data, patch); validate(new); self.data = new; self.save(); return self.data

    def __getitem__(self, k): return self.data[k]

def validate(c):
    if float(c["capital"]) <= 0: raise ValueError("capital must be > 0")
    if not c["watchlist"] or not all(isinstance(s, str) and s.strip() for s in c["watchlist"]): raise ValueError("watchlist must be non-empty")
    c["watchlist"] = [s.strip().upper() for s in c["watchlist"]]
    for r, v in c["seats"].items():
        if r not in SEATS: raise ValueError(f"unknown seat {r}")
        if v["provider"] not in ["rules", *PROVIDERS]: raise ValueError(f"unknown provider {v['provider']} for seat {r}")
    if c["language"] not in LANGUAGES: raise ValueError(f"unknown language {c['language']}")
    if c["risk_dial"] not in ("auto", "normal", "cautious", "defensive"): raise ValueError("risk_dial must be auto/normal/cautious/defensive")
    if c["data"]["price_source"] not in c["data"]["sources"]: raise ValueError("unknown price source")
    if c["broker"]["mode"] != "paper": raise ValueError("only paper mode is supported")
    from seatcrew.profiles import validate_display; validate_display(c["display"])

def migrate(d):
    """Map the old 'roles' layout (scanner/news/sizer/...) onto seats so older config files keep working."""
    if "roles" in d:
        seats = d.setdefault("seats", {})
        for old, v in (d.pop("roles") or {}).items():
            seats.setdefault(LEGACY_ROLE_MAP.get(old, old), v)
    return d


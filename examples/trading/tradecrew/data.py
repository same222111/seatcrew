"""Pluggable information sources. Price sources return {symbol: DataFrame[Open,High,Low,Close,Volume]} (daily, adjusted).
  yfinance (default, free) | alpaca (ALPACA_API_KEY/SECRET) | polygon (POLYGON_API_KEY) | demo (offline synthetic data)
News sources: any list of RSS URLs with a {symbol} placeholder, each enabled/disabled in Settings."""
import concurrent.futures as cf, datetime as dt, hashlib, json, os, urllib.parse, urllib.request, warnings
import xml.etree.ElementTree as ET
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
_POOL = cf.ThreadPoolExecutor(4)

def with_timeout(fn, *a, timeout=45, **kw):
    """Run fn in a worker thread; a hung socket can never freeze an agent. Returns (ok, value_or_error)."""
    f = _POOL.submit(fn, *a, **kw)
    try: return True, f.result(timeout=timeout)
    except cf.TimeoutError: return False, f"timeout > {timeout}s"
    except Exception as e: return False, f"{type(e).__name__}: {str(e)[:200]}"

def _get_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "tradecrew/0.1", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read())

def yfinance_daily(symbols, days):
    import yfinance as yf
    warnings.simplefilter("ignore")
    d = yf.download(symbols, period=f"{max(days, 30)}d", interval="1d", auto_adjust=True, progress=False,
                    group_by="ticker", threads=False, timeout=15)
    out = {}
    for s in symbols:
        try:
            df = (d[s] if isinstance(d.columns, pd.MultiIndex) else d)[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(df): df.index = pd.to_datetime(df.index).tz_localize(None); out[s] = df
        except KeyError: pass
    return out

def alpaca_daily(symbols, days):
    k, s = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_API_SECRET")
    if not (k and s): raise RuntimeError("set ALPACA_API_KEY and ALPACA_API_SECRET")
    start = (dt.date.today() - dt.timedelta(days=int(days * 1.5) + 5)).isoformat(); out = {}
    for sym in symbols:
        q = urllib.parse.urlencode(dict(timeframe="1Day", start=start, adjustment="all", limit=10000, feed="iex"))
        j = _get_json(f"https://data.alpaca.markets/v2/stocks/{sym}/bars?{q}", {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s})
        bars = j.get("bars") or []
        if bars:
            df = pd.DataFrame(bars); df.index = pd.to_datetime(df.t).dt.tz_localize(None).dt.normalize()
            out[sym] = df.rename(columns=dict(o="Open", h="High", l="Low", c="Close", v="Volume"))[["Open", "High", "Low", "Close", "Volume"]]
    return out

def polygon_daily(symbols, days):
    k = os.getenv("POLYGON_API_KEY")
    if not k: raise RuntimeError("set POLYGON_API_KEY")
    end = dt.date.today(); start = end - dt.timedelta(days=int(days * 1.5) + 5); out = {}
    for sym in symbols:
        j = _get_json(f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/day/{start}/{end}?adjusted=true&limit=50000&apiKey={k}")
        res = j.get("results") or []
        if res:
            df = pd.DataFrame(res); df.index = pd.to_datetime(df.t, unit="ms").dt.normalize()
            out[sym] = df.rename(columns=dict(o="Open", h="High", l="Low", c="Close", v="Volume"))[["Open", "High", "Low", "Close", "Volume"]]
    return out

def demo_daily(symbols, days):
    """Deterministic synthetic prices (per-symbol seed). For offline demos and tests - NOT real market data."""
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days); out = {}
    for s in symbols:
        rng = np.random.default_rng(int(hashlib.md5(s.encode()).hexdigest()[:8], 16))
        r = rng.normal(0.0005, 0.018, days); c = 100 * np.exp(np.cumsum(r))
        o = c * (1 + rng.normal(0, 0.004, days)); h = np.maximum(o, c) * (1 + abs(rng.normal(0, 0.006, days)))
        l = np.minimum(o, c) * (1 - abs(rng.normal(0, 0.006, days))); v = rng.integers(1_000_000, 5_000_000, days).astype(float)
        out[s] = pd.DataFrame(dict(Open=o, High=h, Low=l, Close=c, Volume=v), index=idx)
    return out

PRICE_SOURCES = {"yfinance": yfinance_daily, "alpaca": alpaca_daily, "polygon": polygon_daily, "demo": demo_daily}

def get_daily(symbols, days, cfg, timeout=60):
    """Use the selected price source; on failure fall back through the other ENABLED sources. Returns (data, source, errors)."""
    d = cfg["data"]; order = [d["price_source"]] + [n for n, v in d["sources"].items() if v.get("enabled") and n != d["price_source"]]
    errs = []
    for name in order:
        ok, val = with_timeout(PRICE_SOURCES[name], list(symbols), days, timeout=timeout)
        if ok and val: return val, name, errs
        errs.append(f"{name}: {val if not ok else 'no data'}")
    return {}, None, errs

def headlines(symbol, cfg, per_feed=6, timeout=10):
    out = []
    for f in cfg["data"]["news"]:
        if not f.get("enabled"): continue
        url = f["url"].replace("{symbol}", urllib.parse.quote(symbol))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(urllib.request.urlopen(req, timeout=timeout).read())
            out += [(f["name"], i.findtext("title")) for i in root.iter("item")][:per_feed]
        except Exception: pass
    seen = set(); return [h for h in out if h[1] and not (h[1] in seen or seen.add(h[1]))]

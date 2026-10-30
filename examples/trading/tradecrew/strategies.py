"""Strategies. Each turns daily closes/volumes into a DataFrame of target weights (decided at close t, held from t+1).
The same function drives the live paper portfolio (last row) and the backtester (whole history), so they never drift apart.
Honest note: in our own walk-forward tests none of these clearly beat simply holding QQQ in 2023-2026; the trend
filters mainly reduced drawdowns. See docs/RESEARCH.md."""
import numpy as np, pandas as pd

def rsi(x, n=2):
    d = x.diff(); u = d.clip(lower=0).ewm(alpha=1 / n).mean(); v = (-d.clip(upper=0)).ewm(alpha=1 / n).mean()
    return 100 - 100 / (1 + u / v)

def _col(C, s):
    if s not in C: raise ValueError(f"symbol {s} not in data - add it to the watchlist")
    return C[s]

def vol_managed_qqq(C, V, p):
    """Scale exposure to target_vol / realized vol (lookback), capped at max_weight; remainder in cash_symbol."""
    c = _col(C, p["symbol"]); rv = c.pct_change().rolling(p["lookback"]).std() * np.sqrt(252)
    w = (p["target_vol"] / rv).clip(upper=p["max_weight"]).fillna(0)
    W = pd.DataFrame({p["symbol"]: w}, index=C.index)
    if p.get("cash_symbol") in C: W[p["cash_symbol"]] = 1 - w
    return W

def trend_rsi2(C, V, p):
    """Hold symbol while close > SMA(n); below it only take RSI(2) < rsi_entry bounces, exit when close > 5d SMA."""
    c = _col(C, p["symbol"]); sma = c.rolling(p["sma"]).mean(); r = rsi(c); s5 = c.rolling(5).mean()
    st = pd.Series(np.nan, index=c.index); st[r < p["rsi_entry"]] = 1; st[c > s5] = 0
    bounce = st.ffill().fillna(0) > 0
    return pd.DataFrame({p["symbol"]: ((c > sma) | bounce).astype(float)}, index=C.index)

def momentum_swing(C, V, p, universe):
    """Buy 20-day-high breakouts above the 50d MA with 5d gain >= min_5d_gain and rising volume; exit on take-profit,
    hard stop, trailing stop, or max_hold days. Up to max_positions, equal weight."""
    U = [s for s in universe if s in C]; c = C[U]; v = V[U]
    sig = (c >= c.shift(1).rolling(20).max()) & (c > c.rolling(50).mean()) & (c / c.shift(5) - 1 >= p["min_5d_gain"]) \
          & (v.rolling(5).mean() > v.rolling(20).mean())
    g5 = c / c.shift(5) - 1; W = pd.DataFrame(0.0, index=C.index, columns=U); held = {}
    for i, t in enumerate(C.index):
        px = c.loc[t]
        for s in list(held):
            e, pk, n = held[s]; pk = max(pk, px[s]); n += 1; held[s] = (e, pk, n)
            if px[s] >= e * (1 + p["take_profit"]) or px[s] <= e * (1 - p["stop_loss"]) or \
               (pk > e * 1.01 and px[s] <= pk * (1 - p["trail"])) or n >= p["max_hold"]: del held[s]
        cand = [s for s in g5.loc[t][sig.loc[t]].sort_values(ascending=False).index if s not in held]
        for s in cand[: max(0, p["max_positions"] - len(held))]: held[s] = (px[s], px[s], 0)
        for s in held: W.at[t, s] = 1 / p["max_positions"]
    return W

def rotation(C, V, p):
    """Hold the strongest 'rising' name (close > MA(ma_trend), 5d and 10d return > 0) of a small universe; sell when
    close < MA(ma_exit) or trailing stop; 1 slot (100%) below two_slot_equity, 2 slots (50/50) above."""
    U = [s for s in p["universe"] if s in C]; c = C[U]
    r5, r10 = c / c.shift(5) - 1, c / c.shift(10) - 1; ma_t, ma_x = c.rolling(p["ma_trend"]).mean(), c.rolling(p["ma_exit"]).mean()
    elig = (c > ma_t) & (r5 > 0) & (r10 > 0); score = 0.5 * r5 + 0.5 * r10
    W = pd.DataFrame(0.0, index=C.index, columns=U); held = {}; eq = 1.0; prev = None
    for t in C.index:
        if prev is not None: eq *= 1 + sum(W.loc[prev, s] * (c.at[t, s] / c.at[prev, s] - 1) for s in U if W.loc[prev, s])
        slots = 2 if eq * p.get("_capital", 200) >= p["two_slot_equity"] else 1
        for s in list(held):
            held[s] = max(held[s], c.at[t, s])
            if c.at[t, s] < ma_x.at[t, s] or c.at[t, s] <= held[s] * (1 - p["trail"]): del held[s]
        for s in [s for s in score.loc[t][elig.loc[t]].sort_values(ascending=False).index if s not in held][: max(0, slots - len(held))]:
            held[s] = c.at[t, s]
        for s in held: W.at[t, s] = 1 / max(slots, len(held))
        prev = t
    return W

def short_term_team(C, V, p, universe):
    """Daily proxy of the agent team: close > 20d MA, close > 50d MA, day change >= min_day_change; exit on
    atr_mult x ATR trailing stop. Risk-based sizing (risk_per_trade / stop distance), at most max_positions."""
    U = [s for s in universe if s in C]; c = C[U]
    atr = c.diff().abs().rolling(14).mean(); ch = c.pct_change()
    sig = (c > c.rolling(20).mean()) & (c > c.rolling(50).mean()) & (ch >= p["min_day_change"])
    W = pd.DataFrame(0.0, index=C.index, columns=U); held = {}
    for t in C.index:
        for s in list(held):
            stop, w = held[s]; stop = max(stop, c.at[t, s] - p["atr_mult"] * atr.at[t, s])
            if c.at[t, s] <= stop: del held[s]
            else: held[s] = (stop, w)
        for s in [s for s in ch.loc[t][sig.loc[t]].sort_values(ascending=False).index if s not in held][: p["max_positions"] - len(held)]:
            dist = p["atr_mult"] * atr.at[t, s] / c.at[t, s]
            if dist > 0: held[s] = (c.at[t, s] - p["atr_mult"] * atr.at[t, s], min(p["risk_per_trade"] / dist, 1 / p["max_positions"]))
        for s, (_, w) in held.items(): W.at[t, s] = w
    return W

STRATEGIES = {
    "short_term_team": dict(label="Short-term team", fn=short_term_team, needs_universe=True),
    "vol_managed_qqq": dict(label="Vol-managed QQQ", fn=vol_managed_qqq),
    "trend_rsi2": dict(label="Trend + RSI(2)", fn=trend_rsi2),
    "momentum_swing": dict(label="Momentum swing", fn=momentum_swing, needs_universe=True),
    "rotation": dict(label="Rotation", fn=rotation),
}

def symbols_for(name, p, watchlist):
    if name in ("vol_managed_qqq", "trend_rsi2"): return [p["symbol"]] + ([p["cash_symbol"]] if p.get("cash_symbol") else [])
    if name == "rotation": return list(p["universe"])
    return list(watchlist)

def weights(name, C, V, p, watchlist, capital=200.0):
    s = STRATEGIES[name]; p = {k: v for k, v in p.items() if k != "enabled"}
    if name == "rotation": p["_capital"] = capital
    return s["fn"](C, V, p, watchlist) if s.get("needs_universe") else s["fn"](C, V, p)

def explain(name, C, p, w_last):
    held = {s: round(float(w), 3) for s, w in w_last.items() if w > 1e-4}
    if name == "trend_rsi2":
        c = C[p["symbol"]]; sma = c.rolling(p["sma"]).mean().iloc[-1]
        return f"{p['symbol']} close {c.iloc[-1]:.2f} vs {p['sma']}d SMA {sma:.2f}, RSI2={rsi(c).iloc[-1]:.0f} -> " + ("hold" if held else "cash")
    if name == "vol_managed_qqq":
        rv = C[p["symbol"]].pct_change().rolling(p["lookback"]).std().iloc[-1] * np.sqrt(252)
        return f"realized vol {rv:.1%} vs target {p['target_vol']:.0%} -> {p['symbol']} weight {w_last.get(p['symbol'], 0):.0%}"
    return ("holding " + ", ".join(f"{s} {w:.0%}" for s, w in held.items())) if held else "no qualifying signal -> cash"

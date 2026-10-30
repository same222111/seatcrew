"""Vectorized backtester with costs and a train / out-of-sample split; plus the PROPOSER -> VALIDATOR research loop."""
import json, numpy as np, pandas as pd
from . import strategies as S, data as D
from .providers import ask_role

def run(W, C, cost_bps=3.0):
    W = W.reindex(C.index).fillna(0.0); held = W.shift(1).fillna(0.0)
    r = (held * C[W.columns].pct_change().fillna(0)).sum(axis=1)
    turn = held.diff().abs().sum(axis=1).fillna(held.abs().sum(axis=1))
    return r - turn * cost_bps / 1e4, turn

def stats(r):
    r = r.dropna()
    if len(r) < 20: return None
    eq = (1 + r).cumprod(); yrs = len(r) / 252; sd = r.std() * np.sqrt(252)
    return dict(cagr=round(float(eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1), max_dd=round(float((eq / eq.cummax() - 1).min()) * 100, 1),
                sharpe=round(float(r.mean() * 252 / sd), 2) if sd > 0 else 0.0, days=len(r))

def backtest(name, cfg, years=5, params=None, prices=None, benchmark="QQQ", split=0.7, cost_bps=3.0):
    p = dict(cfg["strategies"][name], **(params or {})); syms = sorted(set(S.symbols_for(name, p, cfg["watchlist"]) + [benchmark]))
    if prices is None:
        prices, src, errs = D.get_daily(syms, int(years * 252) + 220, cfg)
        if not prices: raise RuntimeError("no price data: " + "; ".join(errs))
    else: src = "provided"
    C = pd.DataFrame({s: df["Close"] for s, df in prices.items()}).ffill().dropna(how="all")
    V = pd.DataFrame({s: df["Volume"] for s, df in prices.items()}).reindex(C.index)
    W = S.weights(name, C, V, p, cfg["watchlist"], cfg["capital"])
    warm = 200 if len(C) > 400 else 60; C, W = C.iloc[warm:], W.iloc[warm:]
    r, turn = run(W, C, cost_bps); bh = C[benchmark].pct_change().fillna(0) if benchmark in C else None
    k = int(len(r) * split); eq = (1 + r).cumprod()
    out = dict(strategy=name, params={k2: v for k2, v in p.items() if k2 != "enabled"}, source=src, start=str(C.index[0].date()),
               end=str(C.index[-1].date()), full=stats(r), train=stats(r.iloc[:k]), test=stats(r.iloc[k:]),
               trades_per_year=round(float((turn > 0).sum() / (len(r) / 252)), 1),
               equity=[[str(t.date()), round(float(v) * cfg["capital"], 2)] for t, v in eq.iloc[::max(1, len(eq) // 150)].items()])
    if bh is not None:
        out["benchmark"] = dict(symbol=benchmark, full=stats(bh), train=stats(bh.iloc[:k]), test=stats(bh.iloc[k:]))
        out["benchmark_equity"] = [[str(t.date()), round(float(v) * cfg["capital"], 2)] for t, v in (1 + bh).cumprod().iloc[::max(1, len(bh) // 150)].items()]
    return out

GRID = {"trend_rsi2": dict(sma=[100, 150, 200], rsi_entry=[5, 10]), "vol_managed_qqq": dict(target_vol=[0.15, 0.2, 0.25], lookback=[20, 60]),
        "momentum_swing": dict(take_profit=[0.04, 0.06, 0.08], stop_loss=[0.03, 0.05]), "rotation": dict(trail=[0.04, 0.06, 0.1], ma_exit=[5, 10]),
        "short_term_team": dict(atr_mult=[2.0, 3.0], min_day_change=[0.0, 0.005, 0.01])}

def research(name, cfg, rounds=3, years=5, log=lambda *a: None):
    """PROPOSER suggests params (AI if assigned, else grid walk); VALIDATOR judges train vs out-of-sample (AI if assigned,
    else rule: test Sharpe >= 0.9 x benchmark test Sharpe and test >= 50% of train Sharpe). Returns history + best."""
    import itertools, random
    syms = sorted(set(S.symbols_for(name, cfg["strategies"][name], cfg["watchlist"]) + ["QQQ"]))
    prices, src, errs = D.get_daily(syms, int(years * 252) + 220, cfg)
    if not prices: raise RuntimeError("no price data: " + "; ".join(errs))
    grid = [dict(zip(GRID[name], v)) for v in itertools.product(*GRID[name].values())]; random.Random(0).shuffle(grid)
    hist = []
    for i in range(rounds):
        tried = [h["params"] for h in hist]; untried = [g for g in grid if g not in tried] or grid
        prop = untried[0]; who = "rules (next untested grid point)"
        ai = ask_role("scan", f"Strategy {name}. Grid: {json.dumps(GRID[name])}. Past: {json.dumps([(h['params'], h['test']) for h in hist])[:1500]}. "
                      f"Pick the index (0..{len(grid)-1}) of: {json.dumps(grid)}", [str(j) for j in range(len(grid))], cfg)
        if ai and ai["ok"]:
            if grid[int(ai["label"])] in tried: who = f"{ai['provider']} repeated a tested set -> using next untested grid point"
            else: prop = grid[int(ai["label"])]; who = f"{ai['provider']}: {ai['reason']}"
        log("PROPOSER", f"round {i+1}: {prop} ({who})")
        bt = backtest(name, cfg, years, prop, prices=prices); b = bt.get("benchmark", {})
        ok = bool(bt["test"] and b.get("test") and bt["test"]["sharpe"] >= 0.9 * b["test"]["sharpe"] and bt["train"] and bt["test"]["sharpe"] >= 0.5 * bt["train"]["sharpe"])
        verdict, why = ("pass" if ok else "fail"), "rule: OOS Sharpe vs benchmark and vs train"
        ai = ask_role("judge", json.dumps(dict(train=bt["train"], test=bt["test"], benchmark=b)), ["pass", "fail"], cfg)
        if ai and ai["ok"]:
            why = f"{ai['provider']}: {ai['reason']}"; verdict = "pass" if ok and ai["label"] == "pass" else "fail"
        log("VALIDATOR", f"round {i+1}: {verdict} - test {bt['test']} vs {b.get('symbol')} {b.get('test')} ({why})")
        hist.append(dict(params=prop, train=bt["train"], test=bt["test"], benchmark_test=b.get("test"), verdict=verdict, why=why))
    passed = [h for h in hist if h["verdict"] == "pass"]
    # choose on TRAIN Sharpe only (choosing on the out-of-sample column would be data snooping)
    best = max(passed or hist, key=lambda h: (h["train"] or {}).get("sharpe", -9))
    return dict(strategy=name, source=src, rounds=hist, best=best, any_passed=bool(passed))

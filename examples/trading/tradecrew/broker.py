"""Brokers. Only PaperBroker is implemented. LiveBroker is an interface stub that is disabled by default and raises -
TradeCrew deliberately ships WITHOUT live trading. If you implement one, you take full responsibility."""
import json, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")
# US equities, many retail brokers: regular 09:30-16:00, pre 04:00/07:00-09:30, after 16:00-20:00, overnight 20:00-04:00 Sun-Fri.
SLIPPAGE = {"regular": 0.0005, "pre": 0.0025, "after": 0.0025, "overnight": 0.005, "closed": 0.0}

def now(): return dt.datetime.now(NY)

def session(t=None):
    t = (t or now()).astimezone(NY); wd, h = t.weekday(), t.time()
    if wd == 5 or (wd == 4 and h >= dt.time(20)) or (wd == 6 and h < dt.time(20)): return "closed"
    if wd < 5 and dt.time(9, 30) <= h < dt.time(16): return "regular"
    if wd < 5 and dt.time(4) <= h < dt.time(9, 30): return "pre"
    if wd < 5 and dt.time(16) <= h < dt.time(20): return "after"
    return "overnight"

def fractional_ok(t=None): return session(t) == "regular"

class PaperBroker:
    """Simulated fills: price x (1 +/- session slippage). Off regular hours only whole-share limit orders are allowed."""
    def __init__(self, name, capital, state_dir):
        self.name = name; self.f = Path(state_dir) / f"portfolio_{name}.json"; self.f.parent.mkdir(parents=True, exist_ok=True)
        self.p = json.loads(self.f.read_text(encoding="utf-8")) if self.f.exists() else dict(cash=float(capital), start=float(capital), pos={}, trades=[], day="", day_start=float(capital), orders_today=0)
    def save(self): self.f.write_text(json.dumps(self.p, indent=1), encoding="utf-8")
    def equity(self, px): return self.p["cash"] + sum(q * px.get(s, 0) for s, q in self.p["pos"].items())
    def roll_day(self, px):
        d = now().strftime("%Y-%m-%d")
        if self.p["day"] != d: self.p.update(day=d, day_start=self.equity(px), orders_today=0)
    def fill(self, sym, qty, price, sess, reason):
        if sess == "closed": raise RuntimeError("market closed")
        side = "buy" if qty > 0 else "sell"; fp = price * (1 + SLIPPAGE[sess] * (1 if qty > 0 else -1))
        if qty > 0: qty = min(qty, self.p["cash"] / fp)
        else: qty = -min(-qty, self.p["pos"].get(sym, 0))
        if abs(qty) < 1e-6: return None
        self.p["cash"] -= qty * fp; self.p["pos"][sym] = round(self.p["pos"].get(sym, 0) + qty, 6)
        if self.p["pos"][sym] <= 1e-6: self.p["pos"].pop(sym)
        t = dict(ts=now().isoformat(timespec="seconds"), sym=sym, side=side, qty=round(abs(qty), 6), price=round(fp, 4), session=sess, reason=reason)
        self.p["trades"] = (self.p["trades"] + [t])[-200:]; self.p["orders_today"] += 1; self.save(); return t

    def revert(self, t):
        """Undo a paper fill (used when the REVIEW seat blocks a trade). Impossible with a real broker - paper only."""
        q = t["qty"] * (1 if t["side"] == "buy" else -1)
        self.p["cash"] += q * t["price"]; self.p["pos"][t["sym"]] = round(self.p["pos"].get(t["sym"], 0) - q, 6)
        if self.p["pos"][t["sym"]] <= 1e-6: self.p["pos"].pop(t["sym"])
        self.p["trades"] = [x for x in self.p["trades"] if x is not t and x != t]; self.p["orders_today"] -= 1; self.save()

class LiveBroker:
    """Interface stub for a real broker. Disabled: every method raises. Not part of this project's scope."""
    enabled = False
    def __init__(self, *a, **k): raise NotImplementedError("Live trading is intentionally not included. TradeCrew is paper-only.")

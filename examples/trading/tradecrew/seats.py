"""TradeCrew, the flagship SeatCrew example: eight seats, each owns ONE job, plus REVIEW and a Runner.

    CHIEF   commander - plans each cycle, may HOLD all new entries (AI: proceed|hold)
    QUANT   risk dial - sets the crew-wide risk level normal/cautious/defensive (AI may only make it MORE cautious)
    STOCKS  universe + information desk - watchlist, price data, news headlines (AI: headline sentiment)
    SCAN    research - turns strategy signals into trade IDEAS, ranks candidates (AI: candidate|skip)
    JUDGE   evaluates each idea - an idea is not a trigger (AI: approve|reject)
    RISK    hard limits - kill switch, daily loss cap, order cap, session (AI: approve|veto)
    SIZE    position sizing - dollars -> shares, risk dial, whole shares off-hours (AI: keep|halve)
    FILLS   order desk - simulated paper fills with session slippage (AI: now|wait)
    REVIEW  post-trade replay - checks the fill against the intent; a failed review reverts the paper fill (AI: ok|flag)
    Runner  runs the pipeline on a schedule.

Every order walks the CHECK CHAIN  SCAN -> JUDGE -> RISK -> SIZE -> FILLS -> REVIEW.
Each step returns CHECK OK or CHECK BLOCKED + reason. The first BLOCKED stops the order, so a single
point of failure is intercepted instead of running all the way to a trade.

To add a seat: subclass Seat, implement check(order) -> (ok, reason), add it to Crew.chain, add it to
config.SEATS / DEFAULT_PROMPTS and the locale files. See AGENTS.md."""
import itertools, json, threading, time, traceback
from pathlib import Path
import numpy as np, pandas as pd
from . import data as D, strategies as S
from .broker import PaperBroker, SLIPPAGE, session, fractional_ok, now
from seatcrew import core as K

DIAL = {"normal": 1.0, "cautious": 0.5, "defensive": 0.25}
_ids = itertools.count(1)

class Seat(K.Seat):
    """Trading seats are framework seats; each overrides check(order) with its own rules + AI labels."""
    def check(self, order): return True, "ok"

class Chief(Seat):
    name = "chief"; job = "commander"
    def plan(self, orders, dial, sess):
        buys = sum(o["side"] == "buy" for o in orders)
        self.crew.log(self.name, "PLAN", f"session={sess}, risk dial={dial}, {len(orders)} ideas ({buys} buys)")
        if buys:
            o = self.ai(f"Session {sess}. Risk dial {dial}. Ideas: {json.dumps([(x['sym'], x['side'], round(x['dollars'], 2)) for x in orders])}", ["proceed", "hold"])
            if o and o["label"] == "hold": return False
        return True

class Quant(Seat):
    name = "quant"; job = "risk dial"
    def dial(self, C):
        """Rules: benchmark below its 200d SMA -> cautious; 20d realized vol > 35% -> defensive. Manual override in Settings."""
        if self.cfg["risk_dial"] != "auto": lvl, why = self.cfg["risk_dial"], "manual setting"
        else:
            b = next((s for s in ("QQQ", "SPY") if s in C), None)
            if b is None: lvl, why = "normal", "no benchmark in data"
            else:
                c = C[b].dropna(); vol = c.pct_change().tail(20).std() * np.sqrt(252); below = len(c) > 200 and c.iloc[-1] < c.rolling(200).mean().iloc[-1]
                lvl = "defensive" if vol > 0.35 else "cautious" if below else "normal"
                why = f"{b} 20d vol {vol:.0%}, {'below' if below else 'above'} 200d SMA"
        o = self.ai(f"Rule dial {lvl} ({why})", list(DIAL))
        if o and DIAL[o["label"]] < DIAL[lvl]: lvl, why = o["label"], why + f"; AI: {o['reason']}"
        self.crew.log(self.name, "DIAL", f"{lvl} x{DIAL[lvl]} ({why})"); return lvl

class Stocks(Seat):
    name = "stocks"; job = "universe & info"
    def universe(self):
        cfg = self.cfg; names = [n for n, p in cfg["strategies"].items() if p.get("enabled")]
        return sorted(set(cfg["watchlist"]).union(*[S.symbols_for(n, cfg["strategies"][n], cfg["watchlist"]) for n in names]))
    def load(self):
        syms = self.universe(); prices, src, errs = D.get_daily(syms, 320, self.cfg)
        for e in errs: self.crew.log(self.name, "ERROR", e)
        self.crew.log(self.name, "DATA", f"{len(prices)}/{len(syms)} symbols from {src}")
        return prices, src
    def news(self, sym):
        if not any(f.get("enabled") for f in self.cfg["data"]["news"]): return None
        hl = D.headlines(sym, self.cfg)
        self.crew.log(self.name, "NEWS", f"{len(hl)} headlines" + (f"; latest: {hl[0][1][:90]} ({hl[0][0]})" if hl else ""), sym)
        o = self.ai(f"Ticker {sym}. Headlines:\n" + "\n".join(f"- {h}" for _, h in hl[:8]), ["bullish", "bearish", "neutral"], sym) if hl else None
        return o["label"] if o else None

class Scan(Seat):
    name = "scan"; job = "research ideas"
    def rank(self, stats):
        top = sorted(stats, key=lambda s: -stats[s]["ret5"])[:3]
        if top:
            self.crew.log(self.name, "CANDIDATES", "strongest 5d: " + ", ".join(f"{s} {stats[s]['ret5']:+.1f}%" for s in top))
            self.ai(json.dumps(dict(symbol=top[0], **stats[top[0]])), ["candidate", "skip"], top[0])
    def check(self, o):
        if o["px"] is None or o["px"] <= 0: return False, "no fresh price for this symbol"
        return True, f"idea from {o['label']}: {o['why']}"

class Judge(Seat):
    name = "judge"; job = "evaluates ideas"
    def check(self, o):
        if o["side"] == "sell": return True, "exit idea - exits are always allowed"
        st = self.crew.stats.get(o["sym"]) or {}
        if st.get("chg", 0) <= -5: return False, f"falling knife: {st['chg']:+.1f}% today"
        if self.crew.stocks.news(o["sym"]) == "bearish": return False, "STOCKS reports bearish headlines"
        a = self.ai(f"Idea: {o['label']} wants to buy ${o['dollars']:.2f} of {o['sym']}. Reason: {o['why']}. Stats: {st}", ["approve", "reject"], o["sym"])
        if a and a["label"] == "reject": return False, f"AI judge rejected: {a['reason']}"
        return True, "idea consistent with data" + (" and news" if self.cfg["data"]["news"] else "")

class Risk(Seat):
    name = "risk"; job = "hard limits"
    def check(self, o):
        r, b = self.cfg["risk"], o["broker"]
        if o["sess"] == "closed": return False, "market closed - idea queued for next session"
        if o["side"] == "sell": return True, "exits allowed"
        if r["kill_switch"]: return False, "kill switch ON"
        if b.p["day_start"] - o["equity"] >= r["daily_loss_cap"]: return False, f"daily loss cap ${r['daily_loss_cap']} hit"
        if b.p["orders_today"] >= r["max_orders_per_day"]: return False, f"max {r['max_orders_per_day']} orders/day reached"
        a = self.ai(f"{o['label']} wants to buy ${o['dollars']:.2f} of {o['sym']}. Reason: {o['why']}. Stats: {self.crew.stats.get(o['sym'])}", ["approve", "veto"], o["sym"])
        if a and a["label"] == "veto": return False, f"AI risk veto: {a['reason']}"
        return True, f"limits ok ({b.p['orders_today']}/{r['max_orders_per_day']} orders, loss cap ${r['daily_loss_cap']})"

class Size(Seat):
    name = "size"; job = "position sizing"
    def check(self, o):
        dv = o["dollars"] * (DIAL[self.crew.dial_level] if o["side"] == "buy" else 1); qty = dv / o["px"]
        if not fractional_ok():
            qty = float(int(qty)) if qty > 0 else -float(min(o["broker"].p["pos"].get(o["sym"], 0), int(-qty) or o["broker"].p["pos"].get(o["sym"], 0)))
            if qty == 0: return False, f"{o['sess']} session: whole shares only, ${dv:.2f} < 1 share (${o['px']:.2f})"
        if abs(qty * o["px"]) < 1: return False, f"order too small (${abs(qty * o['px']):.2f})"
        if o["side"] == "buy":
            a = self.ai(f"Rule size {qty:.4f} sh (${dv:.2f}) of {o['sym']}, equity ${o['equity']:.2f}", ["keep", "halve"], o["sym"])
            if a and a["label"] == "halve": qty /= 2
        o["qty"] = qty
        return True, f"{abs(qty):.4f} sh (${abs(qty * o['px']):.2f}, dial {self.crew.dial_level})"

class Fills(Seat):
    name = "fills"; job = "order desk"
    def check(self, o):
        if o["side"] == "buy":
            a = self.ai(f"Session {o['sess']}. Buy {o['qty']:.4f} {o['sym']} @ {o['px']:.2f}", ["now", "wait"], o["sym"])
            if a and a["label"] == "wait": return False, f"AI order desk chose to wait: {a['reason']}"
        try: t = o["broker"].fill(o["sym"], o["qty"], o["px"], o["sess"], f"{o['label']}: {o['why']}")
        except Exception as e: return False, f"fill failed: {e}"
        if not t: return False, "nothing to fill (no cash / no position)"
        o["trade"] = t; return True, f"PAPER {t['side']} {t['qty']} @ {t['price']} ({o['sess']})"

class Review(Seat):
    name = "review"; job = "post-trade replay"
    def check(self, o):
        t = o["trade"]; slip = abs(t["price"] / o["px"] - 1); lim = SLIPPAGE[o["sess"]] * 2 + 1e-6
        problems = []
        if slip > lim: problems.append(f"slippage {slip:.3%} > {lim:.3%}")
        if t["qty"] * t["price"] > abs(o["dollars"]) * 1.02 + 1: problems.append("filled more than intended")
        if o["broker"].p["cash"] < -0.01: problems.append("negative cash")
        a = self.ai(f"Intended {o['side']} ${abs(o['dollars']):.2f} {o['sym']} @~{o['px']:.2f}; filled {t['qty']} @ {t['price']}", ["ok", "flag"], o["sym"])
        if a and a["label"] == "flag": problems.append(f"AI review flag: {a['reason']}")
        if problems: o["broker"].revert(t); return False, "; ".join(problems) + " -> paper fill reverted"
        return True, f"fill matches intent (slippage {slip:.3%})"

class Crew(K.Workflow):
    """The trading workflow. Items are paper orders; the chain is SCAN -> JUDGE -> RISK -> SIZE -> FILLS -> REVIEW."""
    name = "trading"; title = "TradeCrew - paper trading"
    interval_key = "scan_interval_sec"; persist_items = False; done_status = "filled"
    locale_dirs = (Path(__file__).parent / "locales",)
    def __init__(self, cfg, state_dir="state"):
        super().__init__(cfg, state_dir)
        self.chief, self.quant, self.stocks, self.scan = Chief(self), Quant(self), Stocks(self), Scan(self)
        self.judge, self.risk, self.size, self.fills, self.review = Judge(self), Risk(self), Size(self), Fills(self), Review(self)
        self.setup([self.chief, self.quant, self.stocks, self.scan, self.judge, self.risk, self.size, self.fills, self.review],
                   ["scan", "judge", "risk", "size", "fills", "review"])   # the check chain
        self.stats, self.px, self.reasons, self.brokers = {}, {}, {}, {}
        self.source = None; self.dial_level = "normal"; self._hold_buys = False

    orders = property(lambda self: self.items, lambda self, v: setattr(self, "items", v))

    def broker(self, name):
        if name not in self.brokers: self.brokers[name] = PaperBroker(name, self.cfg["capital"], self.state_dir)
        return self.brokers[name]

    def gate(self, seat, o):
        if self._hold_buys and seat is self.judge and o["side"] == "buy": return False, "CHIEF is holding new entries this cycle"
        return None

    def run_chain(self, o, hold_buys=False, start=0):
        """Walk one order through the framework's check chain. Returns True if it was filled and passed review."""
        self._hold_buys = hold_buys
        try: return super().run_chain(o, start)
        finally: self._hold_buys = False

    def ideas(self, C, V, sess):
        """SCAN turns each enabled strategy's target weights into order ideas (sells first)."""
        out = []
        for name, p in self.cfg["strategies"].items():
            if not p.get("enabled"): continue
            b = self.broker(name); b.roll_day(self.px); eq = b.equity(self.px)
            try: W = S.weights(name, C, V, p, self.cfg["watchlist"], eq)
            except Exception as e: self.log("scan", "ERROR", f"{name}: {e}"); continue
            w = W.iloc[-1].fillna(0); why = S.explain(name, C, p, w); self.reasons[name] = why
            for s in sorted(set(w.index) | set(b.p["pos"])):
                dv = float(w.get(s, 0)) * eq - b.p["pos"].get(s, 0) * self.px.get(s, 0)
                if abs(dv) >= max(1.0, 0.05 * eq):
                    out.append(dict(id=next(_ids), title=f"{'BUY' if dv > 0 else 'SELL'} {s} ${abs(dv):.2f}", subject=s, portfolio=name, label=S.STRATEGIES[name]["label"], sym=s, side="buy" if dv > 0 else "sell",
                                    dollars=dv, px=self.px.get(s), sess=sess, why=why, equity=eq, broker=b, ts=now().isoformat(timespec="seconds")))
        return sorted(out, key=lambda o: o["dollars"])

    def run_cycle(self):
        cfg = self.cfg.data; sess = session(); self.cycle_no += 1
        self.log("chief", "CYCLE", f"cycle {self.cycle_no} start, session={sess}")
        prices, src = self.stocks.load()
        if not prices: self.log("chief", "ERROR", "no price data this cycle"); return
        self.source = src
        C = pd.DataFrame({s: df["Close"] for s, df in prices.items()}).ffill(); V = pd.DataFrame({s: df["Volume"] for s, df in prices.items()}).reindex(C.index)
        self.px = {s: float(C[s].dropna().iloc[-1]) for s in C}
        self.stats = {}
        for s in cfg["watchlist"]:
            c = C[s].dropna() if s in C else []
            if len(c) >= 60:
                self.stats[s] = dict(price=round(c.iloc[-1], 2), chg=round((c.iloc[-1] / c.iloc[-2] - 1) * 100, 2), ma20=bool(c.iloc[-1] > c.rolling(20).mean().iloc[-1]),
                                     ma50=bool(c.iloc[-1] > c.rolling(50).mean().iloc[-1]), ret5=round((c.iloc[-1] / c.iloc[-6] - 1) * 100, 2))
        self.dial_level = self.quant.dial(C); self.scan.rank(self.stats)
        orders = self.ideas(C, V, sess); proceed = self.chief.plan(orders, self.dial_level, sess)
        if not proceed: self.log("chief", "HOLD", "CHIEF holds all new entries this cycle (exits still run)")
        filled = sum(self.run_chain(o, hold_buys=not proceed) for o in orders)
        self.log("chief", "DONE", f"cycle {self.cycle_no}: {filled}/{len(orders)} orders filled"); self.active = None
        self.last_cycle = now().isoformat(timespec="seconds")
    cycle = run_cycle  # backwards-compatible name

    def snapshot(self):
        cfg = self.cfg.data; ports = {}
        for n, p in cfg["strategies"].items():
            if not p.get("enabled") and n not in self.brokers: continue
            b = self.broker(n); eq = b.equity(self.px)
            ports[n] = dict(label=S.STRATEGIES[n]["label"], enabled=p.get("enabled"), equity=round(eq, 2), start=b.p["start"], cash=round(b.p["cash"], 2),
                            ret=round((eq / b.p["start"] - 1) * 100, 2), pos={s: dict(qty=q, value=round(q * self.px.get(s, 0), 2)) for s, q in b.p["pos"].items()},
                            trades=b.p["trades"][-8:], reason=self.reasons.get(n, ""))
        seats = {k: dict(v, active=(self.active == k) or (time.time() - v["t"] < 4), ai=cfg["seats"][k]["provider"] + (f"/{cfg['seats'][k]['model']}" if cfg["seats"][k].get("model") else ""))
                 for k, v in self.seats.items()}
        orders = [{k: v for k, v in o.items() if k != "broker"} for o in self.orders[:30]]
        panels = [dict(title="Paper portfolios", columns=["portfolio", "equity", "return %", "cash", "positions"],
                       rows=[[p["label"], p["equity"], p["ret"], p["cash"], ", ".join(f"{s} {v['qty']:.3f}" for s, v in p["pos"].items())] for p in ports.values()])]
        return dict(workflow=self.name, title=self.title, items=orders, panels=panels, time=now().isoformat(timespec="seconds"), session=session(), fractional=fractional_ok(), source=self.source, cycle=self.cycle_no,
                    last_cycle=self.last_cycle, seats=seats, events=self.events[-120:], stats=self.stats, portfolios=ports, orders=orders,
                    dial=self.dial_level, kill_switch=cfg["risk"]["kill_switch"], setup_complete=cfg["setup_complete"], language=cfg["language"],
                    runner=dict(interval=cfg["scan_interval_sec"], running=not self.stop.is_set()))

    def reset(self):
        for f in self.state_dir.glob("portfolio_*.json"): f.unlink()
        self.brokers = {}; self.orders = []; self.log("chief", "INFO", "paper portfolios reset")

Runner = K.Runner  # the framework's scheduler (uses Crew.interval_key = scan_interval_sec)

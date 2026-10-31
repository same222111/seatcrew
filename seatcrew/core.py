"""The engine: Seat, HumanSeat, Chief, Workflow (check chain + event log + state) and Runner.

    item  ->  seat 1 -> seat 2 -> ... -> REVIEW
              each seat: check(item) -> (True, reason)   CHECK OK       -> next seat
                                        (False, reason)  CHECK BLOCKED  -> item stops here
                                        (None, reason)   WAITING        -> item parks until a human approves/rejects

A seat's decision = its rules, then (optionally) its assigned AI. The AI answers with one label from `labels`;
if that label is in `block_labels` the seat blocks. The AI can therefore only make the decision MORE cautious,
and any AI failure (no key, timeout, bad JSON, budget) abstains so the rules stay in control.

Subclass Workflow and override collect() (where items come from), or describe everything in YAML (yamlflow.py)."""
import itertools, json, os, threading, time, traceback
from datetime import datetime
from pathlib import Path
from .llm import ask_role

def now(): return datetime.now().astimezone()

class Seat:
    """One job. Override rules(item) and/or ai_prompt(item). Or override check(item) completely."""
    name = "seat"; job = ""
    labels = ()          # labels the seat's AI may answer with, e.g. ("ok", "flag")
    block_labels = ()    # which of those labels block the item
    kind = "check"       # check | human | producer (shown in the UI)

    def __init__(self, wf, name=None, job=None, labels=None, block_labels=None):
        self.wf = wf; self.name = name or self.name; self.job = job if job is not None else self.job
        if labels is not None: self.labels = tuple(labels)
        if block_labels is not None: self.block_labels = tuple(block_labels)
    crew = property(lambda self: self.wf)                 # alias used by the trading example
    @property
    def cfg(self): return self.wf.cfg.data

    def ai(self, prompt, labels, subject="-"):
        """Ask this seat's assigned AI. Returns its dict or None (rules-only / abstained). Logged either way."""
        o = ask_role(self.name, prompt, labels, self.cfg)
        if o: self.wf.log(self.name, "AI" if o["ok"] else "AI-ERR", f"[{o['provider']}/{o['model']}] {o['label']}: {o['reason']}", subject)
        return o if o and o["ok"] else None

    def rules(self, item):
        """Deterministic part. Return (ok, reason)."""
        return True, "ok"

    def ai_prompt(self, item):
        """Text sent to this seat's AI (None = don't ask). Default: the item's title + data as JSON."""
        return f"{item.get('title', '')}\n{json.dumps(item.get('data', {}), ensure_ascii=False, default=str)[:3000]}"

    def check(self, item):
        ok, why = self.rules(item)
        if ok is not True or not self.labels: return ok, why
        prompt = self.ai_prompt(item)
        a = self.ai(prompt, self.labels, Workflow.subject(item)) if prompt else None
        if a and a["label"] in self.block_labels: return False, f"AI {a['label']}: {a['reason']}"
        return ok, why + (f" · AI {a['label']}" if a else "")

class HumanSeat(Seat):
    """Human-in-the-loop gate: parks the item until someone approves or rejects it (dashboard button or `run --yes`)."""
    kind = "human"; job = "human approval"
    def check(self, item):
        d = item.get("decisions", {}).get(self.name)
        if d is None:
            if self.cfg.get("settings", {}).get(f"{self.name}_auto_approve"): return True, "auto-approved (setting)"
            return None, "waiting for a human to approve"
        return (True, f"approved by human{': ' + d['note'] if d.get('note') else ''}") if d["approve"] else (False, f"rejected by human{': ' + d['note'] if d.get('note') else ''}")

class Chief(Seat):
    """The orchestrator: opens and closes each cycle and may HOLD new items (AI labels proceed|hold)."""
    name = "chief"; job = "commander"; labels = ("proceed", "hold")
    def plan(self, items):
        self.wf.log(self.name, "PLAN", f"{len(items)} new item(s)")
        if items and self.cfg["seats"].get(self.name, {}).get("provider", "rules") != "rules":
            a = self.ai(f"Workflow {self.wf.name}. New items: {json.dumps([i.get('title') for i in items], ensure_ascii=False)[:2000]}", self.labels)
            if a and a["label"] == "hold": return False
        return True

class Workflow:
    """Ordered check chain of seats + event log + item state. Subclass and override collect(), or use yamlflow."""
    name = "workflow"; title = "Workflow"
    interval_key = "run_interval_sec"
    persist_items = True
    locale_dirs = ()

    def __init__(self, cfg, state_dir="state", seats=(), chain=None):
        self.cfg = cfg; self.state_dir = Path(state_dir); self.state_dir.mkdir(exist_ok=True, parents=True)
        self.log_f = self.state_dir / "log.jsonl"; self.items_f = self.state_dir / "items.json"; self.lock = threading.RLock()
        self._decision_lock = threading.RLock()
        self.stop = threading.Event(); self.wake = threading.Event(); self.inbox = []; self._ids = itertools.count(1)
        self.events, self.items = [], []; self.cycle_no = 0; self.last_cycle = None; self.active = None
        if self.log_f.exists(): self.events = [json.loads(l) for l in self.log_f.read_text(encoding="utf-8").splitlines()[-300:] if l.strip()]
        if seats: self.setup(seats, chain)

    def setup(self, seats, chain=None):
        """seats: Seat instances in grid order. chain: names in check order (default: every non-chief seat)."""
        self.seat_map = {s.name: s for s in seats}
        self.chief = self.seat_map.get("chief")
        self.chain = [self.seat_map[n] for n in chain] if chain else [s for s in seats if s.name != "chief"]
        self.seats = {s.name: dict(status="idle", last="", ts="", t=0.0) for s in seats}
        if self.persist_items and self.items_f.exists():
            self.items = json.loads(self.items_f.read_text(encoding="utf-8"))
            self._ids = itertools.count(max([i["id"] for i in self.items] + [0]) + 1)

    # ---------- event log ----------
    @staticmethod
    def subject(item): return str(item.get("sym") or item.get("subject") or "-")

    def log(self, seat, kind, msg, sym="-", **kw):
        e = dict(ts=now().isoformat(timespec="seconds"), agent=seat.upper(), kind=kind, sym=sym, msg=msg, **kw)
        with self.lock:
            self.events = (self.events + [e])[-300:]
            with open(self.log_f, "a", encoding="utf-8") as f: f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        if seat in self.seats: self.seats[seat] = dict(status=kind, last=f"{sym} {msg}"[:160], ts=e["ts"][11:19], t=time.time())
        self.active = seat; return e

    # ---------- items ----------
    def new_item(self, title, data=None, subject="-", **kw):
        return dict(id=next(self._ids), title=title, subject=subject, data=dict(data or {}), chain=[], status="new",
                    ts=now().isoformat(timespec="seconds"), **kw)

    def submit(self, title=None, data=None, subject="-"):
        """Queue an item for the next cycle (dashboard form / API / code). Returns the item."""
        data = dict(data or {}); title = title or str(next(iter(data.values()), "item"))[:80]
        it = self.new_item(title, data, subject)
        with self.lock: self.inbox.append(it)
        self.log("chief", "SUBMIT", f"#{it['id']} {title}", subject); self.wake.set(); return it

    def collect(self):
        """Where new items come from each cycle. Default: whatever was submitted. Override for feeds/APIs/files."""
        with self.lock: out, self.inbox = self.inbox, []
        return out

    def save_items(self):
        if self.persist_items:
            with self.lock:
                self.items = self._retained_items(200)
                tmp = self.items_f.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.items, ensure_ascii=False, default=str, indent=0), encoding="utf-8")
                os.replace(tmp, self.items_f)

    def _retained_items(self, limit):
        """Bound completed history, but never discard outstanding human approvals."""
        return [item for index, item in enumerate(self.items) if index < limit or "pending" in item]

    def gate(self, seat, item):
        """Hook: return (ok, reason) to override a seat's own check for this item (e.g. CHIEF hold), else None."""
        if getattr(self, "_hold", False) and seat is self.chain[0] and not item.get("exit"): return False, "CHIEF is holding new items this cycle"
        return None

    def run_chain(self, item, start=0):
        """Walk one item through the check chain from `start`. Returns True (passed every seat), False (blocked) or None (waiting)."""
        item.setdefault("chain", [])
        with self.lock:
            if item not in self.items:
                self.items.insert(0, item)
                self.items = self._retained_items(200)
        for i, seat in enumerate(self.chain[start:], start):
            g = self.gate(seat, item)
            if g is not None: ok, why = g
            else:
                try: ok, why = seat.check(item)
                except Exception as e: ok, why = False, f"seat error: {type(e).__name__}: {e}"
            label = item.get("label") or item.get("title", "")
            if ok is None:
                item["status"] = f"waiting at {seat.name.upper()}"; item["pending"] = i
                self.log(seat.name, "WAITING", f"[{label}] #{item['id']} {why}", self.subject(item), order=item["id"]); self.save_items(); return None
            item.pop("pending", None)
            item["chain"].append(dict(seat=seat.name, ok=bool(ok), reason=why, ts=now().strftime("%H:%M:%S")))
            self.log(seat.name, "CHECK_OK" if ok else "CHECK_BLOCKED", f"[{label}] #{item['id']} {why}", self.subject(item), order=item["id"])
            if not ok: item["status"] = f"blocked at {seat.name.upper()}"; self.save_items(); return False
        item["status"] = self.done_status; self.save_items(); return True
    done_status = "done"

    def decide(self, item_id, approve, note=""):
        """A human approves/rejects a waiting item; the chain resumes from that seat."""
        if type(approve) is not bool: raise ValueError("approve must be a boolean")
        # Keep the check and resume together so two HTTP requests cannot execute an action twice.
        # Use a separate lock: long-running seats must not block dashboard reads or event logging.
        with self._decision_lock:
            it = next((i for i in self.items if i["id"] == int(item_id)), None)
            if not it or "pending" not in it: raise ValueError(f"item {item_id} is not waiting for approval")
            seat = self.chain[it["pending"]]
            it.setdefault("decisions", {})[seat.name] = dict(approve=approve, note=str(note)[:200], ts=now().isoformat(timespec="seconds"))
            return self.run_chain(it, it["pending"])

    # ---------- cycle ----------
    def run_cycle(self):
        self.cycle_no += 1; self.log("chief", "CYCLE", f"cycle {self.cycle_no} start")
        items = self.collect()
        self._hold = not self.chief.plan(items) if self.chief else False
        if self._hold: self.log("chief", "HOLD", "CHIEF holds new items this cycle")
        res = [self.run_chain(i) for i in items]; self._hold = False
        self.log("chief", "DONE", f"cycle {self.cycle_no}: {sum(r is True for r in res)} passed, {sum(r is False for r in res)} blocked, {sum(r is None for r in res)} waiting / {len(items)}")
        self.active = None; self.last_cycle = now().isoformat(timespec="seconds")

    # ---------- for the dashboard ----------
    def definition(self):
        """Everything the generic dashboard needs to draw this workflow."""
        return dict(name=self.name, title=self.title, interval_key=self.interval_key,
                    seats=[dict(name=s.name, job=s.job, kind=s.kind, labels=list(s.labels), block_labels=list(s.block_labels)) for s in self.seat_map.values()],
                    chain=[s.name for s in self.chain], submit=getattr(self, "submit_fields", []))

    def panels(self):
        """Optional extra tables for the dashboard: [dict(title, columns, rows)]."""
        return []

    def item_view(self, it):
        return {k: v for k, v in it.items() if not k.startswith("_") and k != "broker"}

    def snapshot(self):
        cfg = self.cfg.data
        seats = {k: dict(v, active=(self.active == k) or (time.time() - v["t"] < 4),
                         ai=cfg["seats"][k]["provider"] + (f"/{cfg['seats'][k]['model']}" if cfg["seats"][k].get("model") else "")) for k, v in self.seats.items()}
        return dict(workflow=self.name, title=self.title, time=now().isoformat(timespec="seconds"), cycle=self.cycle_no, last_cycle=self.last_cycle,
                    seats=seats, items=[self.item_view(i) for i in self._retained_items(40)], events=self.events[-120:], panels=self.panels(),
                    language=cfg["language"], runner=dict(interval=cfg[self.interval_key], running=not self.stop.is_set()))

class Runner:
    """Runs workflow.run_cycle() every <interval_key> seconds; workflow.wake.set() runs it now. auto_run=False = manual only."""
    def __init__(self, wf): self.wf = wf
    def loop(self):
        while not self.wf.stop.is_set():
            if self.wf.cfg.data.get("auto_run", True) or self.wf.wake.is_set():
                self.wf.wake.clear()
                try: self.wf.run_cycle()
                except Exception: self.wf.log("chief", "ERROR", traceback.format_exc()[-300:])
            self.wf.wake.wait(self.wf.cfg.data[self.wf.interval_key])
    def start(self): threading.Thread(target=self.loop, daemon=True, name="runner").start(); return self

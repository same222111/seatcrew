"""Core engine: check chain semantics, human gate, CHIEF hold, AI-only-more-cautious, Runner, config."""
import time, pytest
from seatcrew import Seat, HumanSeat, Chief, Workflow, Runner, llm
from seatcrew.config import Config, base_defaults

class Need(Seat):
    """passes when data[field] is truthy"""
    def __init__(self, wf, name, field, labels=(), block=()): super().__init__(wf, name, f"needs {field}", labels, block); self.field = field
    def rules(self, it): return (True, f"{self.field} ok") if it["data"].get(self.field) else (False, f"{self.field} missing")

def make(tmp_path, human=False, labels=("ok", "flag"), block=("flag",)):
    names = ["chief", "a", "b"] + (["gate"] if human else []) + ["c"]
    wf = Workflow(Config(tmp_path / "c.yaml", base_defaults(names)), tmp_path / "st")
    seats = [Chief(wf), Need(wf, "a", "x"), Need(wf, "b", "y", labels, block)] + ([HumanSeat(wf, "gate")] if human else []) + [Need(wf, "c", "z")]
    wf.setup(seats); return wf

def chain(it): return [(c["seat"], c["ok"]) for c in it["chain"]]

def test_all_pass(tmp_path):
    wf = make(tmp_path); it = wf.new_item("t", dict(x=1, y=1, z=1))
    assert wf.run_chain(it) is True and it["status"] == "done" and chain(it) == [("a", True), ("b", True), ("c", True)]

@pytest.mark.parametrize("missing,seat", [("x", "a"), ("y", "b"), ("z", "c")])
def test_first_block_stops_item(tmp_path, missing, seat):
    wf = make(tmp_path); d = dict(x=1, y=1, z=1); d[missing] = 0; it = wf.new_item("t", d)
    assert wf.run_chain(it) is False and it["status"] == f"blocked at {seat.upper()}"
    assert [c[0] for c in chain(it)] == ["a", "b", "c"][: "abc".index(seat) + 1] and chain(it)[-1][1] is False
    assert any(e["kind"] == "CHECK_BLOCKED" and e["agent"] == seat.upper() for e in wf.events)

def test_seat_exception_blocks(tmp_path):
    wf = make(tmp_path); wf.chain[1].rules = lambda it: 1 / 0
    it = wf.new_item("t", dict(x=1, y=1, z=1)); assert wf.run_chain(it) is False and "ZeroDivisionError" in it["chain"][-1]["reason"]

def test_ai_can_only_add_blocks(tmp_path, ai_says):
    ai_says("flag"); wf = make(tmp_path); wf.cfg.data["seats"]["b"]["provider"] = "xai"
    it = wf.new_item("t", dict(x=1, y=1, z=1)); assert wf.run_chain(it) is False and it["chain"][-1]["reason"].startswith("AI flag")
    ai_says("ok"); it2 = wf.new_item("t", dict(x=1, y=0, z=1))   # AI says ok but rules block -> still blocked
    assert wf.run_chain(it2) is False and it2["chain"][-1]["seat"] == "b"

def test_ai_failure_abstains(tmp_path, monkeypatch):
    def boom(*a): raise llm.LLMError("HTTP 500")
    monkeypatch.setenv("XAI_API_KEY", "k"); monkeypatch.setattr(llm, "_post", boom)
    wf = make(tmp_path); wf.cfg.data["seats"]["b"]["provider"] = "xai"
    assert wf.run_chain(wf.new_item("t", dict(x=1, y=1, z=1))) is True and any(e["kind"] == "AI-ERR" for e in wf.events)

def test_rules_only_never_calls_ai(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_post", lambda *a: pytest.fail("AI called in rules-only mode"))
    assert make(tmp_path).run_chain(make(tmp_path).new_item("t", dict(x=1, y=1, z=1)))

def test_human_gate_waits_then_resumes(tmp_path):
    wf = make(tmp_path, human=True); it = wf.new_item("t", dict(x=1, y=1, z=1))
    assert wf.run_chain(it) is None and it["status"] == "waiting at GATE" and [c[0] for c in chain(it)] == ["a", "b"]
    assert wf.decide(it["id"], True, "lgtm") is True and chain(it)[-2:] == [("gate", True), ("c", True)] and "lgtm" in it["chain"][-2]["reason"]
    it2 = wf.new_item("t2", dict(x=1, y=1, z=1)); wf.run_chain(it2)
    assert wf.decide(it2["id"], False) is False and it2["status"] == "blocked at GATE"
    with pytest.raises(ValueError): wf.decide(it2["id"], True)

def test_human_auto_approve_setting(tmp_path):
    wf = make(tmp_path, human=True); wf.cfg.data["settings"]["gate_auto_approve"] = True
    assert wf.run_chain(wf.new_item("t", dict(x=1, y=1, z=1))) is True

def test_items_persist_across_restart(tmp_path):
    wf = make(tmp_path, human=True); it = wf.new_item("t", dict(x=1, y=1, z=1)); wf.run_chain(it)
    wf2 = make(tmp_path, human=True); assert wf2.items[0]["pending"] == 2 and wf2.decide(it["id"], True) is True
    assert wf2.new_item("n")["id"] > it["id"]

def test_chief_hold_blocks_cycle(tmp_path, ai_says):
    ai_says("hold"); wf = make(tmp_path); wf.cfg.data["seats"]["chief"]["provider"] = "xai"
    wf.submit(data=dict(x=1, y=1, z=1)); wf.run_cycle()
    assert wf.items[0]["status"] == "blocked at A" and "CHIEF" in wf.items[0]["chain"][0]["reason"]
    assert any(e["kind"] == "HOLD" for e in wf.events)

def test_cycle_and_snapshot(tmp_path):
    wf = make(tmp_path); wf.submit(data=dict(x=1, y=1, z=1)); wf.submit(data=dict(x=0)); wf.run_cycle()
    s = wf.snapshot(); assert s["cycle"] == 1 and [i["status"] for i in s["items"]] == ["blocked at A", "done"]
    assert set(s["seats"]) == {"chief", "a", "b", "c"} and s["runner"]["interval"] == 300
    d = wf.definition(); assert d["chain"] == ["a", "b", "c"] and d["seats"][2]["block_labels"] == ["flag"]

def test_runner_manual_mode(tmp_path):
    wf = make(tmp_path); wf.cfg.data["auto_run"] = False; wf.cfg.data["run_interval_sec"] = 0.05
    Runner(wf).start(); time.sleep(0.2); assert wf.cycle_no == 0
    wf.wake.set(); time.sleep(0.2); assert wf.cycle_no == 1; wf.stop.set(); wf.wake.set()

def test_config_validation(tmp_path):
    c = Config(tmp_path / "c.yaml", base_defaults(["a"]))
    for bad in [{"language": "xx"}, {"seats": {"nope": {"provider": "rules"}}}, {"seats": {"a": {"provider": "nope"}}}, {"bogus": 1}]:
        with pytest.raises(ValueError): c.update(bad)
    c.update({"seats": {"a": {"provider": "ollama"}}, "language": "ja"}); c2 = Config(c.path, base_defaults(["a"]))
    assert c2["seats"]["a"]["provider"] == "ollama" and c2["language"] == "ja" and "KEY" not in c.path.read_text(encoding="utf-8")

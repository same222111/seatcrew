"""'Idea != trigger': every seat in the chain can stop an order, and a block stops everything after it."""
import pytest
from tradecrew import seats as E, providers as P
from tradecrew.config import Config

CHAIN = ["scan", "judge", "risk", "size", "fills", "review"]

@pytest.fixture
def crew(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(E, "session", lambda *a: "regular"); monkeypatch.setattr(E, "fractional_ok", lambda *a: True)
    P.BUDGET.__init__(); c = E.Crew(cfg, tmp_path / "st"); c.px = {"AAA": 100.0}; c.stats = {"AAA": dict(chg=0.5, ret5=2)}; return c

def order(crew, side="buy", dollars=50.0, px=100.0):
    b = crew.broker("trend_rsi2"); b.roll_day(crew.px)
    return dict(id=1, portfolio="trend_rsi2", label="Test", sym="AAA", side=side, dollars=dollars, px=px, sess="regular",
                why="unit test", equity=b.equity(crew.px), broker=b, ts="t")

def seats_run(o): return [c["seat"] for c in o["chain"]]

def test_all_ok_fills(crew):
    o = order(crew); assert crew.run_chain(o) and seats_run(o) == CHAIN and all(c["ok"] for c in o["chain"])
    assert crew.broker("trend_rsi2").p["pos"]["AAA"] > 0

@pytest.mark.parametrize("seat,setup,expect", [
    ("scan", lambda c, o: o.update(px=None), "no fresh price"),
    ("judge", lambda c, o: c.stats["AAA"].update(chg=-7.0), "falling knife"),
    ("risk", lambda c, o: c.cfg.data["risk"].update(kill_switch=True), "kill switch"),
    ("risk", lambda c, o: o.update(sess="closed"), "market closed"),
    ("risk", lambda c, o: o["broker"].p.update(orders_today=99), "orders/day"),
    ("size", lambda c, o: o.update(dollars=0.5), "too small"),
])
def test_single_point_block_stops_order(crew, seat, setup, expect):
    o = order(crew); setup(crew, o)
    assert crew.run_chain(o) is False
    assert seats_run(o) == CHAIN[: CHAIN.index(seat) + 1]          # nothing after the blocking seat ran
    last = o["chain"][-1]; assert not last["ok"] and expect in last["reason"] and o["status"] == f"blocked at {seat.upper()}"
    assert not crew.broker("trend_rsi2").p["pos"]                   # no position was opened
    assert any(e["kind"] == "CHECK_BLOCKED" and e["agent"] == seat.upper() for e in crew.events)

def test_size_whole_shares_off_hours(crew, monkeypatch):
    monkeypatch.setattr(E, "fractional_ok", lambda *a: False); o = order(crew, dollars=50, px=100)
    assert not crew.run_chain(o) and o["chain"][-1]["seat"] == "size" and "whole shares" in o["chain"][-1]["reason"]

def test_review_blocks_and_reverts_bad_fill(crew, monkeypatch):
    monkeypatch.setitem(E.SLIPPAGE, "regular", 0.05)   # fill far worse than review's tolerance (2 x 0.0005 recorded at order time)
    o = order(crew); real = E.SLIPPAGE["regular"]
    monkeypatch.setattr(E.Review, "check", lambda self, o: (o["broker"].revert(o["trade"]), (False, "slippage too high -> paper fill reverted"))[1])
    cash0 = o["broker"].p["cash"]
    assert not crew.run_chain(o) and seats_run(o) == CHAIN and not o["chain"][-1]["ok"]
    assert not o["broker"].p["pos"] and abs(o["broker"].p["cash"] - cash0) < 1e-6 and o["broker"].p["trades"] == []

def test_review_real_rule_detects_slippage(crew):
    o = order(crew); b = o["broker"]
    o["trade"] = b.fill("AAA", 0.4, 110.0, "regular", "bad fill")   # filled 10% above the idea price
    o["qty"] = 0.4; ok, why = crew.review.check(o)
    assert not ok and "slippage" in why and "AAA" not in b.p["pos"]

def ai_says(monkeypatch, label):
    monkeypatch.setenv("XAI_API_KEY", "k")
    monkeypatch.setattr(P, "_post", lambda *a: {"choices": [{"message": {"content": '{"label":"%s","reason":"because"}' % label}}]})

@pytest.mark.parametrize("seat,label", [("judge", "reject"), ("risk", "veto"), ("fills", "wait"), ("review", "flag")])
def test_ai_seat_can_block(crew, monkeypatch, seat, label):
    ai_says(monkeypatch, label); crew.cfg.data["seats"][seat]["provider"] = "xai"
    o = order(crew); assert not crew.run_chain(o) and o["chain"][-1]["seat"] == seat
    assert not crew.broker("trend_rsi2").p["pos"]

def test_ai_failure_never_blocks(crew, monkeypatch):
    def boom(*a): raise P.LLMError("HTTP 500")
    monkeypatch.setenv("XAI_API_KEY", "k"); monkeypatch.setattr(P, "_post", boom)
    for s in CHAIN: crew.cfg.data["seats"][s]["provider"] = "xai"
    assert crew.run_chain(order(crew))

def test_exits_skip_judge_and_risk_limits(crew):
    crew.run_chain(order(crew)); crew.cfg.data["risk"]["kill_switch"] = True
    o = order(crew, side="sell", dollars=-50); o["id"] = 2
    assert crew.run_chain(o) and "AAA" not in crew.broker("trend_rsi2").p["pos"]

def test_chief_hold_blocks_buys_only(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(E, "session", lambda *a: "regular"); monkeypatch.setattr(E, "fractional_ok", lambda *a: True)
    ai_says(monkeypatch, "hold"); P.BUDGET.__init__(); cfg.data["seats"]["chief"]["provider"] = "xai"
    c = E.Crew(cfg, tmp_path / "h"); c.run_cycle()
    assert any(e["kind"] == "HOLD" for e in c.events) and not any(e["kind"] == "CHECK_OK" and e["agent"] == "FILLS" for e in c.events)
    assert all(o["chain"][-1]["seat"] == "judge" and "CHIEF" in o["chain"][-1]["reason"] for o in c.orders if o["side"] == "buy")

def test_quant_dial_scales_size(crew):
    crew.dial_level = "defensive"; o = order(crew, dollars=80); assert crew.run_chain(o)
    assert abs(o["trade"]["qty"] * o["px"] - 20) < 0.5           # 80 x 0.25

def test_quant_manual_override(crew):
    import pandas as pd
    crew.cfg.data["risk_dial"] = "cautious"; assert crew.quant.dial(pd.DataFrame({"QQQ": range(1, 300)})) == "cautious"

def test_legacy_roles_config_migrates(tmp_path):
    f = tmp_path / "c.yaml"; f.write_text("roles:\n  news: {provider: gemini}\n  sizer: {provider: openai}\n")
    c = Config(f); assert c["seats"]["stocks"]["provider"] == "gemini" and c["seats"]["size"]["provider"] == "openai" and "roles" not in c.data

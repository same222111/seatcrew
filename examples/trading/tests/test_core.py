import datetime as dt, json, threading, urllib.request, pytest
from zoneinfo import ZoneInfo
from tradecrew import broker as B, seats as E, providers as P
from tradecrew.backtest import backtest, research
from tradecrew.config import Config
from tradecrew.strategies import STRATEGIES
NY = ZoneInfo("America/New_York")

def test_config_roundtrip_and_validation(cfg, tmp_path):
    cfg.update({"watchlist": ["aapl", " msft "], "seats": {"stocks": {"provider": "gemini", "model": "gemini-2.0-flash"}}})
    c2 = Config(cfg.path); assert c2["watchlist"] == ["AAPL", "MSFT"] and c2["seats"]["stocks"]["provider"] == "gemini"
    assert "API_KEY=" not in cfg.path.read_text()
    for bad in [{"capital": -1}, {"watchlist": []}, {"seats": {"risk": {"provider": "nope"}}}, {"language": "xx"}, {"broker": {"mode": "live"}}, {"bogus": 1}]:
        with pytest.raises(ValueError): cfg.update(bad)

@pytest.mark.parametrize("t,s", [((2026, 10, 28, 10), "regular"), ((2026, 10, 28, 8), "pre"), ((2026, 10, 28, 17), "after"),
                                 ((2026, 10, 28, 23), "overnight"), ((2026, 10, 31, 12), "closed"), ((2026, 11, 1, 21), "overnight")])
def test_sessions(t, s): assert B.session(dt.datetime(*t, tzinfo=NY)) == s

def test_live_broker_disabled():
    with pytest.raises(NotImplementedError): B.LiveBroker()

@pytest.mark.parametrize("name", STRATEGIES)
def test_backtest_each_strategy(name, cfg):
    r = backtest(name, cfg.data, years=3); assert r["full"] and r["test"] and r["benchmark"]["symbol"] == "QQQ" and len(r["equity"]) > 10

def test_research_loop(cfg):
    logs = []; r = research("trend_rsi2", cfg.data, rounds=2, years=3, log=lambda *a: logs.append(a))
    assert len(r["rounds"]) == 2 and {a[0] for a in logs} == {"PROPOSER", "VALIDATOR"}

def run_cycle(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(E, "session", lambda *a: "regular"); monkeypatch.setattr(E, "fractional_ok", lambda *a: True)
    t = E.Crew(cfg, tmp_path / "state"); t.run_cycle(); return t

def test_paper_cycle_rules_only(cfg, tmp_path, monkeypatch):
    t = run_cycle(cfg, tmp_path, monkeypatch); snap = t.snapshot()
    assert set(snap["portfolios"]) == set(STRATEGIES)
    fills = [e for e in t.events if e["kind"] == "CHECK_OK" and e["agent"] == "FILLS"]; assert fills, [e["msg"] for e in t.events]
    assert all(p["equity"] > 0 for p in snap["portfolios"].values())
    assert any(e["kind"] == "CHECK_OK" and e["agent"] == "REVIEW" for e in t.events)
    filled = [o for o in t.orders if o["status"] == "filled"]
    assert filled and all([c["seat"] for c in o["chain"]] == ["scan", "judge", "risk", "size", "fills", "review"] for o in filled)

def test_kill_switch_blocks_buys(cfg, tmp_path, monkeypatch):
    cfg.update({"risk": {"kill_switch": True}}); t = run_cycle(cfg, tmp_path, monkeypatch)
    assert not [e for e in t.events if e["kind"] == "CHECK_OK" and e["agent"] == "FILLS"] and any(e["kind"] == "CHECK_BLOCKED" and e["agent"] == "RISK" and "kill switch" in e["msg"] for e in t.events)

def test_ai_risk_veto_respected(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "k"); P.BUDGET.__init__()
    monkeypatch.setattr(P, "_post", lambda *a: {"choices": [{"message": {"content": '{"label":"veto","reason":"test veto"}'}}]})
    cfg.update({"seats": {"risk": {"provider": "xai"}}}); t = run_cycle(cfg, tmp_path, monkeypatch)
    assert any(e["kind"] == "CHECK_BLOCKED" and "veto" in e["msg"] for e in t.events) and not [e for e in t.events if e["kind"] == "CHECK_OK" and e["agent"] == "FILLS"]
    assert any("[xai/" in e["msg"] for e in t.events)

def test_closed_market_queues(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(E, "session", lambda *a: "closed"); t = E.Crew(cfg, tmp_path / "s"); t.run_cycle()
    assert any(e["kind"] == "CHECK_BLOCKED" and "closed" in e["msg"] for e in t.events) and not [e for e in t.events if e["kind"] == "CHECK_OK" and e["agent"] == "FILLS"]

def test_http_api(cfg, tmp_path, monkeypatch):
    from tradecrew.server import serve
    t = E.Crew(cfg, tmp_path / "s"); srv = serve(cfg, t, port=0); threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    def call(p, body=None):
        req = urllib.request.Request(base + p, json.dumps(body).encode() if body is not None else None, {"Content-Type": "application/json"})
        try: return json.loads(urllib.request.urlopen(req).read())
        except urllib.error.HTTPError as e: return json.loads(e.read())
    assert "<title>TradeCrew" in urllib.request.urlopen(base + "/").read().decode()
    m = call("/api/config"); assert "keys" in m and all(isinstance(v, bool) for v in m["keys"].values())
    assert call("/api/config", {"watchlist": ["TSLA"]})["ok"] and Config(cfg.path)["watchlist"] == ["TSLA"]
    assert call("/api/config", {"capital": 0})["ok"] is False
    r = call("/api/test-connection", {"provider": "deepseek"}); assert r["ok"] is False and "DEEPSEEK_API_KEY" in r["error"]
    assert call("/api/locale/ja")["nav_dash"] == "ダッシュボード" and call("/api/locale/..%2Fconfig")["nav_dash"] == "Dashboard"
    assert call("/api/config", {"language": "zh-CN"})["ok"] and Config(cfg.path)["language"] == "zh-CN"
    assert call("/api/state")["session"] in ("regular", "pre", "after", "overnight", "closed"); srv.shutdown()

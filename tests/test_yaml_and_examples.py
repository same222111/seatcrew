"""YAML workflows, the bundled examples, scaffolding, CLI and the generic HTTP API."""
import json, threading, urllib.request
from pathlib import Path
import pytest
from seatcrew import loader, i18n
from seatcrew.cli import main
from seatcrew.server import serve

@pytest.fixture
def chdir(tmp_path, monkeypatch): monkeypatch.chdir(tmp_path); return tmp_path

def run(wf, yes=False):
    wf.run_cycle()
    if yes:
        for it in [i for i in wf.items if "pending" in i]: wf.decide(it["id"], True)
    return {i["title"][:20]: i for i in wf.items}

def test_support_triage_yaml(chdir):
    wf = loader.build("support_triage"); items = run(wf)
    card = next(i for i in wf.items if "4111" in i["data"]["message"]); assert card["status"] == "blocked at PRIVACY"
    ok = next(i for i in wf.items if i["data"]["customer"] == "Ana")
    assert ok["data"]["category"] == "billing" and ok["status"] == "waiting at APPROVE" and "Ana" in ok["data"]["reply"]
    assert wf.decide(ok["id"], True) is True and ok["chain"][-1]["seat"] == "review"

def test_yaml_ai_block(chdir, ai_says):
    ai_says("escalate"); wf = loader.build("support_triage"); wf.cfg.data["seats"]["intake"]["provider"] = "xai"; run(wf)
    assert all(i["status"] == "blocked at INTAKE" and "AI escalate" in i["chain"][-1]["reason"] for i in wf.items)

def test_yaml_submit_and_rules(chdir):
    wf = loader.build("support_triage"); wf.cfg.data["settings"]["approve_auto_approve"] = True
    it = wf.submit(data=dict(customer="Dee", message="I'm locked out, password: hunter2")); run(wf)
    assert it["status"] == "blocked at PRIVACY" and "password" in it["chain"][-1]["reason"]
    it = wf.submit(data=dict(customer="Eve", message="")); run(wf); assert it["status"] == "blocked at INTAKE"

def test_content_review_rules_only(chdir):
    wf = loader.build("content_review"); run(wf, yes=True); st = {i["data"]["topic"]: i["status"] for i in wf.items}
    assert st == {"Why we test in staging": "done", "Our new pricing": "blocked at POLICY", "Benchmark results": "blocked at FACTCHECK", "Team offsite recap": "done"}
    done = next(i for i in wf.items if i["status"] == "done"); assert Path(done["data"]["published_path"]).read_text(encoding="utf-8") == done["data"]["draft"]

def test_content_review_human_reject_and_review_unpublish(chdir):
    wf = loader.build("content_review"); run(wf); w = [i for i in wf.items if "pending" in i]
    assert len(w) == 2 and wf.decide(w[0]["id"], False, "off-brand") is False and "off-brand" in w[0]["chain"][-1]["reason"]
    wf.seat_map["review"].rules = lambda it: (False, "replay mismatch"); assert wf.decide(w[1]["id"], True) is False
    assert "unpublished" in w[1]["chain"][-1]["reason"] and not Path(w[1]["data"]["published_path"]).exists()

def test_content_review_with_ai(chdir, monkeypatch):
    calls = []
    def fake(url, h, body, timeout):
        sys_p = body["messages"][0]["content"]; calls.append(sys_p[:12])
        if "Reply ONLY with JSON" not in sys_p: return {"choices": [{"message": {"content": "# AI post\n\n" + "Plain words only. " * 20}}]}
        lab = "violation" if "POLICY" in sys_p else "supported" if "FACTCHECK" in sys_p else "ok"
        return {"choices": [{"message": {"content": json.dumps({"label": lab, "reason": "mock"})}}]}
    monkeypatch.setenv("XAI_API_KEY", "k"); monkeypatch.setattr("seatcrew.llm._post", fake)
    wf = loader.build("content_review")
    for s in ("draft", "factcheck", "policy"): wf.cfg.data["seats"][s]["provider"] = "xai"
    run(wf); assert all(i["status"] == "blocked at POLICY" and "AI violation" in i["chain"][-1]["reason"] for i in wf.items)
    assert all(i["data"]["draft"].startswith("# AI post") for i in wf.items) and calls

def test_trading_via_framework(chdir, monkeypatch):
    from tradecrew import seats as E
    monkeypatch.setattr(E, "session", lambda *a: "regular"); monkeypatch.setattr(E, "fractional_ok", lambda *a: True)
    wf = loader.build("trading"); wf.cfg.data["data"]["price_source"] = "demo"; wf.cfg.data["data"]["news"] = []
    wf.run_cycle(); s = wf.snapshot(); d = wf.definition()
    assert d["chain"] == ["scan", "judge", "risk", "size", "fills", "review"] and len(d["seats"]) == 9
    assert s["items"] and all("broker" not in i for i in s["items"]) and s["panels"][0]["rows"]
    assert any(i["status"] == "filled" for i in s["items"])

@pytest.mark.parametrize("py", [False, True])
def test_scaffold_new_then_run(chdir, capsys, py):
    assert main(["new", "expense_ok"] + (["--python"] if py else [])) == 0
    f = chdir / "workflows/expense_ok" / ("workflow.py" if py else "workflow.yaml"); assert f.exists()
    assert main(["new", "expense_ok"] + (["--python"] if py else [])) == 1
    assert main(["run", "workflows/expense_ok", "--yes"] if not py else ["run", str(f), "--yes", "--json"]) == 0
    out = capsys.readouterr().out; assert ("passed" in out) if not py else ("[]" in out or "chain" in out)

def test_cli_run_translated(chdir, capsys):
    assert main(["--lang", "ja", "run", "support_triage"]) == 0
    assert "承認待ち" in capsys.readouterr().out

def test_http_api(chdir):
    wf = loader.build("content_review"); srv = serve(wf, "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start()
    U = f"http://127.0.0.1:{srv.server_address[1]}"
    def call(p, body=None):
        r = urllib.request.Request(U + p, json.dumps(body).encode() if body is not None else None, {"Content-Type": "application/json"})
        try: return json.loads(urllib.request.urlopen(r).read())
        except urllib.error.HTTPError as e: return json.loads(e.read())
    c = call("/api/config"); assert c["definition"]["chain"][0] == "draft" and "keys" in c and all(isinstance(v, bool) for v in c["keys"].values())
    assert call("/api/submit", {"data": {"topic": "Hello", "notes": "x " * 40}})["ok"]; wf.run_cycle()
    it = next(i for i in call("/api/state")["items"] if i["title"] == "Hello"); assert it["pending"] == 3
    assert call("/api/decide", {"id": it["id"], "approve": True})["result"] is True
    assert call("/api/decide", {"id": it["id"], "approve": True})["ok"] is False
    assert call("/api/config", {"language": "zh-TW", "interval": 60, "settings": {"min_words": 10}})["ok"] and wf.cfg["run_interval_sec"] == 60
    assert call("/api/config", {"seats": {"draft": {"provider": "nope"}}})["ok"] is False
    assert call("/api/locale/zh-CN")["seat_draft"] == "撰写草稿" and call("/api/locale/..%2F..%2Fpyproject")["nav_dash"] == "Dashboard"
    assert b"SeatCrew" in urllib.request.urlopen(U + "/").read(); srv.shutdown()

def test_core_locales_complete():
    import re
    en = json.loads((i18n.CORE / "en.json").read_text(encoding="utf-8"))
    html = (Path(i18n.CORE).parent / "web/index.html").read_text(encoding="utf-8")
    used = set(re.findall(r'data-i18n="(\w+)"', html)) | {k for k in re.findall(r"\bT\('(\w+)'", html)}
    assert used <= set(en), used - set(en)
    for f in i18n.CORE.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8")); assert set(d) == set(en), f.name
        for k, v in en.items(): assert set(re.findall(r"\{(\w+)\}", v)) == set(re.findall(r"\{(\w+)\}", d[k])), (f.name, k)
    cr = loader.examples_dir() / "content_review/locales"
    assert all(set(json.loads(f.read_text(encoding="utf-8"))) == set(json.loads((cr / "en.json").read_text(encoding="utf-8"))) for f in cr.glob("*.json"))

import copy, json, urllib.request
import pytest
from seatcrew import llm, assistant
from seatcrew.assistant import Assistant
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from test_desktop_install import app, get, post  # noqa: F401

class Cfg:
    def __init__(self):
        self.defaults = {"display": {"theme": "dark", "simple": True}, "broker": {"mode": "paper"}, "seats": {}}
        self.data = copy.deepcopy(self.defaults)
    def validate(self, d):
        if d["display"]["theme"] not in ("dark", "light"): raise ValueError("bad theme")
    def update(self, p): self.data = assistant.merge(self.data, p)

def mk(tmp_path, **kw):
    c = Cfg(); return Assistant(tmp_path / "chat.json", lang=lambda: "en", config=c, cfg=lambda: c.data, wf_dir=tmp_path / "wfs", **kw), c

def llm_returns(monkeypatch, obj):
    monkeypatch.setenv("XAI_API_KEY", "k")
    monkeypatch.setattr(llm, "_post", lambda *a: {"choices": [{"message": {"content": json.dumps(obj)}}]})

def test_offline_faq_and_who_decides(tmp_path):
    a, _ = mk(tmp_path); assert a.status()["offline"] and a.provider() is None
    r = a.send("hello, what is this app?"); assert r["offline"] and r["messages"][-1]["role"] == "chief"
    r = a.send("who decides?"); assert r["messages"][-1]["tool"] == "who_decides"

def test_create_workflow_needs_confirm_and_cancel_works(tmp_path):
    a, _ = mk(tmp_path)
    m = a.send("create a workflow that reviews blog posts")["messages"][-1]
    assert m["kind"] == "proposal" and m["status"] == "pending" and not (tmp_path / "wfs").exists()
    assert a.confirm(m["id"], True)["status"] == "applied"
    assert len(list((tmp_path / "wfs").glob("*/workflow.yaml"))) == 1
    with pytest.raises(ValueError): a.confirm(m["id"], True)
    m2 = a.send("create a workflow for invoices")["messages"][-1]
    assert a.confirm(m2["id"], False)["status"] == "cancelled" and len(list((tmp_path / "wfs").iterdir())) == 1

def test_set_config_from_mocked_ai_shows_diff_and_waits(tmp_path, monkeypatch):
    a, c = mk(tmp_path)
    llm_returns(monkeypatch, {"reply": "Switching to light.", "tool": "set_config", "args": {"patch": {"display": {"theme": "light"}}}})
    m = a.send("make it light")["messages"][-1]
    assert m["proposal"]["diff"] == [{"path": "display.theme", "old": "dark", "new": "light"}] and c.data["display"]["theme"] == "dark"
    a.confirm(m["id"], True); assert c.data["display"]["theme"] == "light"

def test_blocked_patch_and_secrets_refused(tmp_path, monkeypatch):
    a, c = mk(tmp_path)
    llm_returns(monkeypatch, {"reply": "ok", "tool": "set_config", "args": {"patch": {"broker": {"mode": "live"}}}})
    m = a.send("go live")["messages"][-1]; assert m["kind"] == "warn" and c.data["broker"]["mode"] == "paper"
    a2, _ = mk(tmp_path / "b")
    r = a2.send("my key is sk-abcdefghijklmnopqrstuvwxyz123456 OPENAI_API_KEY=sk-zzzzzzzzzzzzzzzzzzzzzz")
    assert any(x.get("kind") == "warn" for x in r["messages"])
    saved = (tmp_path / "b" / "chat.json").read_text(encoding="utf-8")
    assert "abcdefghijklmnop" not in saved and "zzzzzzzzzzzz" not in saved and "abcdefghijklmnop" not in json.dumps(r)

def test_prompt_never_contains_key_values(tmp_path, monkeypatch):
    a, _ = mk(tmp_path); seen = []
    monkeypatch.setenv("XAI_API_KEY", "secret-value-123")
    monkeypatch.setattr(llm, "_post", lambda u, h, b, t: seen.append(json.dumps(b)) or {"choices": [{"message": {"content": '{"reply":"hi"}'}}]})
    assert a.send("hi")["messages"][-1]["text"] == "hi" and seen and "secret-value-123" not in seen[0]

def test_clear(tmp_path):
    a, _ = mk(tmp_path); a.send("hi"); a.clear()
    assert a.status()["history"] == [] and json.loads((tmp_path / "chat.json").read_text()) == []

def test_launcher_chat_test_connection_and_modes(app):
    assert "ChiefChat" in get(app.url + "chat.js") and "chat.js" in get(app.url)
    code, r = post(app.url + "api/test-connection", {"provider": "openai", "api_key": "sk-test-999"})
    assert code == 200 and r["ok"] is False and "sk-test-999" not in json.dumps(r)
    assert not (app.home / ".env").exists() or "sk-test-999" not in (app.home / ".env").read_text()
    assert post(app.url + "api/setup", {"language": "en", "mode": "bogus"})[0] == 400
    code, r = post(app.url + "api/setup", {"language": "en", "mode": "demo"}); assert r["ai_mode"] == "demo"
    code, r = post(app.url + "api/chat", {"message": "who decides?"}); assert code == 200 and r["offline"]

def test_dashboards_serve_chat(app):
    url = post(app.url + "api/open", {"workflow": "support_triage"})[1]["url"].split("?")[0]
    assert "chat.js" in get(url) and "ChiefChat" in get(url + "chat.js") and "CHAT_FULL" in get(url + "chat")
    code, r = post(url + "api/chat", {"message": "run a sample"}); assert r["messages"][-1]["kind"] == "proposal"

def test_tradecrew_page_has_chat():
    from pathlib import Path
    assert "/chat.js" in (Path(__file__).parent.parent / "examples/trading/tradecrew/web/index.html").read_text(encoding="utf-8")

def test_display_simple_default_and_validated():
    from seatcrew import profiles as C
    assert C.DISPLAY_DEFAULTS["simple"] is True
    with pytest.raises(ValueError): C.validate_display(dict(C.DISPLAY_DEFAULTS, simple="yes"))

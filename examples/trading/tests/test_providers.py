import json, pytest
from tradecrew import providers as P

class Spy:
    def __init__(self, resp): self.resp, self.calls = resp, []
    def __call__(self, url, headers, body, timeout): self.calls.append((url, headers, body)); return self.resp

OPENAI = {"choices": [{"message": {"content": "pong"}}]}
CASES = {
    "openai": ("OPENAI_API_KEY", OPENAI, "api.openai.com/v1/chat/completions", "Authorization"),
    "xai": ("XAI_API_KEY", OPENAI, "api.x.ai/v1/chat/completions", "Authorization"),
    "deepseek": ("DEEPSEEK_API_KEY", OPENAI, "api.deepseek.com/v1/chat/completions", "Authorization"),
    "anthropic": ("ANTHROPIC_API_KEY", {"content": [{"type": "text", "text": "pong"}]}, "api.anthropic.com/v1/messages", "x-api-key"),
    "gemini": ("GEMINI_API_KEY", {"candidates": [{"content": {"parts": [{"text": "pong"}]}}]}, "generativelanguage.googleapis.com", "x-goog-api-key"),
    "ollama": (None, {"message": {"content": "pong"}}, "localhost:11434/api/chat", None),
    "custom": (None, OPENAI, "localhost:1234/v1/chat/completions", None),
}

@pytest.mark.parametrize("name", CASES)
def test_each_provider_shape(name, cfg, monkeypatch):
    env, resp, url, hdr = CASES[name]
    if env: monkeypatch.setenv(env, "sk-test-SECRET123456789")
    spy = Spy(resp); monkeypatch.setattr(P, "_post", spy)
    r = P.test_connection(name, cfg.data)
    assert r["ok"] and r["reply"] == "pong", r
    u, h, b = spy.calls[0]; assert url in u
    if hdr: assert hdr in h
    assert "SECRET" not in json.dumps(r) and "SECRET" not in u   # key never in URL or result

def test_custom_base_url_and_model(cfg, monkeypatch):
    spy = Spy(OPENAI); monkeypatch.setattr(P, "_post", spy)
    cfg.update({"providers": {"custom": {"base_url": "https://openrouter.ai/api/v1", "model": "meta/llama"}}})
    r = P.test_connection("custom", cfg.data); assert r["ok"] and r["model"] == "meta/llama"
    assert spy.calls[0][0] == "https://openrouter.ai/api/v1/chat/completions" and spy.calls[0][2]["model"] == "meta/llama"

def test_missing_key_is_clear_error(cfg):
    r = P.test_connection("openai", cfg.data); assert not r["ok"] and "OPENAI_API_KEY" in r["error"]

def test_http_error_is_scrubbed(cfg, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abcdefghijklmnop")
    def boom(*a): raise P.LLMError(P._scrub("HTTP 401: invalid key sk-abcdefghijklmnop"))
    monkeypatch.setattr(P, "_post", boom)
    r = P.test_connection("openai", cfg.data); assert not r["ok"] and "401" in r["error"] and "abcdefghijklmnop" not in r["error"]

def test_real_http_path_against_local_server(cfg):
    """Exercise the real urllib path against a local OpenAI-compatible fake server."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["messages"][-1]["role"] == "user"
            out = json.dumps(OPENAI).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)
    s = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start()
    cfg.update({"providers": {"custom": {"base_url": f"http://127.0.0.1:{s.server_port}/v1"}}})
    assert P.test_connection("custom", cfg.data)["ok"]; s.shutdown()

def test_unreachable_endpoint(cfg):
    cfg.update({"providers": {"ollama": {"base_url": "http://127.0.0.1:9"}}})
    r = P.test_connection("ollama", cfg.data); assert not r["ok"] and "connection failed" in r["error"]

def test_ask_role_rules_only_and_assigned(cfg, monkeypatch):
    assert P.ask_role("risk", "x", ["approve", "veto"], cfg.data) is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(P, "_post", Spy({"content": [{"text": '{"label":"veto","reason":"earnings tomorrow"}'}]}))
    cfg.update({"seats": {"risk": {"provider": "anthropic", "model": "claude-x"}}})
    o = P.ask_role("risk", "x", ["approve", "veto"], cfg.data); assert o["ok"] and o["label"] == "veto" and o["model"] == "claude-x"

def test_ask_role_garbage_abstains(cfg, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k"); monkeypatch.setattr(P, "_post", Spy({"choices": [{"message": {"content": "maybe?"}}]}))
    cfg.update({"seats": {"stocks": {"provider": "openai"}}})
    assert P.ask_role("stocks", "x", ["bullish", "bearish"], cfg.data)["ok"] is False

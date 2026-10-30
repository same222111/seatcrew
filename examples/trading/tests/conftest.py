import pytest
from tradecrew.config import Config

@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY", "CUSTOM_API_KEY"]: monkeypatch.delenv(k, raising=False)
    c = Config(tmp_path / "config.yaml"); c.data["data"]["price_source"] = "demo"
    c.data["data"]["news"] = []; c.data["scan_interval_sec"] = 3600; return c

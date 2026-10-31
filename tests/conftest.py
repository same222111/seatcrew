import os, sys
from pathlib import Path
# test this checkout's examples (tradecrew), not whatever copy the venv has installed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples" / "trading"))
import pytest
from seatcrew import llm

@pytest.fixture(autouse=True)
def isolated_cli_accounts(monkeypatch):
    """Only test-provided fake CLIs may run, never the developer's logged-in CLI."""
    from seatcrew import cli_ai
    for tool in cli_ai.TOOLS:
        monkeypatch.delenv(f"SEATCREW_{tool.upper()}_BIN", raising=False)
    for key in ("SEATCREW_CHAT_PROVIDER", "SEATCREW_DEMO"):
        monkeypatch.delenv(key, raising=False)
    def fake_only(tool):
        path = os.getenv(f"SEATCREW_{tool.upper()}_BIN")
        return path if path and Path(path).is_file() else None
    monkeypatch.setattr(cli_ai, "which", fake_only)
    cli_ai._cache.clear()
    yield
    cli_ai._cache.clear()

@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    from seatcrew.video import providers
    keys = {p["key_env"] for p in llm.PROVIDERS.values() if p["key_env"]}
    keys.update(key for entry in providers.CATALOG for key in entry["env"])
    keys.add("STABILITY_API_KEY")
    for key in keys: monkeypatch.delenv(key, raising=False)
    def offline(*args, **kwargs): raise llm.LLMError("HTTP disabled in offline tests; provide a mock")
    monkeypatch.setattr(llm, "_post", offline)
    llm.BUDGET.__init__()

@pytest.fixture
def ai_says(monkeypatch):
    """ai_says('flag') -> every AI call returns that label."""
    def set_(label):
        monkeypatch.setenv("XAI_API_KEY", "k")
        monkeypatch.setattr(llm, "_post", lambda *a: {"choices": [{"message": {"content": '{"label":"%s","reason":"because"}' % label}}]})
    return set_

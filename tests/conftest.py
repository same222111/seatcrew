import pytest
from seatcrew import llm

@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY", "CUSTOM_API_KEY", "ELEVENLABS_API_KEY", "REPLICATE_API_TOKEN", "STABILITY_API_KEY"]: monkeypatch.delenv(k, raising=False)
    llm.BUDGET.__init__()

@pytest.fixture
def ai_says(monkeypatch):
    """ai_says('flag') -> every AI call returns that label."""
    def set_(label):
        monkeypatch.setenv("XAI_API_KEY", "k")
        monkeypatch.setattr(llm, "_post", lambda *a: {"choices": [{"message": {"content": '{"label":"%s","reason":"because"}' % label}}]})
    return set_

import json, re
from pathlib import Path
from tradecrew import i18n
from tradecrew.config import LANGUAGES, SEATS
from tradecrew.cli import main
ROOT = Path(__file__).resolve().parent.parent / "tradecrew"

def test_every_language_has_every_key():
    en = json.loads((ROOT / "locales/en.json").read_text())
    for code in LANGUAGES:
        loc = json.loads((ROOT / f"locales/{code}.json").read_text(encoding="utf-8"))
        assert set(loc) == set(en), (code, set(en) ^ set(loc))
        for k, v in en.items(): assert set(re.findall(r"\{(\w+)\}", v)) == set(re.findall(r"\{(\w+)\}", loc[k])), (code, k)

def test_all_ui_keys_exist():
    html = (ROOT / "web/index.html").read_text(); en = i18n.load("en")
    keys = set(re.findall(r'data-i18n="(\w+)"', html)) | {k for k in re.findall(r"\bT\('(\w+)'", html) if not k.endswith('_')} | {f"seat_{s}" for s in SEATS}
    assert keys and not (keys - set(en)), keys - set(en)

def test_fallback_and_format():
    assert i18n.t("cli_dashboard", "es", url="X").startswith("Panel: X") and i18n.t("nope", "ja") == "nope"

def test_cli_translated(tmp_path, capsys, monkeypatch):
    for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY"]: monkeypatch.delenv(k, raising=False)
    assert main(["--config", str(tmp_path / "c.yaml"), "--env", str(tmp_path / "none"), "--lang", "zh-CN", "test-ai"]) == 1
    assert "没有找到任何 Key" in capsys.readouterr().out

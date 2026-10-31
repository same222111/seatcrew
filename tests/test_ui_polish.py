"""v0.9.3 polish: translated model cards, pasted keys, zero-key samples, and a real-browser overflow check."""
import json, os, shutil, urllib.error, urllib.request
from pathlib import Path
import pytest
from seatcrew import desktop
from seatcrew.video import providers as PV

HERE = Path(__file__).resolve().parent

def get(url):
    with urllib.request.urlopen(url, timeout=10) as r: return json.loads(r.read())

def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for e in PV.CATALOG:
        for v in e["env"]: monkeypatch.delenv(v, raising=False)
    a = desktop.App(tmp_path / "home").start(); yield a
    if a.launcher.socket.fileno() != -1: a.stop()

def test_every_catalog_entry_is_translated():
    t = PV.i18n()
    for lang in ("zh-CN", "zh-TW", "ja", "es"):
        missing = [e["id"] for e in PV.CATALOG if not (t["good_at"].get(e["id"]) or {}).get(lang)]
        assert not missing, (lang, missing)

def test_paste_key_is_validated_and_never_echoed(app):
    i = next(e["id"] for e in PV.CATALOG if PV.key_var(e["id"]))
    assert post(app.url + "api/models/key", {"id": "nope", "value": "abcdefgh123"})[0] == 400
    assert post(app.url + "api/models/key", {"id": i, "value": "short"})[0] == 400
    assert post(app.url + "api/models/key", {"id": i, "value": "has space inside"})[0] == 400
    code, r = post(app.url + "api/models/key", {"id": i, "value": "test-key-0123456789"})
    try:
        assert code == 200 and r["ok"] and "test-key-0123456789" not in json.dumps(r)
        assert f"{PV.key_var(i)}=test-key-0123456789" in (app.home / ".env").read_text(encoding="utf-8")
    finally: os.environ.pop(PV.key_var(i), None)

def test_language_pref_is_saved(app):
    assert post(app.url + "api/prefs", {"language": "zh-CN"})[0] == 200
    assert json.loads((app.home / "desktop.json").read_text(encoding="utf-8"))["language"] == "zh-CN"
    assert post(app.url + "api/prefs", {"language": "xx"})[0] == 400

def test_zero_key_sample_is_in_ui_language():
    from seatcrew.assistant import sample_for
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("sv_wf", HERE.parent / "examples" / "short_video" / "workflow.py")
    m = importlib.util.module_from_spec(spec); sys.modules["sv_wf"] = m; spec.loader.exec_module(m)
    wf = type("W", (), {"spec": {"sample_items": m.SAMPLES}})()
    assert "天空" in sample_for(wf, "zh-CN")["topic"] and "lang" not in sample_for(wf, "zh-CN")
    assert sample_for(wf, "fr")["topic"].startswith("Why")
    zh = next(s for s in m.SAMPLES if s.get("lang") == "zh-CN")
    assert len(m.sentences(zh["notes"])) == 5                 # CJK sentences split without spaces
    assert "天空" in zh["topic"]

def _chrome():
    """System Chrome/Chromium path, "bundled" for Playwright's own Chromium, else None (test skipped - CI sets
    SEATCREW_REQUIRE_UI=1 so a missing browser fails there instead)."""
    try: from playwright.sync_api import sync_playwright
    except ImportError: return None
    sys_c = next((p for p in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser") if os.path.exists(p)), None) or shutil.which("google-chrome")
    if sys_c: return sys_c
    try:
        with sync_playwright() as p: return "bundled" if os.path.exists(p.chromium.executable_path) else None
    except Exception: return None

@pytest.mark.skipif(not _chrome() and not os.environ.get("SEATCREW_REQUIRE_UI"), reason="needs playwright + a Chrome/Chromium")
def test_no_clipped_text_or_horizontal_overflow(app):
    from playwright.sync_api import sync_playwright
    post(app.url + "api/setup", {"language": "zh-CN"})
    js = (HERE / "ui" / "overflow.js").read_text(encoding="utf-8"); bad = []
    with sync_playwright() as p:
        c = _chrome(); b = p.chromium.launch(**({} if c == "bundled" else dict(executable_path=c)), args=["--no-sandbox"])
        for w, h in ((1280, 800), (1440, 900), (1920, 1080)):
            pg = b.new_page(viewport=dict(width=w, height=h)); pg.goto(app.url); pg.wait_for_timeout(800)
            bad += [(w, x) for x in pg.evaluate(js)]
            pg.close()
        print("ui overflow checked with", c)
        b.close()
    assert not bad, bad[:10]

def test_almost_json_from_a_small_model_abstains_or_parses(monkeypatch):
    from seatcrew import llm
    cfg = {"seats": {"x": {"provider": "ollama", "prompt": "p", "model": "m"}}, "llm_limits": {"max_calls_per_hour": 99, "cost_per_call_usd": 0, "max_daily_usd": 1}}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: ('{"label": "hold" "reason": "broken json"}', "m"))
    r = llm.ask_role("x", "u", ("proceed", "hold"), cfg); assert r["label"] == "hold" and r["ok"]
    monkeypatch.setattr(llm, "chat", lambda *a, **k: ("{not json at all}", "m"))
    assert llm.ask_role("x", "u", ("proceed", "hold"), cfg)["label"] == "abstain"

def test_ollama_default_model_falls_back_to_an_installed_one(monkeypatch):
    from seatcrew import llm
    llm._OL["http://x"] = (__import__("time").time(), ["qwen2.5:0.5b"])
    assert llm.ollama_model("http://x", llm.PROVIDERS["ollama"]["model"]) == "qwen2.5:0.5b"
    assert llm.ollama_model("http://x", "mine:7b") == "mine:7b"

@pytest.mark.parametrize("data", [{"settings": "x"}, {"seats": "x"}, {"settings": {"crf": "abc"}}, {"settings": {"allow_draft": "yes"}}])
def test_malformed_profile_is_a_clean_error(data):
    from seatcrew import profiles as PF
    class C: defaults = {"settings": {"crf": 18, "allow_draft": True}, "seats": {"a": {}}}; data = defaults
    with pytest.raises(ValueError): PF.clean(C, data)

def test_every_python_package_ships_in_the_wheel():
    import re
    root = HERE.parent; txt = (root / "pyproject.toml").read_text(encoding="utf-8")
    pkgs = set(re.findall(r'"([\w.]+)"', re.search(r"^packages = \[(.*)\]", txt, re.M).group(1)))
    for init in (root / "seatcrew").rglob("__init__.py"):
        assert ".".join(init.parent.relative_to(root).parts) in pkgs, f"{init.parent} missing from pyproject packages"

def test_still_image_static_camera_is_not_frozen():
    from seatcrew.video.editor import _kb
    assert _kb("static", 100, 0.1)[0] != "1"

def test_character_without_choice_gets_voice_by_gender_age(tmp_path):
    from seatcrew.video import characters as CH, voices as VO
    st = CH.Store(root=tmp_path / "c", casts=tmp_path / "k", voices=tmp_path / "v.yaml")
    st.create("老张", "x", "male", "adult", ""); st.create("小美", "x", "female", "young", "")
    a, b = st.bind_voice("老张")[1], st.bind_voice("小美")[1]
    assert a["gender"] == "male" and b["gender"] == "female" and a["voice"] != b["voice"]


def test_setup_renderer_in_every_language():
    """The asynchronous detection renderer must not resolve #lang as a JS function."""
    import subprocess
    node = os.environ.get('SEATCREW_TEST_NODE') or shutil.which('node')
    if not node:
        if os.environ.get('CI'): pytest.fail('Node is required for the setup renderer regression test')
        pytest.skip('Node is needed for the setup renderer regression test')
    subprocess.run([node, str(HERE / 'ui' / 'setup.cjs'), str(HERE.parent / 'seatcrew' / 'web' / 'setup.js')], check=True)

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
    try: import playwright.sync_api  # noqa
    except ImportError: return None
    return next((p for p in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser") if os.path.exists(p)), None) or shutil.which("google-chrome")

@pytest.mark.skipif(not _chrome(), reason="needs playwright + a Chrome/Chromium")
def test_no_clipped_text_or_horizontal_overflow(app):
    from playwright.sync_api import sync_playwright
    post(app.url + "api/setup", {"language": "zh-CN"})
    js = (HERE / "ui" / "overflow.js").read_text(encoding="utf-8"); bad = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=_chrome(), args=["--no-sandbox"])
        for w, h in ((1280, 800), (1440, 900), (1920, 1080)):
            pg = b.new_page(viewport=dict(width=w, height=h)); pg.goto(app.url); pg.wait_for_timeout(800)
            bad += [(w, x) for x in pg.evaluate(js)]
            pg.close()
        b.close()
    assert not bad, bad[:10]

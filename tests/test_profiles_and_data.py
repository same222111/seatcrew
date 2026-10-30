"""v0.5: per-workflow profiles (save/load/reset/export/import/share code) and the choosable data folder."""
import base64, json, os, sys, urllib.request
from pathlib import Path
import pytest
from seatcrew import desktop, profiles as PF
import urllib.error
ROOT = Path(__file__).resolve().parent.parent

def get(url):
    with urllib.request.urlopen(url, timeout=5) as r: return r.read().decode()

def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

@pytest.fixture
def wf(tmp_path, monkeypatch):
    """content_review dashboard served from a desktop App (data folder = tmp)."""
    monkeypatch.chdir(tmp_path)
    a = desktop.App(tmp_path / "home").start()
    url = post(a.url + "api/open", {"workflow": "content_review"})[1]["url"]
    yield url.split("?")[0], a
    a.stop()

def test_secret_stripping_keeps_env_names():
    removed = []
    data = PF.strip_secrets({"seats": {"a": {"api_key": "x", "key_env": "OPENAI_API_KEY", "prompt": "hi sk-abcdefghijklmnopqrstu"}},
                             "token": "y", "note": "ghp_" + "a" * 30, "ok": 3}, removed=removed)
    assert data == {"seats": {"a": {"key_env": "OPENAI_API_KEY", "prompt": "hi <removed>"}}, "note": "<removed>", "ok": 3} and len(removed) == 4

def test_display_validation():
    PF.validate_display({"theme": "light", "font_size": 15, "density": "compact"})
    for bad in ({"theme": "pink"}, {"font_size": 99}, {"density": "x"}):
        with pytest.raises(ValueError): PF.validate_display({**PF.DISPLAY_DEFAULTS, **bad})

def test_profile_editor_roundtrip(wf):
    base, app = wf
    pr = json.loads(get(base + "api/profiles"))
    assert pr["profiles"] == [] and "display" in pr["current"] and "broker" not in pr["current"] and "setup_complete" not in pr["current"]
    cur = pr["current"]; cur["display"] = {"theme": "light", "font_size": 16, "density": "comfy"}
    s, r = post(base + "api/profiles/save", {"name": "My Light", "data": cur}); assert s == 200 and r["profiles"] == ["My Light"]
    f = app.home / "workflows" / "content_review" / "profiles" / "My Light.yaml"; assert f.exists()
    assert json.loads(get(base + "api/config"))["display"]["theme"] == "light"
    assert post(base + "api/profiles/reset", {})[0] == 200 and json.loads(get(base + "api/config"))["display"]["theme"] == "dark"
    assert post(base + "api/profiles/load", {"name": "My Light"})[0] == 200 and json.loads(get(base + "api/config"))["display"]["font_size"] == 16
    bad = dict(cur, display={"theme": "light", "font_size": 500, "density": "comfy"})
    assert post(base + "api/profiles/apply", {"data": bad})[0] == 400
    assert post(base + "api/profiles/save", {"name": "../evil", "data": cur})[0] == 400
    assert post(base + "api/profiles/delete", {"name": "My Light"})[1]["profiles"] == [] and not f.exists()

def test_export_share_code_and_import(wf, monkeypatch):
    base, app = wf
    cur = json.loads(get(base + "api/profiles"))["current"]
    first = next(iter(cur["seats"])); cur["seats"][first]["api_key"] = "sk-SECRETSECRETSECRET123"; cur["display"]["density"] = "compact"
    s, ex = post(base + "api/profiles/export", {"data": cur, "author": "tester"}); assert s == 200
    blob = json.dumps(ex); assert "SECRETSECRET" not in blob and ex["filename"].endswith(".seatcrew.json")
    assert ex["file"]["seatcrew_profile"] == PF.SCHEMA and ex["file"]["workflow"] == "content_review" and ex["file"]["app_version"]
    assert ex["code"].startswith("SC1.") and len(ex["code"]) < len(json.dumps(ex["file"]))
    for text in (ex["code"], json.dumps(ex["file"])):
        pv = post(base + "api/profiles/preview", {"text": text})[1]
        assert pv["ok"] and pv["author"] == "tester" and any(c["path"] == "display.density" for c in pv["changes"])
    s, r = post(base + "api/profiles/import", {"text": ex["code"], "name": "shared", "apply": True})
    assert s == 200 and r["name"] == "shared" and json.loads(get(base + "api/config"))["display"]["density"] == "compact"
    # wrong workflow / newer schema / garbage -> clear errors; older app version -> warning only
    other = dict(ex["file"], workflow="trading"); assert not post(base + "api/profiles/preview", {"text": json.dumps(other)})[1]["ok"]
    newer = dict(ex["file"], seatcrew_profile=PF.SCHEMA + 1); assert "newer" in post(base + "api/profiles/preview", {"text": json.dumps(newer)})[1]["error"].lower()
    assert not post(base + "api/profiles/preview", {"text": "SC1.@@@"})[1]["ok"]
    old = dict(ex["file"], app_version="0.1.0"); pv = post(base + "api/profiles/preview", {"text": json.dumps(old)})[1]
    assert pv["ok"] and pv["warnings"]

def test_ui_has_big_back_button_breadcrumb_and_editor():
    html = (ROOT / "seatcrew/web/index.html").read_text(encoding="utf-8")
    for s in ('id="homeBtn" class="home"', 'data-i18n="back_home"', "crumbWf", "ArrowLeft", "Escape", 'data-t="prof"', 'id="impM"', 'id="expM"', "applyDisplay"):
        assert s in html
    assert 'id="homeBtn"' in (ROOT / "examples/trading/tradecrew/web/index.html").read_text(encoding="utf-8")
    want = {"en": "← Back to home", "zh-CN": "← 返回首页", "zh-TW": "← 返回首頁", "ja": "← ホームに戻る", "es": "← Volver al inicio"}
    for c, v in want.items():
        assert json.loads((ROOT / f"seatcrew/locales/{c}.json").read_text(encoding="utf-8"))["back_home"] == v

# ---------------- data folder ----------------
@pytest.fixture
def fresh(tmp_path, monkeypatch):
    for v in ("SEATCREW_DATA_DIR", "SEATCREW_HOME"): monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(desktop, "default_dir", lambda: tmp_path / "appdata" / "SeatCrew")
    monkeypatch.chdir(tmp_path); return tmp_path

def test_data_location_precedence(fresh, monkeypatch):
    assert desktop.data_location() == (fresh / "appdata" / "SeatCrew", "default")
    ptr = fresh / "appdata" / "SeatCrew" / "location.json"; ptr.parent.mkdir(parents=True)
    ptr.write_text(json.dumps({"data_dir": str(fresh / "D")}), encoding="utf-8")
    assert desktop.data_location() == (fresh / "D", "custom")
    monkeypatch.setenv("SEATCREW_DATA_DIR", str(fresh / "E")); assert desktop.data_location() == (fresh / "E", "env")
    assert desktop.data_dir() == fresh / "E" and (fresh / "E").is_dir()

def test_portable_mode_keeps_data_next_to_exe(fresh, monkeypatch):
    exe = fresh / "SeatCrew"; exe.mkdir(); (exe / "portable.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False); monkeypatch.setattr(sys, "executable", str(exe / "SeatCrew.exe"))
    assert desktop.data_location() == (exe.resolve() / "data", "portable") and desktop.pointer_file() == exe.resolve() / "location.json"
    (exe / "portable.txt").unlink(); assert desktop.data_location()[1] == "default"

def test_change_data_folder_moves_data_and_persists_pointer(fresh):
    a = desktop.App().start()
    try:
        assert a.home == fresh / "appdata" / "SeatCrew"
        post(a.url + "api/setup", {"language": "es"}); post(a.url + "api/open", {"workflow": "content_review"})
        (a.home / "workflows" / "content_review" / "profiles").mkdir(parents=True); (a.home / "workflows" / "content_review" / "profiles" / "p.yaml").write_text("x: 1", encoding="utf-8")
        info = json.loads(get(a.url + "api/home")); assert info["data_source"] == "default"
        assert post(a.url + "api/datadir", {"path": "relative/dir", "move": True})[0] == 400
        assert post(a.url + "api/datadir", {"path": str(a.home / "inner"), "move": True})[0] == 400
        new = fresh / "D_drive" / "SeatCrewData"
        s, r = post(a.url + "api/datadir", {"path": str(new), "move": True}); assert s == 200 and r["ok"], r
        assert (new / "desktop.json").exists() and (new / "workflows/content_review/profiles/p.yaml").exists()
        assert not (fresh / "appdata" / "SeatCrew" / "desktop.json").exists()
        assert json.loads((fresh / "appdata/SeatCrew/location.json").read_text(encoding="utf-8"))["data_dir"] == str(new.resolve())
        assert desktop.data_location() == (new.resolve(), "custom") and a.home == new.resolve() and Path.cwd() == new.resolve()
        assert json.loads(get(a.url + "api/home"))["language"] == "es"          # prefs followed the data
        assert post(a.url + "api/open", {"workflow": "content_review"})[0] == 200
        s, r = post(a.url + "api/datadir", {"path": str(fresh / "appdata" / "SeatCrew"), "move": False}); assert s == 200
        assert not (fresh / "appdata/SeatCrew/location.json").exists()          # back to default -> pointer removed
    finally: a.stop()

def test_env_override_locks_change_and_home_is_masked(fresh, monkeypatch):
    monkeypatch.setenv("SEATCREW_DATA_DIR", str(fresh / "E"))
    with pytest.raises(ValueError): desktop.relocate(fresh / "E", fresh / "F", True)
    assert desktop.pretty(Path.home() / "x" / "y").startswith("~") and str(Path.home()) not in desktop.pretty(Path.home() / "x")

def test_installer_lets_user_pick_folder_without_admin():
    iss = (ROOT / "packaging/seatcrew.iss").read_text(encoding="utf-8")
    for s in ("PrivilegesRequired=lowest", "DisableDirPage=no", "UsePreviousAppDir=yes"): assert s in iss
    assert "portable.txt" in (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

def test_animations_toggle_validated_and_ui_respects_reduced_motion():
    assert PF.DISPLAY_DEFAULTS["animations"] is True
    PF.validate_display({**PF.DISPLAY_DEFAULTS, "animations": False})
    for bad in ("no", 0, None):
        with pytest.raises(ValueError): PF.validate_display({**PF.DISPLAY_DEFAULTS, "animations": bad})
    root = Path(__file__).resolve().parent.parent
    css = (root / "seatcrew/web/neon.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css and "body.noanim" in css
    for page in ("seatcrew/web/index.html", "examples/trading/tradecrew/web/index.html"):
        h = (root / page).read_text(encoding="utf-8"); assert "motionBtn" in h and "/neon.css" in h and "noanim" in h

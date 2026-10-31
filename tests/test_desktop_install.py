"""Desktop launcher (no window: --no-window/--smoke) and installer scripts (--dry-run)."""
import json, os, shutil, socket, stat, subprocess, sys, urllib.error, urllib.request
from pathlib import Path
import pytest
from seatcrew import desktop

ROOT = Path(__file__).resolve().parent.parent

def get(url):
    with urllib.request.urlopen(url, timeout=5) as r: return r.read().decode()

def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

def closed(port):
    with socket.socket() as s: return s.connect_ex(("127.0.0.1", port)) != 0

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    a = desktop.App(tmp_path / "home").start(); yield a
    if a.launcher.socket.fileno() != -1: a.stop()

def test_free_port_is_bindable():
    p = desktop.free_port()
    with socket.socket() as s: s.bind(("127.0.0.1", p))

def test_data_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SEATCREW_HOME", str(tmp_path / "x")); assert desktop.data_dir() == tmp_path / "x" and (tmp_path / "x").is_dir()

def test_first_run_lists_examples_and_serves_launcher(app):
    info = json.loads(get(app.url + "api/home"))
    assert info["first_run"] is True and {"trading", "content_review", "support_triage"} <= {w["name"] for w in info["workflows"]}
    assert "SeatCrew" in get(app.url) and urllib.request.urlopen(app.url + "icon.png").read()[:4] == b"\x89PNG"

def test_wizard_saves_language_and_key_privately(app):
    code, r = post(app.url + "api/setup", {"language": "ja", "provider": "openai", "api_key": "sk-test-123"})
    assert code == 200 and r["ok"] and "sk-test-123" not in json.dumps(r)
    env = app.home / ".env"; assert "OPENAI_API_KEY=sk-test-123" in env.read_text(encoding="utf-8")
    if os.name == "posix": assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert json.loads((app.home / "desktop.json").read_text(encoding="utf-8"))["language"] == "ja"
    assert json.loads(get(app.url + "api/home"))["first_run"] is False
    assert post(app.url + "api/setup", {"language": "xx"})[0] == 400

def test_open_workflow_starts_backend_and_stop_closes_it(app):
    post(app.url + "api/setup", {"language": "es"})
    code, r = post(app.url + "api/open", {"workflow": "content_review"})
    assert code == 200 and "?home=" + app.url in r["url"]
    base = r["url"].split("?")[0]; st = json.loads(get(base + "api/state")); assert st["workflow"] == "content_review"
    assert json.loads(get(base + "api/config"))["language"] == "es"            # wizard choice applied on first open
    assert post(app.url + "api/open", {"workflow": "content_review"})[1]["url"] == r["url"]   # reused, not a 2nd server
    assert post(app.url + "api/open", {"workflow": "../etc"})[0] == 400
    wport = int(base.rsplit(":", 1)[1].strip("/")); lport = app.launcher.server_port
    app.stop(); assert closed(wport) and closed(lport)

def test_main_smoke_without_window(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert desktop.main(["--no-window", "--smoke", "0.3", "--home", str(tmp_path / "h"), "--open", "support_triage"]) == 0
    out = capsys.readouterr().out; assert "url: http://127.0.0.1:" in out and "stopped" in out

def test_cli_app_subcommand_routes_to_desktop(monkeypatch):
    seen = {}; monkeypatch.setattr(desktop, "main", lambda argv: seen.setdefault("argv", argv) and 0)
    from seatcrew import cli
    cli.main(["app", "--no-window"]); assert seen["argv"] == ["--no-window"]

def test_gui_backend():
    assert desktop.gui_backend() in (None, "gtk", "qt")

# ---------- installers ----------
def sh(*args, home):
    env = {**os.environ, "HOME": str(home)}; env.pop("XDG_DATA_HOME", None)
    return subprocess.run(["bash", str(ROOT / "install.sh"), *args], capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)

@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="install.sh is for macOS/Linux")
@pytest.mark.parametrize("osname,shortcut", [("Linux", "Desktop/seatcrew.desktop"), ("Darwin", "Desktop/SeatCrew.app")])
def test_install_sh_dry_run_plans_everything_and_writes_nothing(tmp_path, osname, shortcut):
    r = sh("--dry-run", "--os", osname, home=tmp_path)
    assert r.returncode == 0, r.stderr
    o = r.stdout
    assert "-m venv" in o and "seatcrew[desktop] @ git+https://github.com/same222111/seatcrew.git@main" in o
    assert str(tmp_path / shortcut) in o and "shortcuts=2 dry_run=1" in o
    if osname == "Linux": assert "PyQt6-WebEngine" in o and "applications/seatcrew.desktop" in o
    else: assert "Applications/SeatCrew.app/Contents/Info.plist" in o
    assert list(tmp_path.iterdir()) == []                                      # nothing written

@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="install.sh is for macOS/Linux")
def test_install_sh_options(tmp_path):
    r = sh("--dry-run", "--no-shortcut", "--source", str(ROOT), home=tmp_path)
    assert r.returncode == 0 and "shortcuts=0" in r.stdout and f"{ROOT}[desktop]" in r.stdout
    assert sh("--bogus", home=tmp_path).returncode == 2

@pytest.mark.skipif(not (shutil.which("pwsh") or Path("/tmp/pwsh/pwsh").exists()), reason="PowerShell not installed")
def test_install_ps1_dry_run(tmp_path):
    pw = shutil.which("pwsh") or "/tmp/pwsh/pwsh"
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path / "local"), "HOME": str(tmp_path)}
    r = subprocess.run([pw, "-NoProfile", "-File", str(ROOT / "install.ps1"), "-DryRun"], capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SeatCrew.lnk" in r.stdout and "shortcuts=2 dry_run=1" in r.stdout and "pythonw.exe -m seatcrew.desktop" in r.stdout
    assert not (tmp_path / "local").exists()

def test_packaging_files_are_consistent():
    ver = __import__("seatcrew").__version__
    assert f'"CFBundleShortVersionString": "{ver}"' in (ROOT / "packaging/seatcrew.spec").read_text(encoding="utf-8")
    assert f'#define MyVersion "{ver}"' in (ROOT / "packaging/seatcrew.iss").read_text(encoding="utf-8")
    rel = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    for s in ("tags:", "windows-latest", "macos-latest", "ubuntu-", "build_appimage.sh", "seatcrew.iss", "build_macos.sh"): assert s in rel
    for f in ("icon.png", "icon.ico", "icon.icns"): assert (ROOT / "seatcrew/assets" / f).stat().st_size > 1000

def test_launcher_animation_pref_and_shared_css(app):
    assert json.loads(get(app.url + "api/home"))["animations"] is True
    assert ".nx-card" in get(app.url + "neon.css")
    assert post(app.url + "api/prefs", {"animations": "off"})[0] == 400
    code, _ = post(app.url + "api/prefs", {"animations": False}); assert code == 200
    assert json.loads(get(app.url + "api/home"))["animations"] is False
    base = post(app.url + "api/open", {"workflow": "content_review"})[1]["url"].split("?")[0]
    assert "prefers-reduced-motion" in get(base + "neon.css")


def test_local_servers_do_not_need_reverse_dns(tmp_path, monkeypatch):
    import socket
    from seatcrew import loader, server
    def dns_unavailable(*args): raise AssertionError('local startup must not wait for reverse DNS')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(socket, 'getfqdn', dns_unavailable)
    a = desktop.App(tmp_path / 'app')
    a.launcher.server_close()
    wf = loader.build('support_triage', str(tmp_path / 'cfg.yaml'), str(tmp_path / 'state'))
    srv = server.serve(wf, port=0)
    assert srv.server_port > 0 and srv.server_name == '127.0.0.1'
    srv.server_close()


def test_bundled_namespace_examples_are_loadable(tmp_path, monkeypatch):
    from types import ModuleType
    from seatcrew import loader
    bundle = ModuleType("seatcrew_examples")
    bundle.__file__ = None
    bundle.__path__ = [str(tmp_path)]
    monkeypatch.setitem(sys.modules, "seatcrew_examples", bundle)
    sample = tmp_path / "sample"
    sample.mkdir()
    (sample / "workflow.yaml").write_text("name: sample", encoding="utf-8")
    assert loader.examples_dir() == tmp_path
    assert loader.list_examples() == ["sample"]
    assert loader.find("sample") == sample / "workflow.yaml"


def test_desktop_trading_opens_full_terminal(app):
    post(app.url + "api/setup", {"mode": "demo", "language": "zh-CN"})
    code, opened = post(app.url + "api/open", {"workflow": "trading"})
    assert code == 200
    base = opened["url"].split("?")[0]
    assert 'id="lab"' in get(base)
    assert json.loads(get(base + "api/config"))["config"]["data"]["news"] == []
    assert json.loads(get(base + "api/config"))["config"]["data"]["price_source"] == "demo"

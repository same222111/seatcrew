"""First-run detection, account login through official CLIs (fake CLI scripts), local voice engines and consent."""
import json, os, stat, subprocess, sys, time, types
from pathlib import Path
import pytest
from seatcrew import cli_ai, llm, setup_detect as SD
from seatcrew.video import localvoice as LV, tts

FAKE = r'''#!/usr/bin/env python3
import sys, os, json
a = sys.argv[1:]; st = os.environ.get("FAKE_STATE", "")
if a[:1] == ["--version"]: print("fake-cli 9.9"); sys.exit(0)
if a[-1:] == ["status"]: sys.exit(0 if os.path.exists(st) else 1)
if a[:1] == ["login"] or a[:2] == ["auth", "login"]:
    print("Open \x1b[1mhttps://auth.example.com/authorize?x=1\x1b[0m")
    if "--device-auth" in a: print("Enter this one-time code: ABCD-12345")
    if a[:2] == ["auth", "login"]:
        code = sys.stdin.readline().strip(); print("got code" if code == "PASTED" else "bad code")
    open(st, "w").write("1"); print("Logged in, token sk-abcdefghijklmnop"); sys.exit(0)
if a[:1] == ["exec"]:
    out = a[a.index("-o") + 1]; prompt = sys.stdin.read()
    if not os.path.exists(st): print("401 Unauthorized", file=sys.stderr); sys.exit(1)
    open(out, "w").write("codex says: " + prompt.splitlines()[-1]); sys.exit(0)
if a[:1] == ["-p"]:
    if not os.path.exists(st): print("Not logged in · Please run /login"); sys.exit(1)
    assert "--tools" in a and "--system-prompt" in a
    print("claude says: " + sys.stdin.read().strip()); sys.exit(0)
sys.exit(2)
'''

@pytest.fixture
def fake(tmp_path, monkeypatch):
    p = tmp_path / "fakecli"; p.write_text(FAKE); p.chmod(p.stat().st_mode | stat.S_IEXEC)
    st = tmp_path / "logged"; monkeypatch.setenv("FAKE_STATE", str(st))
    for t in ("codex", "claude"): monkeypatch.setenv(f"SEATCREW_{t.upper()}_BIN", str(p))
    cli_ai._cache.clear(); yield st; cli_ai._cache.clear()

def test_status_logged_out_then_ask_raises_with_hint(fake):
    s = cli_ai.status("codex", fresh=True)
    assert s["installed"] and s["version"] == "fake-cli 9.9" and s["logged_in"] is False
    with pytest.raises(cli_ai.CLIError, match="codex login"): cli_ai.ask("codex", "sys", "hi")
    assert llm.key_status()["codex_cli"] is False

def test_not_installed_shows_install_command(monkeypatch):
    monkeypatch.setattr(cli_ai, "which", lambda t: None); cli_ai._cache.clear()
    s = cli_ai.status("claude", fresh=True); assert not s["installed"] and "npm install -g @anthropic-ai/claude-code" in s["install"]
    with pytest.raises(cli_ai.CLIError, match="not installed"): cli_ai.login("codex")
    cli_ai._cache.clear()

def wait(jid):
    for _ in range(100):
        j = cli_ai.login_job(jid)
        if j["done"]: return j
        time.sleep(0.05)
    raise AssertionError("login job did not finish")

def test_codex_device_login_relays_url_and_code_but_scrubs_tokens(fake):
    j = wait(cli_ai.login("codex", device=True)["id"])
    assert j["ok"] and j["url"].startswith("https://auth.example.com") and j["code"] == "ABCD-12345"
    assert not any("sk-abcdef" in l for l in j["lines"]) and not any("\x1b" in l for l in j["lines"])
    assert cli_ai.status("codex")["logged_in"] and llm.key_status()["codex_cli"] is True

def test_claude_login_paste_code_then_chat_through_llm(fake):
    jid = cli_ai.login("claude")["id"]; time.sleep(0.3); cli_ai.login_send(jid, "PASTED"); j = wait(jid)
    assert j["ok"] and "got code" in j["lines"]
    txt, model = llm.chat("claude_cli", "be brief", "ping", {"providers": {}, "llm_limits": {"timeout_sec": 5}})
    assert txt == "claude says: ping"
    txt, _ = llm.chat("codex_cli", "be brief", "pong", {"providers": {}, "llm_limits": {"timeout_sec": 5}})
    assert txt.startswith("codex says:")

def test_cli_provider_errors_become_llm_errors(fake):
    with pytest.raises(llm.LLMError, match="sign in"): llm.chat("codex_cli", "s", "u", {"providers": {}, "llm_limits": {}})

def test_cli_ai_never_reads_auth_files():
    src = Path(cli_ai.__file__).read_text()
    assert "auth.json" not in src and ".credentials" not in src and "keychain" not in src.lower()
    assert src.count(" open(") == 1 and "with open(outf" in src     # the only file read: the reply file in a fresh temp dir

def base_det(**kw):
    d = dict(keys={"openai": False}, cli={"codex": {"logged_in": False}, "claude": {"logged_in": False}},
             ollama={"running": False, "models": []}, gpu=None, ram_gb=16, disk_free_gb=100, edge_tts=True); d.update(kw); return d

@pytest.mark.parametrize("det,chat,mode", [
    (base_det(), None, "demo"),
    (base_det(cli={"codex": {"logged_in": False}, "claude": {"logged_in": True}}), "claude_cli", "cli"),
    (base_det(cli={"codex": {"logged_in": True}, "claude": {"logged_in": True}}), "codex_cli", "cli"),
    (base_det(keys={"openai": True}, cli={"codex": {"logged_in": True}, "claude": {"logged_in": False}}), "openai", "key"),
    (base_det(ollama={"running": True, "models": ["qwen2.5:3b"]}), "ollama", "ollama")])
def test_recommend_priority_and_zero_key_default(det, chat, mode):
    r = SD.recommend(det); assert r["chat_provider"] == chat and r["ai_mode"] == mode and r["voice"] == "edge"

def test_recommend_voice_engine_by_hardware():
    assert SD.recommend(base_det(gpu={"cuda": True, "vram_gb": 8}))["clone_device"] == "cuda"
    cpu = SD.recommend(base_det()); assert cpu["clone_device"] == "cpu" and "CPU" in cpu["warning"]
    assert SD.recommend(base_det(disk_free_gb=3))["clone_engine"] is None

def test_detect_runs_on_this_machine(tmp_path):
    d = SD.detect(tmp_path); assert d["cpu_count"] and "codex" in d["cli"] and "cosyvoice" in d["voice_engines"]
    assert all(isinstance(v, bool) for v in d["keys"].values())

def test_gpu_parses_nvidia_smi(monkeypatch):
    monkeypatch.setattr(SD.shutil, "which", lambda n: "/x/nvidia-smi" if n == "nvidia-smi" else None)
    monkeypatch.setattr(SD, "_run", lambda a, timeout=6: "NVIDIA GeForce RTX 4070, 12282\n")
    g = SD.gpu(); assert g["cuda"] and g["vram_gb"] == 12.0 and "4070" in g["name"]

# ---------------- voice engines ----------------
def test_licences_and_noncommercial_never_installable(tmp_path):
    assert LV.ENGINES["cosyvoice"]["license"] == "Apache-2.0" and LV.ENGINES["gpt_sovits"]["license"] == "MIT"
    for e in ("f5_tts", "fish_speech"):
        assert not LV.ENGINES[e]["commercial"] and "NON-COMMERCIAL" in LV.ENGINES[e]["license"]
        with pytest.raises(LV.VoiceEngineError): LV.plan(e, tmp_path)

def test_install_plan_goes_into_chosen_data_folder(tmp_path):
    data = tmp_path / "D_drive" / "SeatCrewData"; steps = LV.plan("cosyvoice", data, "cpu")
    flat = " ".join(" ".join(s) for s in steps)
    assert str(data / "voice_engines" / "cosyvoice") in flat and "whl/cpu" in flat and "CosyVoice-300M-SFT" in flat
    assert "whl/cu121" in " ".join(" ".join(s) for s in LV.plan("cosyvoice", data, "cuda"))

def test_install_job_runs_steps_and_marks_installed(tmp_path):
    calls = []
    def runner(cmd, **k): calls.append(cmd); return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    j = LV.install("cosyvoice", tmp_path, "cpu", runner=runner)
    assert "CPU" in j["warning"]
    for _ in range(100):
        if LV.job(j["id"])["done"]: break
        time.sleep(0.02)
    assert LV.job(j["id"])["ok"] and LV.status("cosyvoice", tmp_path)["installed"] and calls
    assert (tmp_path / "voice_engines" / "cosyvoice" / "seatcrew_cosy_run.py").exists()

def test_install_failure_is_reported(tmp_path):
    j = LV.install("cosyvoice", tmp_path, runner=lambda c, **k: types.SimpleNamespace(returncode=1, stdout="", stderr="boom"))
    for _ in range(100):
        if LV.job(j["id"])["done"]: break
        time.sleep(0.02)
    assert LV.job(j["id"])["ok"] is False and "boom" in LV.job(j["id"])["log"][-1]

def test_clone_requires_consent_and_transcript(tmp_path):
    wav = tmp_path / "me.wav"; wav.write_bytes(b"RIFF")
    with pytest.raises(LV.VoiceEngineError, match="consent"): LV.add_clone(tmp_path, "me", wav, "hello", consent=False)
    with pytest.raises(LV.VoiceEngineError, match="consent"): LV.add_clone(tmp_path, "me", wav, "hello", consent="yes")
    with pytest.raises(LV.VoiceEngineError, match="exactly"): LV.add_clone(tmp_path, "me", wav, " ", consent=True)
    p = LV.add_clone(tmp_path, "me", wav, "hello there", consent=True)
    assert p["consent"]["given"] and p["consent"]["date"] and LV.get_clone(tmp_path, p["id"])["wav_path"].endswith(".wav")
    f = LV.clones_dir(tmp_path) / f"{p['id']}.json"; d = json.loads(f.read_text()); d["consent"] = {}; f.write_text(json.dumps(d))
    with pytest.raises(LV.VoiceEngineError, match="consent"): LV.get_clone(tmp_path, p["id"])

def _installed(tmp_path):
    d = tmp_path / "voice_engines" / "cosyvoice"; d.mkdir(parents=True); (d / ".installed").write_text("{}"); return d

def test_cosyvoice_builtin_speaker_and_clone_requests(tmp_path):
    _installed(tmp_path); seen = []
    def runner(cmd, input=None, **k):
        req = json.loads(input); seen.append(req); Path(req["out"]).write_bytes(b"RIFF"); return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    LV.cosyvoice("你好", tmp_path / "a", lang="zh-CN", data_dir=tmp_path, runner=runner)
    assert seen[-1]["mode"] == "sft" and seen[-1]["spk"] == "中文女"
    wav = tmp_path / "me.wav"; wav.write_bytes(b"RIFF"); p = LV.add_clone(tmp_path, "me", wav, "hello", consent=True)
    LV.cosyvoice("hi", tmp_path / "b", voice="clone:" + p["id"], data_dir=tmp_path, runner=runner)
    assert seen[-1]["mode"] == "zero_shot" and seen[-1]["prompt_text"] == "hello" and "CosyVoice2" in seen[-1]["model"]

def test_cosyvoice_not_installed_is_tts_error_and_auto_never_picks_local(tmp_path, monkeypatch):
    monkeypatch.setattr(LV, "data_dir_default", lambda: tmp_path)
    with pytest.raises(tts.TTSError, match="not installed"): tts.BACKENDS["cosyvoice"]("hi", str(tmp_path / "x"))
    assert "cosyvoice" not in tts.auto_order("auto")

def test_gpt_sovits_client_posts_consented_reference(tmp_path, monkeypatch):
    wav = tmp_path / "me.wav"; wav.write_bytes(b"RIFF"); p = LV.add_clone(tmp_path, "me", wav, "你好", consent=True); sent = {}
    class R:
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def read(s): return b"RIFFDATA"
    def opener(req, timeout=0): sent.update(json.loads(req.data)); sent["url"] = req.full_url; return R()
    out = LV.gpt_sovits("hello", tmp_path / "o", voice="clone:" + p["id"], lang="ja", data_dir=tmp_path, opener=opener)
    assert Path(out).read_bytes() == b"RIFFDATA" and sent["url"].endswith(":9880/tts") and sent["text_lang"] == "ja" and sent["prompt_text"] == "你好"
    with pytest.raises(LV.VoiceEngineError, match="consented"): LV.gpt_sovits("x", tmp_path / "o", voice=None, data_dir=tmp_path)

# ---------------- desktop routes ----------------
from tests.test_desktop_install import get, post, app  # noqa: F401,E402

def test_desktop_detect_login_and_recommend_apply(app, fake):
    d = json.loads(get(app.url + "api/detect")); assert d["recommended"]["ai_mode"] in ("demo", "key", "ollama", "cli")
    assert "setup.js" in get(app.url) and "Log in with ChatGPT" in get(app.url + "setup.js")
    code, r = post(app.url + "api/recommend-apply", {"provider": "codex_cli"}); assert code == 400 and "log in" in r["error"]
    code, j = post(app.url + "api/cli-login", {"tool": "codex", "device": True}); assert code == 200
    j = wait(j["id"]); assert json.loads(get(app.url + "api/cli-login/" + j["id"]))["ok"]
    cli_ai._cache.clear()
    code, r = post(app.url + "api/recommend-apply", {"provider": "codex_cli"}); assert code == 200 and r["ai_mode"] == "cli"
    assert os.environ["SEATCREW_CHAT_PROVIDER"] == "codex_cli"
    code, r = post(app.url + "api/cli-login", {"tool": "rm -rf"}); assert code == 400

def test_desktop_voice_engines_and_clone_consent(app, tmp_path):
    v = json.loads(get(app.url + "api/voice-engines")); assert v["engines"]["cosyvoice"]["path"].startswith(str(app.home))
    wav = tmp_path / "v.wav"; wav.write_bytes(b"RIFF")
    code, r = post(app.url + "api/voice-clone", {"name": "me", "wav_path": str(wav), "transcript": "hi"}); assert code == 400 and "consent" in r["error"]
    code, r = post(app.url + "api/voice-clone", {"name": "me", "wav_path": str(wav), "transcript": "hi", "consent": True}); assert code == 200 and r["id"]
    code, r = post(app.url + "api/voice-engine/plan", {"engine": "f5_tts"}); assert code == 400 and "NON-COMMERCIAL" in r["error"]

"""Character Studio: image / 3D / lip-sync adapters (mocked HTTP), characters + casts store, export/import without keys,
continuity QC on synthetic clips, dialogue template, cast-aware workflow, server routes, CHIEF intents, CLI."""
import base64, json, shutil, struct, subprocess, threading
from pathlib import Path
from urllib.request import urlopen, Request
import pytest
from seatcrew import loader
from seatcrew.video import providers as PV, imagegen as IG, model3d as M3, lipsync as LS, characters as CH, continuity as CT, qc as QC, voices as VO
from seatcrew.video import storyboard as SB, templates as TP

class Fake:
    def __init__(self, routes): self.routes = [[m, u, list(r)] for m, u, r in routes]; self.calls = []
    def __call__(self, method, url, headers, data, timeout):
        self.calls.append(dict(method=method, url=url, headers=headers, data=data))
        for r in self.routes:
            if r[0] == method and r[1] in url:
                st, body = r[2].pop(0) if len(r[2]) > 1 else r[2][0]
                return st, (body if isinstance(body, bytes) else json.dumps(body).encode()), "application/json"
        raise AssertionError(f"unexpected {method} {url}")
    def body(self, i): return json.loads(self.calls[i]["data"])

FF = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg not installed")
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==") + b"\0" * 200
GLB = b"glTF" + struct.pack("<II", 2, 300) + b"\0" * 300
KEYS = ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "MINIMAX_API_KEY", "REPLICATE_API_TOKEN", "MESHY_API_KEY", "TRIPO_API_KEY", "KLING_API_KEY", "SEATCREW_PUBLIC_MEDIA_URL")

@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in KEYS: monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    def use(routes, **keys):
        for k, v in keys.items(): monkeypatch.setenv(k, v)
        f = Fake(routes); monkeypatch.setattr(PV, "_send", f); return f
    return use

def img(tmp_path, name="ref.png"):
    p = tmp_path / name; p.write_bytes(PNG); return p

# ---------- image adapters
def test_openai_image_edits_with_refs(env, tmp_path):
    f = env([("POST", "/v1/images/edits", [(200, {"data": [{"b64_json": base64.b64encode(PNG).decode()}]})])], OPENAI_API_KEY="sk-test-xxxxxxxxxxxxxxxx")
    p, info = IG.generate("front view", tmp_path / "o.png", [img(tmp_path), img(tmp_path, "b.png")], "1:1", "openai")
    assert p.read_bytes() == PNG and info["backend"] == "openai" and info["refs"] == 2
    c = f.calls[0]; assert c["data"].count(b'name="image[]"') == 2 and b"gpt-image-1" in c["data"] and c["headers"]["Authorization"].startswith("Bearer ")

def test_openai_image_generations_without_refs(env, tmp_path):
    f = env([("POST", "/v1/images/generations", [(200, {"data": [{"b64_json": base64.b64encode(PNG).decode()}]})])], OPENAI_API_KEY="sk-x")
    IG.generate("a nurse", tmp_path / "o.png", [], "2:3", "openai"); assert f.body(0)["size"] == "1024x1536"

def test_gemini_image_multi_ref(env, tmp_path):
    f = env([("POST", "gemini-nano-banana-2.1:generateContent", [(200, {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(PNG).decode()}}]}}]})])], GEMINI_API_KEY="g")
    IG.generate("side", tmp_path / "o.png", [img(tmp_path, f"r{i}.png") for i in range(6)], "16:9", "gemini")
    b = f.body(0); parts = b["contents"][0]["parts"]
    assert sum("inline_data" in p for p in parts) == 4 and b["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9" and f.calls[0]["headers"]["x-goog-api-key"] == "g"

def test_minimax_image_subject_reference_and_error(env, tmp_path):
    env([("POST", "/v1/image_generation", [(200, {"data": {"image_base64": [base64.b64encode(PNG).decode()]}, "base_resp": {"status_code": 0}})])], MINIMAX_API_KEY="m")
    p, _ = IG.generate("x", tmp_path / "o.png", [img(tmp_path)], "1:1", "minimax"); assert p.is_file()
    f = env([("POST", "/v1/image_generation", [(200, {"base_resp": {"status_code": 1026, "status_msg": "sensitive"}})])])
    with pytest.raises(PV.ProviderError, match="sensitive"): IG.generate("x", tmp_path / "o2.png", [img(tmp_path)], "1:1", "minimax", allow_draft=False)
    assert f.body(0)["subject_reference"][0]["type"] == "character"

def test_replicate_image_polls(env, tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    env([("POST", "/models/black-forest-labs/flux-kontext-pro/predictions", [(201, {"status": "starting", "urls": {"get": "https://api.replicate.com/v1/predictions/p1"}})]),
         ("GET", "/v1/predictions/p1", [(200, {"status": "processing", "urls": {"get": "https://api.replicate.com/v1/predictions/p1"}}), (200, {"status": "succeeded", "output": "https://cdn/x.png"})]),
         ("GET", "https://cdn/x.png", [(200, PNG)])], REPLICATE_API_TOKEN="r8_test")
    p, info = IG.generate("x", tmp_path / "o.png", [img(tmp_path)], "1:1", "replicate"); assert p.read_bytes() == PNG and info["backend"] == "replicate"

@FF
def test_image_draft_fallback_is_labeled(env, tmp_path):
    p, info = IG.generate("x", tmp_path / "front.png", [], "1:1", "auto"); assert info["draft"] and p.stat().st_size > 1000
    with pytest.raises(PV.ProviderError): IG.generate("x", tmp_path / "f2.png", [], "1:1", "auto", allow_draft=False)

# ---------- 3D
def test_meshy_tripo_replicate_3d(env, tmp_path):
    env([("POST", "/openapi/v1/image-to-3d", [(200, {"result": "t1"})]), ("GET", "/image-to-3d/t1", [(200, {"status": "IN_PROGRESS"}), (200, {"status": "SUCCEEDED", "model_urls": {"glb": "https://m/x.glb"}})]),
         ("GET", "https://m/x.glb", [(200, GLB)])], MESHY_API_KEY="msy")
    p, info = M3.make(img(tmp_path), tmp_path / "m.glb", "meshy"); assert p.read_bytes()[:4] == b"glTF" and info["backend"] == "meshy"
    f = env([("POST", "/v3/files", [(200, {"code": 0, "data": {"file_token": "ft"}})]), ("POST", "/v3/generation/image-to-model", [(200, {"code": 0, "data": {"task_id": "k"}})]),
             ("GET", "/v3/tasks/k", [(200, {"data": {"status": "success", "output": {"pbr_model": "https://t/x.glb"}}})]), ("GET", "https://t/x.glb", [(200, GLB)])], TRIPO_API_KEY="tsk")
    M3.make(img(tmp_path), tmp_path / "t.glb", "tripo"); assert f.body(1) == {"input": "ft"}
    f = env([("POST", "/models/firtoz/trellis/predictions", [(201, {"status": "starting", "urls": {"get": "https://api.replicate.com/v1/predictions/z"}})]),
             ("GET", "/predictions/z", [(200, {"status": "succeeded", "output": {"model_file": "https://r/x.glb"}})]), ("GET", "https://r/x.glb", [(200, GLB)])], REPLICATE_API_TOKEN="r8")
    M3.make(img(tmp_path), tmp_path / "r.glb", "replicate"); assert f.body(0)["input"]["images"][0].startswith("data:image/png;base64,")

def test_3d_rejects_non_glb_and_standee_is_valid(env, tmp_path):
    env([("POST", "/openapi/v1/image-to-3d", [(200, {"result": "t1"})]), ("GET", "/image-to-3d/t1", [(200, {"status": "SUCCEEDED", "model_urls": {"glb": "https://m/x.glb"}})]),
         ("GET", "https://m/x.glb", [(200, b"<html>" * 50)])], MESHY_API_KEY="msy")
    with pytest.raises(PV.ProviderError, match="not a GLB"): M3.make(img(tmp_path), tmp_path / "m.glb", "meshy", allow_draft=False)
    p, info = M3.make(img(tmp_path), tmp_path / "s.glb", "auto"); b = p.read_bytes()
    assert info["backend"] == "draft" and b[:4] == b"glTF" and struct.unpack("<I", b[8:12])[0] == len(b)
    jl = struct.unpack("<I", b[12:16])[0]; g = json.loads(b[20:20 + jl]); assert g["asset"]["version"] == "2.0" and g["materials"][0]["doubleSided"]

# ---------- lip-sync
def test_lipsync_replicate_and_kling(env, tmp_path, monkeypatch):
    v = tmp_path / "c.mp4"; v.write_bytes(b"\0" * 500); a = tmp_path / "l.mp3"; a.write_bytes(b"ID3" + b"\0" * 300)
    f = env([("POST", "/models/sync/lipsync-2/predictions", [(201, {"status": "succeeded", "output": "https://r/o.mp4"})]), ("GET", "https://r/o.mp4", [(200, b"MP4" * 100)])], REPLICATE_API_TOKEN="r8")
    p, info = LS.apply(v, a, tmp_path / "o.mp4", "replicate"); assert info["lipsync"] == "replicate" and p.read_bytes().startswith(b"MP4")
    b = f.body(0)["input"]; assert b["video"].startswith("data:video/mp4;base64,") and b["audio"].startswith("data:audio/")
    monkeypatch.setattr("seatcrew.video.ff.duration", lambda p: 3.5); monkeypatch.setattr(LS.Kling, "poll_every", 0)
    f = env([("POST", "/v1/videos/identify-face", [(200, {"code": 0, "data": {"session_id": "s", "face_data": [{"face_id": 7}]}})]),
             ("POST", "/v1/videos/advanced-lip-sync", [(200, {"code": 0, "data": {"task_id": "T"}})]),
             ("GET", "/advanced-lip-sync/T", [(200, {"data": {"task_status": "processing"}}), (200, {"data": {"task_status": "succeed", "task_result": {"videos": [{"url": "https://k/o.mp4"}]}}})]),
             ("GET", "https://k/o.mp4", [(200, b"MP4" * 100)])], KLING_API_KEY="k")
    p, info = LS.apply(v, a, tmp_path / "k.mp4", "kling", video_url="https://example.org/c.mp4")
    assert info["lipsync"] == "kling", info; fc = f.body(1)["face_choose"][0]; assert fc["face_id"] == "7" and fc["sound_end_time"] == 3500

def test_lipsync_none_or_failure_keeps_clip(env, tmp_path):
    v = tmp_path / "c.mp4"; v.write_bytes(b"x")
    assert LS.apply(v, v, tmp_path / "o.mp4", "none")[1]["lipsync"] == "none"
    p, info = LS.apply(v, v, tmp_path / "o.mp4", "kling"); assert p == v and info["lipsync"] == "failed" and "public video URL" in info["error"] or "KLING" in info["error"]

# ---------- characters + casts
def store(tmp_path): return CH.Store(tmp_path / "characters", tmp_path / "casts", tmp_path / "voices" / "characters.yaml")

@FF
def test_character_create_sheet_lock_voice(env, tmp_path):
    st = store(tmp_path); c = st.create("林晚", "28, short bob, beige trench coat", "female", "young", "quick-tempered", [img(tmp_path)])
    assert c["refs"] == ["refs/ref.png"] and not c["locked"]
    with pytest.raises(ValueError): st.create("林晚", "dup")
    with pytest.raises(ValueError): st.create("x", "")
    with pytest.raises(ValueError): st.create("../evil", "d")
    c, info = st.make_sheet("林晚", "draft", expressions=("happy",))
    assert set(c["sheet"]) == {"front", "side", "full", "expressions"} and c["sheet_draft"] and all((st.path("林晚") / v).is_file() for v in ("sheet/front.png", "sheet/expr_happy.png"))
    st.bind_voice("林晚", preset="zh-CN/young_female_lively"); c = st.lock("林晚")
    assert c["locked"] and c["locked_refs"][:3] == ["sheet/front.png", "sheet/side.png", "sheet/full.png"]
    assert st.lib().get("林晚")["ref_image"].endswith("front.png")
    assert st.file("林晚", "../../casts/x.yaml") is None and st.file("林晚", "sheet/front.png")
    c = st.save_angle("林晚", 90, "data:image/png;base64," + base64.b64encode(PNG).decode()); assert c["angles"] == ["angles/angle_090.png"]
    c, i3 = st.make_3d("林晚", "draft"); assert c["model3d"] == "model.glb" and i3["backend"] == "draft"
    assert st.lock("林晚", unlock=True)["locked"] is False

def test_cast_rules_export_import_no_keys(env, tmp_path, monkeypatch):
    st = store(tmp_path)
    for n in ("A", "B", "C", "D", "E", "F"): st.create(n, f"{n} desc", refs=[img(tmp_path)])
    st.bind_voice("A", preset="en/narrator_female" if any(p["id"] == "en/narrator_female" for p in VO.presets("en")) else None)
    with pytest.raises(ValueError, match="at most 5"): st.save_cast("Big", ["A", "B", "C", "D", "E", "F"])
    with pytest.raises(ValueError): st.save_cast("Bad", ["A", "Nobody"])
    with pytest.raises(ValueError): st.save_cast("Dup", ["A", "A"])
    sheet = img(tmp_path, "set.png")
    c = st.save_cast("Family", [dict(character="A", role="lead", notes="sk-ABCDEFGHIJKLMNOPQRSTUV leaked"), "B"], plot="dinner", set_sheet=str(sheet))
    assert c["members"][1]["role"] == "supporting" and "sk-ABC" not in st.cast_path("Family").read_text()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-REALKEYREALKEYREALKEY")
    doc = st.export_cast("Family"); txt = json.dumps(doc)
    assert "sk-REAL" not in txt and str(tmp_path) not in txt and doc["images_included"] and "refs/ref.png" in doc["characters"][0]["images"]
    assert set(st.cast_refs(st.cast("Family"))) == {"A", "B"}
    st2 = CH.Store(tmp_path / "c2", tmp_path / "k2", tmp_path / "v2.yaml"); st2.import_cast(txt)
    assert st2.cast("Family")["members"][0]["character"] == "A" and (st2.path("A") / "refs" / "ref.png").read_bytes() == PNG
    evil = json.loads(txt); evil["characters"][0]["images"] = {"../../pwn.png": base64.b64encode(PNG).decode(), "refs/x.sh": "eA=="}
    evil["characters"][0]["character"]["name"] = "Z"; evil["cast"]["members"] = [dict(character="Z")]
    st2.import_cast(evil); assert not (tmp_path / "pwn.png").exists() and not list((tmp_path / "c2").rglob("x.sh"))
    with pytest.raises(ValueError): st2.import_cast({"hello": 1})
    lite = st.export_cast("Family", images=False); assert not lite["characters"][0]["images"] and lite["set_sheet_image"] is None

# ---------- storyboard + template
def test_storyboard_characters_and_dialogue_template():
    sb = SB.validate_storyboard({"aspect": "16:9", "shots": [{"lines": [{"speaker": "A", "text": "Hi."}], "characters": "A, B", "shot_type": "ots"}]})
    assert sb["shots"][0]["characters"] == ["A", "B"] and sb["shots"][0]["shot_type"] == "ots"
    with pytest.raises(ValueError): SB.validate_storyboard({"shots": [{"narration": "x", "characters": list("abcdef")}]})
    t = TP.TEMPLATES["dialogue_scene"]
    assert t["aspect"] == "16:9" and t["transition"] == "cut" and t["no_music"] and t["room_tone_db"] < -30 and t["needs_cast"]

# ---------- continuity on synthetic clips
def _clip(path, vf, d=2.0):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=320x180:d={d}:r=24", "-vf", vf, "-pix_fmt", "yuv420p", str(path)], check=True)

@FF
def test_continuity_flags_vanishing_prop_and_glitch(tmp_path):
    good = tmp_path / "good.mp4"; _clip(good, "drawbox=x=100:y=40:w=80:h=80:color=red:t=fill,boxblur=1")
    still = tmp_path / "still.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=320x180:d=2:r=24", "-vf",
                    "drawbox=x=40:y=40:w=80:h=100:color=0xd0a080:t=fill,drawbox=x=200:y=60:w=60:h=60:color=red:t=fill:enable='lt(t,1)'", "-pix_fmt", "yuv420p", str(still)], check=True)
    r = {c["name"]: c for c in CT.analyse(still, [dict(id="s07", start=0, dur=2.0)])}
    assert not r["local_change"]["ok"] and "s07" in r["local_change"]["detail"] and r["local_change"]["severity"] == "warn"
    r = {c["name"]: c for c in CT.analyse(still, [dict(id="s07", start=0, dur=2.0)], thresholds=dict(drift=0.95))}
    assert not r["shot_drift"]["ok"] and "s07" in r["shot_drift"]["detail"]
    glitch = tmp_path / "glitch.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=320x180:d=3:r=24", "-vf",
                    "drawbox=x=0:y=0:w=320:h=180:color=white:t=fill:enable='between(t,1.4,1.7)'", "-pix_fmt", "yuv420p", str(glitch)], check=True)
    r = {c["name"]: c for c in CT.analyse(glitch, [dict(id="s02", start=0, dur=3.0)])}
    assert not r["glitch_jump"]["ok"] and "s02" in r["glitch_jump"]["detail"]
    calm = tmp_path / "calm.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=320x180:d=2:r=24", "-vf", "drawbox=x=40:y=40:w=80:h=100:color=0xd0a080:t=fill", "-pix_fmt", "yuv420p", str(calm)], check=True)
    r = {c["name"]: c for c in CT.analyse(calm, [dict(id="s01", start=0, dur=2.0)])}
    assert r["shot_drift"]["ok"] and r["glitch_jump"]["ok"] and r["local_change"]["ok"] and r["character_consistency"]["severity"] == "info"

@FF
def test_continuity_refs_set_sheet_and_external_qc(tmp_path):
    v = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=320x180:d=4:r=24", "-f", "lavfi", "-i", "sine=f=300:d=4", "-vf",
                    "drawbox=x=40:y=40:w=80:h=100:color=0xd0a080:t=fill", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(v)], check=True)
    same = tmp_path / "same.png"; subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(v), "-frames:v", "1", str(same)], check=True)
    other = tmp_path / "other.png"; subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xff00ff:s=320x180", "-frames:v", "1", str(other)], check=True)
    sb = {"shots": [dict(id="s01", duration=2, characters=["A"]), dict(id="s02", duration=2, characters=["B"])]}
    rep = QC.check_external(v, sb, {"A": [str(same)], "B": [str(other)]}, str(other))
    by = {c["name"]: c for c in rep["checks"]}
    assert "s02:B" in by["character_consistency"]["detail"] and "s01:A" not in by["character_consistency"]["detail"]
    assert by["character_consistency"]["severity"] in ("warn", "fail") and not by["set_continuity"]["ok"]
    assert by["voice_present"]["ok"] and by["format"]["ok"]

# ---------- workflow with a cast
TINY = dict(supersample=1, preset="ultrafast", inter_crf=23)
def _cast(tmp_path):
    st = CH.Store()
    for n, p in (("Mia", "zh-CN/young_female_lively"), ("Leo", "zh-CN/young_male")):
        st.create(n, f"{n} desc", refs=[img(tmp_path, f"{n}.png")]); st.bind_voice(n, preset=p); st.lock(n)
    st.save_cast("Duo", [dict(character="Mia", role="lead"), dict(character="Leo", role="comic")], plot="Mia: Where were you?\nLeo: Buying mooncakes.\nMia: All night?")
    return st

def wf_(tmp_path, **s):
    wf = loader.build("short_video", str(tmp_path / "config.yaml"), str(tmp_path / "state"))
    wf.cfg.data["settings"].update(dict(tts_backend="mock", visuals_backend="mock", allow_draft=False), **s)
    wf.size_override = (320, 180); wf.editor_opts = dict(TINY); wf.qc_total = (1, 200); wf.qc_opts = dict(min_sharpness=0.0, continuity_thresholds=dict(identity=0.0, set=0.0, drift=0.0, jump=0.0, glitch=999))
    return wf

@FF
def test_cast_workflow_dialogue_scene(env, tmp_path):
    _cast(tmp_path); wf = wf_(tmp_path)
    it = wf.submit(data=dict(topic="Mid-Autumn", cast="Duo", template="dialogue_scene")); wf.run_cycle(); it = next(i for i in wf.items if i["id"] == it["id"])
    d = it["data"]; sb = d["storyboard"]
    assert d["aspect"] == "16:9" and [l["speaker"] for s in sb["shots"] for l in s["lines"]] == ["Mia", "Leo", "Mia"], [c["reason"] for c in it["chain"]]
    assert sb["shots"][0]["shot_type"] == "wide" and set(sb["shots"][0]["characters"]) == {"Mia", "Leo"} and all(s["transition"] == "cut" for s in sb["shots"])
    assert "pending" in it, [c["reason"] for c in it["chain"]]
    names = {c["name"] for c in d["qc"]["checks"]}; assert {"character_consistency", "shot_drift", "glitch_jump", "set_continuity", "stray_text", "local_change"} <= names
    lip = it["data"]["steps"]["lipsync"]; assert "off" in lip["reason"]

@FF
def test_scriptcheck_rejects_speaker_outside_cast(env, tmp_path, monkeypatch):
    _cast(tmp_path); wf = wf_(tmp_path, max_rewrites=0)
    W = next(s for s in wf.chain if s.name == "writer")
    monkeypatch.setattr(type(W), "ai_write", lambda self, d, tp, fb: (SB.validate_storyboard(dict(aspect="16:9", shots=[dict(lines=[dict(speaker="Stranger", text="Hello there.")], duration=2)])), "x"))
    it = wf.submit(data=dict(topic="t", cast="Duo", template="dialogue_scene")); wf.run_cycle(); it = next(i for i in wf.items if i["id"] == it["id"])
    assert any("not in the cast: Stranger" in c["reason"] for c in it["chain"])

def test_dialogue_template_needs_cast(env, tmp_path):
    wf = wf_(tmp_path); it = wf.submit(data=dict(topic="t", template="dialogue_scene")); wf.run_cycle()
    it = next(i for i in wf.items if i["id"] == it["id"]); assert any("needs a cast" in c["reason"] for c in it["chain"])

@FF
def test_lipsync_seat_uses_backend_and_keeps_wide(env, tmp_path, monkeypatch):
    _cast(tmp_path); wf = wf_(tmp_path, lipsync_backend="replicate"); calls = []
    def fake(video, audio, out, pref="none", video_url=None):
        calls.append(Path(video).name); shutil.copy(video, out); return Path(out), dict(lipsync=pref)
    monkeypatch.setattr(LS, "apply", fake)
    it = wf.submit(data=dict(topic="t", cast="Duo", template="dialogue_scene")); wf.run_cycle(); it = next(i for i in wf.items if i["id"] == it["id"])
    lip = it["data"]["steps"]["lipsync"]
    # mock visuals give still keyframes (nothing to lip-sync) -> 0 synced, originals kept; video clips go through LS.apply
    assert lip["ok"] and "replicate: synced 0" in lip["reason"] and calls == []
    sb = {"shots": [dict(id="s01", audio=__file__, clip_path=str(tmp_path / "a.mp4"), shot_type="close"), dict(id="s02", audio=__file__, clip_path=str(tmp_path / "b.mp4"), shot_type="wide")]}
    (tmp_path / "a.mp4").write_bytes(b"x"); (tmp_path / "b.mp4").write_bytes(b"x")
    seat = wf.steps["lipsync"]; ok, why = seat.rules(dict(id=99, data=dict(storyboard=sb)))
    assert ok and "synced 1" in why and calls == ["a.mp4"] and sb["shots"][0]["lipsync"]

# ---------- server + chat + CLI
@FF
def test_server_character_routes(env, tmp_path):
    from seatcrew.server import serve
    wf = wf_(tmp_path); srv = serve(wf, port=0); port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
    def call(p, b=None):
        r = Request(f"http://127.0.0.1:{port}{p}", data=json.dumps(b).encode() if b is not None else None, headers={"Content-Type": "application/json"})
        try:
            with urlopen(r) as x: return x.status, x.read(), x.headers.get("Content-Type")
        except Exception as e: return e.code, e.read(), ""
    try:
        assert call("/characters")[0] == 200 and b"model-viewer" in call("/characters")[1] and call("/vendor/model-viewer.min.js")[0] == 200
        st, b, _ = call("/api/characters/create", dict(name="Mia", description="nurse", photos=["data:image/png;base64," + base64.b64encode(PNG).decode()]))
        assert st == 200 and json.loads(b)["character"]["urls"]["refs"] == ["/cfile/Mia/refs/ref1.png"]
        s, body, ct = call("/cfile/Mia/refs/ref1.png"); assert s == 200 and ct == "image/png" and body == PNG
        assert call("/cfile/Mia/../../config.yaml")[0] == 404 and call("/cfile/Mia/character.yaml")[0] in (200, 404)
        assert json.loads(call("/api/characters/sheet", dict(name="Mia", backend="draft"))[1])["draft"]
        assert json.loads(call("/api/casts/save", dict(name="Solo", members=[dict(character="Mia")]))[1])["ok"]
        st, b, _ = call("/api/casts/save", dict(name="Bad", members=[dict(character="Nope")])); assert st == 400
        assert json.loads(call("/api/casts/shoot", dict(name="Solo"))[1])["id"]
        s = json.loads(call("/api/characters")[1]); assert s["characters"][0]["name"] == "Mia" and "OPENAI_API_KEY" not in json.dumps(s)
    finally: srv.shutdown()

def test_chief_character_and_cast_intents(env, tmp_path):
    from seatcrew.server import chat_for
    wf = wf_(tmp_path); a = chat_for(wf)
    t = a.video_intent("create a character named Mia: 30, nurse, red scarf", "create a character named mia: 30, nurse, red scarf")
    assert t[0] == "create_character" and t[1]["name"] == "Mia"
    t2 = a.video_intent("创建角色 小美：二十八岁，短发，米色风衣", "创建角色 小美：二十八岁，短发，米色风衣"); assert t2[0] == "create_character" and t2[1]["name"] == "小美"
    p = a.propose("create_character", t[1]); a.execute(p); assert CH.Store().get("Mia")["description"].startswith("30")
    t3 = a.video_intent("make a cast called Duo with Mia and Leo", "make a cast called duo with mia and leo"); assert t3[0] == "create_cast"
    with pytest.raises(ValueError, match="Leo"): a.propose("create_cast", t3[1])
    CH.Store().create("Leo", "boy"); a.execute(a.propose("create_cast", t3[1])); assert len(CH.Store().cast("Duo")["members"]) == 2

@FF
def test_cli_character_cast_check(env, tmp_path, capsys):
    from seatcrew.video.cli import main
    p = img(tmp_path)
    assert main(["character", "create", "Mia", "--description", "nurse", "--photo", str(p)]) == 0
    assert main(["character", "lock", "Mia"]) == 0 and main(["cast", "save", "Solo", "--member", "Mia:lead:calm"]) == 0
    assert main(["cast", "export", "Solo", "-o", str(tmp_path / "solo.json")]) == 0 and "sk-" not in (tmp_path / "solo.json").read_text()
    v = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=320x180:d=3:r=24", "-f", "lavfi", "-i", "sine=f=300:d=3", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(v)], check=True)
    (tmp_path / "sb.yaml").write_text("shots:\n  - {id: s01, narration: hi, duration: 3, characters: [Mia]}\n")
    main(["check", str(v), "--storyboard", str(tmp_path / "sb.yaml"), "--cast", "Solo", "--json", str(tmp_path / "r.json")])
    out = capsys.readouterr().out; assert "character_consistency" in out and json.loads((tmp_path / "r.json").read_text())["checks"]

def test_privacy_scan_clean_and_catches(tmp_path, monkeypatch):
    import subprocess as sp, sys
    root = Path(__file__).resolve().parents[1]; scan = root / "scripts" / "privacy_scan.py"
    assert sp.run([sys.executable, str(scan)], cwd=root, capture_output=True).returncode == 0
    sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text('K = "sk-proj-' + "Q7w9" * 8 + '"\n'); (tmp_path / ".env").write_text("X=1\n"); (tmp_path / "clip.mp4").write_bytes(b"x")
    sp.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    r = sp.run([sys.executable, str(scan)], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1 and "a.py:1" in r.stdout and ".env" in r.stdout and "clip.mp4" in r.stdout

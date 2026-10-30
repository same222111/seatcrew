"""Video + TTS provider adapters, tested with mocked HTTP only (no network, no keys)."""
import base64, json, os
import pytest
from seatcrew.video import providers as PV, tts_cloud as TC, tts as TTS

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4000

class Fake:
    """Replaces providers._send. routes: list of (method, url_substring, [responses...]); each response (status, body)."""
    def __init__(self, routes): self.routes = [[m, u, list(r)] for m, u, r in routes]; self.calls = []
    def __call__(self, method, url, headers, data, timeout):
        self.calls.append(dict(method=method, url=url, headers=headers, data=data))
        for r in self.routes:
            if r[0] == method and r[1] in url:
                st, body = r[2].pop(0) if len(r[2]) > 1 else r[2][0]
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                return st, raw, "application/json"
        raise AssertionError(f"unexpected {method} {url}")
    def body(self, i): return json.loads(self.calls[i]["data"])

@pytest.fixture
def env(monkeypatch):
    for k in ("KLING_API_KEY", "RUNWAYML_API_SECRET", "LUMA_AGENTS_API_KEY", "GEMINI_API_KEY", "MINIMAX_API_KEY", "OPENAI_API_KEY", "REPLICATE_API_TOKEN",
              "ELEVENLABS_API_KEY", "VOLC_TTS_API_KEY", "VOLC_TTS_APPID", "VOLC_TTS_ACCESS_KEY", "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION", "SEATCREW_SORA_BASE", "GOOGLE_API_KEY", "LUMAAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(PV.time, "sleep", lambda s: None)
    def use(routes, **keys):
        for k, v in keys.items(): monkeypatch.setenv(k, v)
        f = Fake(routes); monkeypatch.setattr(PV, "_send", f); return f
    return use

def run(adapter, tmp_path, ref=None, **kw):
    clock = iter(range(0, 10_000, 1))
    return adapter.run("a cat at night", tmp_path / "s01.mp4", "9:16", 6, None, ref, sleep=lambda s: None, clock=lambda: next(clock), **kw)

@pytest.fixture
def ref(tmp_path):
    p = tmp_path / "hero.png"; p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100); return p

def test_kling_text_and_image_to_video(env, tmp_path, ref):
    f = env([("POST", "/text-to-video/kling-3.0", [(200, dict(code=0, data=dict(id="t1")))]),
             ("POST", "/image-to-video/kling-3.0", [(200, dict(code=0, data=dict(id="t2")))]),
             ("GET", "/tasks?task_ids=", [(200, dict(code=0, data=[dict(id="t1", status="processing")])),
                                          (200, dict(code=0, data=[dict(id="t1", status="succeeded", outputs=[dict(type="video", url="https://cdn.kling/x.mp4")])]))]),
             ("GET", "cdn.kling", [(200, MP4)])], KLING_API_KEY="k-secret")
    p = run(PV.Kling(), tmp_path); assert p.read_bytes() == MP4
    b = f.body(0); assert b["prompt"].startswith("a cat") and b["settings"]["duration"] == 6 and b["settings"]["aspect_ratio"] == "9:16"
    assert f.calls[0]["headers"]["Authorization"] == "Bearer k-secret" and f.calls[0]["url"] == "https://api-singapore.klingai.com/text-to-video/kling-3.0"
    run(PV.Kling(), tmp_path, ref)
    b = next(json.loads(c["data"]) for c in f.calls if "image-to-video" in c["url"])
    assert b["contents"][0]["type"] == "prompt" and b["contents"][1]["type"] == "first_frame" and base64.b64decode(b["contents"][1]["url"]) == ref.read_bytes()

def test_kling_failed_task_and_bad_key(env, tmp_path):
    env([("POST", "/text-to-video/", [(200, dict(code=0, data=dict(id="t1")))]), ("GET", "/tasks", [(200, dict(data=[dict(status="failed", message="risk control")]))])], KLING_API_KEY="k")
    with pytest.raises(PV.ProviderError, match="risk control"): run(PV.Kling(), tmp_path)
    env([("POST", "/text-to-video/", [(401, dict(message="bad"))])], KLING_API_KEY="k")
    with pytest.raises(PV.ProviderError, match="key rejected"): run(PV.Kling(), tmp_path)

def test_missing_key_is_clear(env, tmp_path):
    env([])
    with pytest.raises(PV.ProviderError, match="KLING_API_KEY is not set"): run(PV.Kling(), tmp_path)

def test_runway_retries_429_then_polls(env, tmp_path, ref):
    f = env([("POST", "/v1/image_to_video", [(429, dict(error="slow down")), (200, dict(id="r1"))]),
             ("GET", "/v1/tasks/r1", [(200, dict(status="RUNNING")), (200, dict(status="SUCCEEDED", output=["https://dnznrvs05pmza.cloudfront.net/o.mp4"]))]),
             ("GET", "cloudfront", [(200, MP4)])], RUNWAYML_API_SECRET="rw")
    run(PV.Runway(), tmp_path, ref)
    posts = [c for c in f.calls if c["method"] == "POST"]; assert len(posts) == 2               # one retry
    b = json.loads(posts[1]["data"]); assert b["model"] == "gen4.5" and b["ratio"] == "720:1280" and b["duration"] == 6 and b["promptImage"].startswith("data:image/png;base64,")
    assert posts[1]["headers"]["X-Runway-Version"] == "2024-11-06"

def test_runway_text_only_and_failed(env, tmp_path):
    f = env([("POST", "/v1/text_to_video", [(200, dict(id="r2"))]), ("GET", "/v1/tasks/r2", [(200, dict(status="FAILED", failure="moderation"))])], RUNWAYML_API_SECRET="rw")
    with pytest.raises(PV.ProviderError, match="moderation"): run(PV.Runway(), tmp_path)
    assert "promptImage" not in f.body(0)

def test_luma_ray32(env, tmp_path, ref):
    f = env([("POST", "/v1/generations", [(201, dict(id="g1", state="queued"))]),
             ("GET", "/v1/generations/g1", [(200, dict(state="dreaming")), (200, dict(state="completed", output=[dict(type="video", url="https://storage.luma/o.mp4")]))]),
             ("GET", "storage.luma", [(200, MP4)])], LUMA_AGENTS_API_KEY="lu")
    run(PV.Luma(), tmp_path, ref); b = f.body(0)
    assert b["model"] == "ray-3.2" and b["type"] == "video" and b["video"]["duration"] == "5s" and b["video"]["start_frame"]["media_type"] == "image/png"

def test_gemini_omni_inline_and_polled(env, tmp_path, ref):
    vid = base64.b64encode(MP4).decode()
    f = env([("POST", "/v1beta/interactions", [(200, dict(id="i1", status="completed", steps=[dict(type="model_output", content=[dict(type="video", data=vid)])]))])], GEMINI_API_KEY="g")
    p = run(PV.Gemini(), tmp_path, ref); assert p.read_bytes() == MP4
    b = f.body(0); assert b["model"] == "gemini-omni-1.1-flash" and b["generation_config"]["video_config"]["task"] == "image_to_video"
    assert b["input"][0]["type"] == "image" and b["response_format"]["duration"] == "6s" and f.calls[0]["headers"]["x-goog-api-key"] == "g"
    f = env([("POST", "/v1beta/interactions", [(200, dict(id="i2", status="in_progress"))]),
             ("GET", "/v1beta/interactions/i2", [(200, dict(status="in_progress")), (200, dict(status="completed", steps=[dict(type="model_output", content=[dict(type="video", data=vid)])]))])], GEMINI_API_KEY="g")
    assert run(PV.Gemini(), tmp_path).read_bytes() == MP4

def test_minimax_hailuo_reference(env, tmp_path, ref):
    f = env([("POST", "/v2/video_generation", [(200, dict(task_id="m1", base_resp=dict(status_code=0)))]),
             ("GET", "/v2/query/video_generation/m1", [(200, dict(status="Processing")), (200, dict(status="Success", content=dict(url="https://cdn.hailuo/x.mp4")))]),
             ("GET", "cdn.hailuo", [(200, MP4)])], MINIMAX_API_KEY="mm")
    run(PV.MiniMax(), tmp_path, ref); b = f.body(0)
    assert b["model"] == "MiniMax-H3" and b["content"][1]["role"] == "reference_image" and b["duration"] == 6 and b["ratio"] == "9:16"
    env([("POST", "/v2/video_generation", [(200, dict(base_resp=dict(status_code=1008, status_msg="insufficient balance")))])], MINIMAX_API_KEY="mm")
    with pytest.raises(PV.ProviderError, match="insufficient balance"): run(PV.MiniMax(), tmp_path)

def test_sora_is_retired_but_compatible_endpoint_works(env, tmp_path, monkeypatch):
    env([], OPENAI_API_KEY="o")
    with pytest.raises(PV.ProviderError, match="discontinued"): run(PV.Sora(), tmp_path)
    f = env([("POST", "/videos", [(200, dict(id="v1"))]), ("GET", "/videos/v1/content", [(200, MP4)]), ("GET", "/videos/v1", [(200, dict(status="completed"))])],
            OPENAI_API_KEY="o", SEATCREW_SORA_BASE="https://example.invalid/v1")
    run(PV.Sora(), tmp_path); assert f.body(0)["seconds"] == "4" and f.body(0)["size"] == "720x1280"

def test_replicate_and_timeout(env, tmp_path):
    env([("POST", "/predictions", [(201, dict(id="p", urls=dict(get="https://api.replicate.com/v1/predictions/p")))]),
         ("GET", "/v1/predictions/p", [(200, dict(status="processing"))])], REPLICATE_API_TOKEN="r")
    a = PV.Replicate(); a.max_wait = 5
    with pytest.raises(PV.ProviderError, match="timed out"):
        a.run("x", tmp_path / "o.mp4", "9:16", 5, "kwaivgi/kling-v2.1", sleep=lambda s: None, clock=iter(range(100)).__next__)

def test_network_errors_retry_then_fail(env, tmp_path, monkeypatch):
    n = []
    def boom(*a): n.append(1); raise PV.ProviderError("network: down")
    monkeypatch.setenv("KLING_API_KEY", "k"); monkeypatch.setattr(PV, "_send", boom)
    with pytest.raises(PV.ProviderError, match="network"): run(PV.Kling(), tmp_path)
    assert len(n) == 4

def test_visuals_make_uses_provider_with_character_ref(env, tmp_path, ref):
    from seatcrew.video import visuals as VIS
    f = env([("POST", "/text-to-video/", [(200, dict(code=0, data=dict(id="a")))]), ("POST", "/image-to-video/", [(200, dict(code=0, data=dict(id="a")))]),
             ("GET", "/tasks", [(200, dict(data=[dict(status="succeeded", outputs=[dict(type="video", url="https://cdn.kling/x.mp4")])]))]),
             ("GET", "cdn.kling", [(200, MP4)])], KLING_API_KEY="k")
    shot = dict(id="s01", visual="girl at desk", duration=4, lines=[dict(speaker="林晚", text="妈？")])
    p, info = VIS.make(shot, tmp_path, "9:16", pref="kling", refs={"林晚": str(ref)})
    assert info == dict(backend="kling", model="kling-3.0", ref_image="hero.png") and p.exists()
    assert any("image-to-video" in c["url"] for c in f.calls)
    assert VIS.auto_order("auto")[0] == "kling"

def test_estimate_and_catalog():
    e = PV.estimate([dict(duration=5)] * 4, "runway"); assert e["usd"] == 2.4 and "check current pricing" in e["note"] and e["pricing"].startswith("https://")
    assert PV.estimate([dict(duration=5)], "replicate")["usd"] is None
    rec = PV.recommended()
    assert set(rec) == {"video", "tts"} and all(set(t) == {"best_quality", "best_value", "free_draft"} for t in rec.values())
    for e in PV.CATALOG:
        assert e["checked"] == PV.CHECKED
        for k in ("docs", "key_url", "pricing"):
            if e[k]: assert e[k].startswith("https://")

def test_test_key_never_leaks(env):
    env([("GET", "api.minimax.io", [(401, dict(base_resp=dict(status_msg="invalid")))])], MINIMAX_API_KEY="sk-SECRET123")
    r = PV.test_key("minimax"); assert not r["ok"] and "SECRET" not in json.dumps(r)
    env([("GET", "api.elevenlabs.io/v1/user", [(200, dict(ok=1))])], ELEVENLABS_API_KEY="el")
    assert PV.test_key("elevenlabs")["ok"]
    assert not PV.test_key("kling")["ok"] and PV.test_key("edge")["ok"]

# ---------------- TTS ----------------
@pytest.fixture
def nodur(monkeypatch):
    monkeypatch.setattr(TC.ff, "duration", lambda p: 1.5)

def test_minimax_tts_emotion(env, tmp_path, nodur):
    f = env([("POST", "/v1/t2a_v2", [(200, dict(data=dict(audio=(b"ID3" + b"\x00" * 50).hex()), base_resp=dict(status_code=0)))])], MINIMAX_API_KEY="mm")
    out, words, info = TC.minimax("你好呀", tmp_path / "a", voice="SeatCrewMom", style="worried", speed=0.9)
    b = f.body(0); assert b["model"] == "speech-2.8-hd" and b["voice_setting"]["emotion"] == "fearful" and b["voice_setting"]["voice_id"] == "SeatCrewMom"
    assert info["backend"] == "minimax" and words and out.endswith(".mp3")
    TC.minimax("hi", tmp_path / "b", style="whisper"); assert f.body(1)["voice_setting"]["emotion"] == "calm"   # 2.8 has no whisper

def test_doubao_tts_stream_and_errors(env, tmp_path, nodur):
    chunks = b"\n".join(json.dumps(x).encode() for x in (dict(code=0, data=base64.b64encode(b"AAA").decode()), dict(code=0, data=base64.b64encode(b"BBB").decode()), dict(code=20000000)))
    f = env([("POST", "/api/v3/tts/unidirectional", [(200, chunks)])], VOLC_TTS_API_KEY="vk")
    out, words, info = TC.doubao("妈，我想你了", tmp_path / "a", voice="S_abc123", style="sad")
    assert open(out, "rb").read() == b"AAABBB"
    h = f.calls[0]["headers"]; assert h["X-Api-Key"] == "vk" and h["X-Api-Resource-Id"] == "seed-icl-2.0"
    assert f.body(0)["req_params"]["audio_params"]["emotion"] == "sad"
    env([("POST", "/api/v3/tts/unidirectional", [(200, json.dumps(dict(code=45000001, message="speaker not found")).encode())])], VOLC_TTS_API_KEY="vk")
    with pytest.raises(TTS.TTSError, match="speaker not found"): TC.doubao("x", tmp_path / "b")

def test_azure_real_ssml_style(env, tmp_path, nodur):
    f = env([("POST", "tts.speech.microsoft.com/cognitiveservices/v1", [(200, b"ID3" + b"\x00" * 400)])], AZURE_SPEECH_KEY="az", AZURE_SPEECH_REGION="eastasia")
    out, words, info = TC.azure("这孩子 <又> 加班了吧", tmp_path / "a", voice="zh-CN-XiaoxiaoNeural", style="tender", rate=-8, pitch=-16)
    ssml = f.calls[0]["data"].decode()
    assert f.calls[0]["url"] == "https://eastasia.tts.speech.microsoft.com/cognitiveservices/v1"
    assert '<mstts:express-as style="affectionate"' in ssml and 'pitch="-16Hz"' in ssml and "&lt;又&gt;" in ssml and info["style"] == "affectionate"

def test_synth_routes_profile_to_backend(env, tmp_path, nodur, monkeypatch):
    from seatcrew.video import voices as VO
    f = env([("POST", "tts.speech.microsoft.com", [(200, b"ID3" + b"\x00" * 400)])], AZURE_SPEECH_KEY="az", AZURE_SPEECH_REGION="eastasia")
    prof = VO.clean_profile("妈妈", dict(preset="zh-CN/elderly_woman", backend="azure"))
    kw = VO.resolve(prof, "sad")
    p, w, info = TTS.synth("睡了吗", tmp_path / "x", pref="azure", voice=kw["voice"], lang="zh-CN", style=kw["style"], azure_voice=kw["azure_voice"], base=kw["base"])
    ssml = f.calls[0]["data"].decode(); assert "zh-CN-XiaoxiaoNeural" in ssml and 'style="sad"' in ssml and 'rate="-8%"' in ssml and info["backend"] == "azure"

def test_clones_return_ids_never_keys(env, tmp_path):
    s = tmp_path / "me.wav"; s.write_bytes(b"RIFF" + b"\x00" * 2000)
    f = env([("POST", "/v1/voices/add", [(200, dict(voice_id="EL123abc456"))])], ELEVENLABS_API_KEY="el-key")
    assert TC.clone("elevenlabs", "妈妈", s) == "EL123abc456" and b'name="files"' in f.calls[0]["data"]
    f = env([("POST", "/v1/files/upload", [(200, dict(file=dict(file_id=99)))]), ("POST", "/v1/voice_clone", [(200, dict(base_resp=dict(status_code=0)))])], MINIMAX_API_KEY="mm")
    vid = TC.clone("minimax", "妈妈", s, "SeatCrewMom01"); assert vid == "SeatCrewMom01" and f.body(1) == dict(file_id=99, voice_id="SeatCrewMom01")
    assert b'name="purpose"' in f.calls[0]["data"]
    f = env([("POST", "mega_tts/audio/upload", [(200, dict(BaseResp=dict(StatusCode=0)))])], VOLC_TTS_APPID="app", VOLC_TTS_ACCESS_KEY="tok")
    assert TC.clone("doubao", "妈妈", s, "S_abc123") == "S_abc123" and f.calls[0]["headers"]["Authorization"] == "Bearer;tok"
    with pytest.raises(PV.ProviderError): TC.clone("doubao", "x", s, "nope")
    with pytest.raises(PV.ProviderError, match="not supported"): TC.clone("azure", "x", s)

def test_library_saves_cloned_ids_not_keys(tmp_path, env):
    from seatcrew.video import voices as VO
    lib = VO.Library(tmp_path / "voices" / "characters.yaml")
    lib.set("妈妈", preset="zh-CN/elderly_woman", backend="minimax", minimax_voice="SeatCrewMom01", ref_image="refs/mom.png")
    txt = (tmp_path / "voices" / "characters.yaml").read_text(encoding="utf-8")
    assert "SeatCrewMom01" in txt and "refs/mom.png" in txt and "api_key" not in txt.lower()
    with pytest.raises(ValueError): lib.set("x", ref_image="../../etc/passwd.png")

def test_models_route_and_chief_answer():
    from seatcrew import assistant as AS
    obj, code = AS.route(None, "GET", "/api/models"); assert code == 200 and "video" in obj["tiers"]
    obj, code = AS.route(None, "POST", "/api/models/test", dict(id="nope")); assert code == 404
    assert AS.static("/models.js")[0].startswith(b"//")
    class A:
        lang = "zh-CN"
    txt = AS.Assistant.models_answer(A(), "推荐模型")
    assert "最佳画质" in txt and "kling" in txt.lower() and "https://" in txt

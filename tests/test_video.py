"""Short-video workflow: storyboard format, mock backends, tiny ffmpeg assembly, QC -> send-back loops, draft labeling, no secrets."""
import json, re, shutil
from pathlib import Path
import pytest
from seatcrew import loader
from seatcrew.video import storyboard as SB, tts as TTS, visuals as VIS, editor as ED, qc as QC, key_status, DRAFT_LABEL
from seatcrew.video.subs import build_ass, chunk

FF = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg not installed")
TINY = dict(supersample=1, preset="ultrafast", inter_crf=23)
NOTES = "Sunlight looks white but holds every colour. Air scatters short blue waves the most. So blue reaches your eyes from all over the sky."

def wf_(tmp_path, **settings):
    wf = loader.build("short_video", str(tmp_path / "config.yaml"), str(tmp_path))
    wf.cfg.data["settings"].update(dict(tts_backend="mock", visuals_backend="mock", allow_draft=False), **settings)
    wf.size_override = (270, 480); wf.editor_opts = dict(TINY); wf.qc_total = (1, 200); wf.qc_opts = dict(min_sharpness=0.0)
    return wf

def run(wf, **data):
    it = wf.submit(data=dict(dict(topic="Why is the sky blue?", notes=NOTES), **data)); wf.run_cycle()
    return next(i for i in wf.items if i["id"] == it["id"])

# ---- format
def test_storyboard_validation():
    sb = SB.validate_storyboard({"aspect": "16:9", "shots": [{"narration": "Hi.", "duration": 2}]})
    assert sb["shots"][0]["id"] == "s01" and sb["shots"][0]["camera"] == "push_in" and sb["shots"][0]["transition"] == "crossfade"
    for bad in [{}, {"shots": []}, {"aspect": "4:3", "shots": [{}]}, {"shots": [{"duration": 99}]}, {"shots": [{"camera": "spin"}]},
                {"shots": [{"id": "a"}, {"id": "a"}]}, {"shots": [{"id": "../x"}]}]:
        with pytest.raises(ValueError): SB.validate_storyboard(bad)

def test_subtitle_chunks_and_ass():
    words = [dict(w=w, start=i * 0.3, end=i * 0.3 + 0.25) for i, w in enumerate("one two three four five six seven eight nine ten".split())]
    lines = chunk(words, dict(max_chars=16, max_cjk=10)); assert all(len(" ".join(x["w"] for x in l)) <= 16 or len(l) == 1 for l in lines)
    ass, cues = build_ass(words, [(0, 3, "Title")], 1080, 1920, 3.5)
    assert "\\k" in ass and "Montserrat" in ass and cues

def test_tts_tokens_cjk_and_estimate():
    assert TTS.tokens("天空 blue") == ["天", "空", "blue"]
    w = TTS.estimate("one two three", 3.0); assert len(w) == 3 and w[-1]["end"] <= 3.0

def test_no_keys_means_no_paid_backend(monkeypatch):
    assert TTS.auto_order("auto")[:1] != ["openai"] and VIS.auto_order("auto") == []
    assert set(key_status().values()) == {False}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test"); assert key_status()["openai"] is True and "openai" in VIS.auto_order("auto")

# ---- full chain with mock providers + tiny ffmpeg assembly
@FF
def test_mock_chain_assembles_and_passes_qc(tmp_path):
    wf = wf_(tmp_path); it = run(wf)
    assert "pending" in it, [c["reason"] for c in it["chain"]]
    d = it["data"]; out = tmp_path / "videos" / str(it["id"]) / d["video"]["file"]
    assert out.name == "final.mp4" and out.is_file() and d["qc"]["passed"] and not d["video"]["draft"]
    man = json.loads((out.parent / "work" / "manifest.json").read_text())
    assert man["size"] == [270, 480] and abs(man["loudness"]["out_i"] + 14) < 1.0 if "out_i" in man.get("loudness", {}) else True
    rep = json.loads((out.parent / "quality_report.json").read_text()); names = {c["name"] for c in rep["checks"]}
    assert {"format", "sharpness", "black_frames", "frozen_frames", "loudness", "clipping", "subtitle_sync", "duration"} <= names
    assert wf.media_file(it["id"], "final.mp4") == out
    for bad in ("../config.yaml", "work/manifest.json", "voice/s01.wav", "final.mp4/../../x"): assert wf.media_file(it["id"], bad) is None
    assert wf.media_file("1/..", "final.mp4") is None

@FF
def test_qc_failure_sends_back_to_visuals_then_holds(tmp_path):
    wf = wf_(tmp_path, max_rewrites=1); wf.qc_opts = dict(min_sharpness=1e9)      # nothing can be this sharp
    it = run(wf)
    assert "pending" not in it and it["data"]["rounds"] == {"visuals": 1}
    assert not it["data"]["qc"]["passed"] and it["data"]["qc"]["send_back"] == "visuals"
    acts = [json.loads(x)["kind"] for x in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert "REWRITE" in acts and "HOLD" in acts

@FF
def test_qc_fail_then_fixed_by_rerun(tmp_path, monkeypatch):
    """First visuals pass is blurry; QC sends it back; the rerun is sharp; the item reaches APPROVE."""
    wf = wf_(tmp_path); wf.qc_opts = dict(min_sharpness=5.0); calls = {"n": 0}
    real = VIS.mock_image
    def flaky(shot, out_dir, aspect, **k):
        calls["n"] += 1; p = real(shot, out_dir, aspect)
        if calls["n"] <= 3:                                                         # first round: blur every shot
            from seatcrew.video import ff; b = Path(out_dir) / f"{shot['id']}_b.png"
            ff.run(["-i", str(p), "-vf", "gblur=sigma=40", str(b)]); return b
        return p
    monkeypatch.setattr(VIS, "mock_image", flaky)
    it = run(wf)
    assert "pending" in it and it["data"]["rounds"].get("visuals") == 1 and it["data"]["qc"]["passed"]

def test_scriptcheck_blocks_and_writer_rewrites(tmp_path, monkeypatch):
    wf = wf_(tmp_path, max_rewrites=2)
    it = run(wf, notes="This miracle cream is guaranteed to work.")
    # v0.9.4: the rules writer would produce the same script again -> no futile rewrite rounds, an actionable tip instead
    assert "pending" not in it and not it["data"]["rounds"].get("writer") and it["data"]["tip"]
    assert any("guaranteed" in c["reason"] or "miracle" in c["reason"] for c in it["chain"] if c["seat"] == "scriptcheck")

def test_ai_writer_gets_feedback_and_fixes_script(tmp_path, monkeypatch):
    """The WRITER's AI is told why SCRIPT CHECK blocked it; a fixed script passes."""
    from seatcrew import llm
    seen = []
    def fake(role, user, cfg, max_tokens=900, **k):
        seen.append(user); bad = len(seen) == 1
        shots = [dict(narration=("This is guaranteed to work." if bad else "Light from the sun holds every colour."), caption="Sky", duration=3, visual="blue sky"),
                 dict(narration="Air scatters the blue part of that light the most.", caption="Scatter", duration=4, visual="air"),
                 dict(narration="So blue light reaches your eyes from every direction.", caption="Everywhere", duration=4, visual="sky"),
                 dict(narration="At sunset the light crosses more air, and red wins.", caption="Sunset", duration=4, visual="sunset")]
        return json.dumps(dict(title="Sky", shots=shots)), "xai"
    monkeypatch.setattr(llm, "write", fake)
    wf = wf_(tmp_path); wf.cfg.data["settings"]["visuals_backend"] = "mock"
    monkeypatch.setattr(ED, "assemble", lambda *a, **k: (_ for _ in ()).throw(ValueError("stop here")))
    it = run(wf, notes="")
    assert it["data"]["rounds"].get("writer") == 1 and len(seen) >= 2 and "guaranteed" in seen[1]
    assert "guaranteed" not in json.dumps(it["data"]["storyboard"])

@FF
def test_draft_is_labeled_everywhere(tmp_path):
    wf = wf_(tmp_path, tts_backend="draft", visuals_backend="draft", allow_draft=True); it = run(wf)
    d = it["data"]; assert d["video"]["draft"] and d["video"]["file"] == "final_DRAFT.mp4"
    assert any(c["name"] == "final_quality" and not c["ok"] for c in d["qc"]["checks"]) and "DRAFT" in d["qc"]["summary"]
    man = json.loads((tmp_path / "videos" / str(it["id"]) / "work" / "manifest.json").read_text()); assert man["draft"] is True
    assert DRAFT_LABEL.lower().startswith("draft preview")

def test_no_draft_when_not_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(TTS, "auto_order", lambda pref="auto": [])               # no keys, no edge-tts: nothing final available
    wf = wf_(tmp_path, tts_backend="auto", visuals_backend="auto", allow_draft=False)
    it = run(wf); blk = [c for c in it["chain"] if not c["ok"]]
    assert blk and blk[-1]["seat"] == "production" and blk[-1]["reason"].split(":")[0] in ("voice", "visuals") and "video" not in it["data"]

@FF
def test_no_secrets_in_state(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRETSECRETSECRET123"); monkeypatch.setenv("ELEVENLABS_API_KEY", "el-SECRETSECRET999")
    wf = wf_(tmp_path); run(wf); wf.cfg.save()
    blob = "".join(p.read_text(errors="ignore") for p in tmp_path.rglob("*") if p.is_file() and p.suffix in (".json", ".yaml", ".jsonl", ".ass", ".txt"))
    blob += json.dumps(wf.definition()) + json.dumps([wf.item_view(i) for i in wf.items])
    assert "SECRETSECRET" not in blob and wf.definition()["keys"]["openai"] is True

def test_settings_validation(tmp_path):
    wf = wf_(tmp_path); import copy
    for k, v in [("template", "horror"), ("aspect", "4:3"), ("max_rewrites", 9), ("crf", 40)]:
        bad = copy.deepcopy(wf.cfg.data); bad["settings"][k] = v
        with pytest.raises((ValueError, KeyError)): wf.cfg.validate(bad)

def test_definition_and_profiles(tmp_path):
    wf = loader.build("short_video", str(tmp_path / "config.yaml"), str(tmp_path)); d = wf.definition()
    assert d["studio"] == "video" and "emotional_story" in d["choices"]["template"]
    assert [f for f in d["submit"] if f["name"] == "template"][0]["type"] == "select"
    from seatcrew import profiles as PF
    for f in (Path(loader.__file__).parent.parent / "examples" / "short_video" / "profiles").glob("*.json"):
        doc = PF.parse(f.read_text()); assert doc["workflow"] == "short_video"; PF.clean(wf.cfg, doc["data"])

def test_locales_complete():
    base = Path(loader.__file__).parent.parent / "examples" / "short_video" / "locales"
    en = json.loads((base / "en.json").read_text(encoding="utf-8"))
    for l in ("zh-CN", "zh-TW", "ja", "es"): assert set(json.loads((base / f"{l}.json").read_text(encoding="utf-8"))) == set(en)

@FF
def test_cli_init_and_assemble(tmp_path, monkeypatch):
    from seatcrew.video.cli import main
    from seatcrew.video import ff
    d = tmp_path / "v"; assert main(["init", str(d), "--template", "product_promo"]) == 0 and (d / "storyboard.yaml").is_file()
    (d / "storyboard.yaml").write_text('aspect: "16:9"\nshots:\n  - {id: a, narration: "Hello there friend.", duration: 2}\n  - {id: b, narration: "Goodbye now.", duration: 2, camera: pan_left}\n')
    ff.run(["-f", "lavfi", "-i", "testsrc2=s=1920x1080:d=4", "-c:v", "libx264", "-preset", "ultrafast", str(d / "clips" / "a.mp4")])
    ff.run(["-f", "lavfi", "-i", "testsrc2=s=1920x1080", "-frames:v", "1", str(d / "clips" / "b.png")])
    monkeypatch.setattr(ED, "DEFAULTS", dict(ED.DEFAULTS, supersample=1)); monkeypatch.setattr(TTS, "auto_order", lambda pref="auto": ["mock"])
    main(["assemble", str(d), "--preset", "ultrafast"])
    assert (d / "final.mp4").is_file() and (d / "quality_report.json").is_file()
    v = ff.vstream(str(d / "final.mp4")); assert (int(v["width"]), int(v["height"])) == (1920, 1080)

def test_media_route_range(tmp_path):
    import threading, urllib.request
    from seatcrew.server import serve
    wf = wf_(tmp_path); vd = tmp_path / "videos" / "7"; vd.mkdir(parents=True); (vd / "final.mp4").write_bytes(bytes(range(256)) * 4)
    srv = serve(wf, "127.0.0.1", 0); port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/media/7/final.mp4", headers={"Range": "bytes=10-19"}))
        assert r.status == 206 and r.read() == bytes(range(10, 20)) and r.headers["Content-Range"] == "bytes 10-19/1024"
        assert urllib.request.urlopen(f"http://127.0.0.1:{port}/media/7/final.mp4").read() == bytes(range(256)) * 4
        for bad in ("/media/7/config.yaml", "/media/7/..%2F..%2Fconfig.yaml", "/media/x/final.mp4"):
            with pytest.raises(urllib.error.HTTPError): urllib.request.urlopen(f"http://127.0.0.1:{port}{bad}")
        assert b"studio" in urllib.request.urlopen(f"http://127.0.0.1:{port}/studio.js").read()
    finally: srv.shutdown()


@FF
def test_chinese_draft_titles_render_distinct_glyphs(tmp_path):
    # Same layout/background and character count: missing-glyph boxes would match.
    a = tmp_path / "a"; b = tmp_path / "b"; a.mkdir(); b.mkdir()
    first = VIS.draft_card({"id": "s01", "caption": "天空"}, a, "9:16", size=(270,480))
    second = VIS.draft_card({"id": "s01", "caption": "蓝色"}, b, "9:16", size=(270,480))
    import subprocess, numpy as np
    def glyph_mask(path):
        raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        return (np.frombuffer(raw, dtype=np.uint8).reshape(-1,3) > 220).all(axis=1)
    assert not np.array_equal(glyph_mask(first), glyph_mask(second)), "Chinese title rendered identical missing-glyph boxes"

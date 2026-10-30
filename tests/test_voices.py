"""Character voice library: presets, persistent profiles, storyboard dialogue lines, per-line rendering, QC consistency,
per-speaker subtitle colors, CHIEF chat voice changes, share/export without keys, dashboard API."""
import json, shutil
from pathlib import Path
import pytest
from seatcrew import loader, profiles as PF
from seatcrew.video import voices as VO, storyboard as SB, editor as ED, qc as QC
from seatcrew.video.subs import build_ass, chunk

FF = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")

@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); return VO.Library()

def test_presets_many_languages_and_valid():
    ps = VO.presets(); ids = [p["id"] for p in ps]
    assert len(ps) >= 60 and len(set(ids)) == len(ids)
    for lg in ("zh-CN", "zh-TW", "en", "ja", "es"):
        kinds = {p["kind"] for p in VO.presets(lg)}
        assert {"narrator_female", "elderly_woman", "elderly_man", "child_girl", "mature_male", "young_female_gentle"} <= kinds
    for p in ps: VO.clean_profile("x", dict(preset=p["id"]))
    assert VO.lang_key("zh-HK") == "zh-TW" and VO.lang_key("fr") == "en"

def test_library_persists_and_validates(lib, tmp_path):
    p = lib.set("妈妈", preset="zh-CN/elderly_woman", description="mom", color="#FFB3C7")
    assert p["voice"] == "zh-CN-XiaoxiaoNeural" and p["pitch"] < 0 and p["age"] == "elderly"
    lib.set("妈妈", rate=-20)                                      # update keeps the rest
    again = VO.Library().get("妈妈"); assert again["rate"] == -20 and again["description"] == "mom"
    assert (tmp_path / "voices" / "characters.yaml").is_file()
    for bad in [dict(rate=99), dict(style="angry_shout"), dict(gender="x"), dict(voice="bad id"), dict(color="red"), dict(openai_voice="zzz"), dict(backend="foo")]:
        with pytest.raises(ValueError): lib.set("妈妈", **bad)
    with pytest.raises(ValueError): lib.set("../evil", rate=1)
    raw = VO.clean_profile("x", dict(api_key="sk-abcdefghijklmnopqrstuvwxyz123456", voice="en-US-AvaNeural"))
    assert "api_key" not in raw
    lib.delete("妈妈"); assert "妈妈" not in VO.Library().all()

def test_overlay_and_signature(lib, tmp_path):
    lib.set("林晚", preset="zh-CN/young_female_gentle")
    (tmp_path / "v").mkdir(); (tmp_path / "v" / "characters.yaml").write_text("characters:\n  妈妈: {preset: zh-CN/elderly_woman}\n", encoding="utf-8")
    both = VO.Library(overlay=tmp_path / "v" / "characters.yaml").all(); assert set(both) == {"林晚", "妈妈"}
    a = both["林晚"]; assert VO.signature(a) == VO.signature(dict(a, style="sad")) != VO.signature(dict(a, pitch=a["pitch"] - 1))

def test_resolve_emotion_and_adjust():
    p = VO.clean_profile("m", dict(preset="zh-CN/elderly_woman"))
    k = VO.resolve(p, "sad"); assert k["rate"].endswith("%") and k["pitch"].endswith("Hz") and k["instructions"] and k["style"] == "sad"
    assert int(VO.resolve(p, "sad")["rate"][:-1]) < int(VO.resolve(p, "cheerful")["rate"][:-1])
    with pytest.raises(ValueError): VO.resolve(p, "angry_shout")
    o = VO.adjusted(p, "older"); assert o["pitch"] < p["pitch"] and o["rate"] < p["rate"]

def test_storyboard_lines():
    sb = SB.validate_storyboard({"shots": [{"narration": "Hi."}, {"lines": ["林晚: 妈？", {"speaker": "妈妈", "text": "嗯。", "emotion": "tender", "pause": 0.5}]}]})
    a, b = sb["shots"]
    assert a["lines"] == [dict(speaker="narrator", text="Hi.", emotion=None, kind="narration")]
    assert [l["speaker"] for l in b["lines"]] == ["林晚", "妈妈"] and b["lines"][1]["pause"] == 0.5 and b["lines"][0]["kind"] == "dialogue"
    assert SB.speakers(sb) == ["narrator", "妈妈", "林晚"] or set(SB.speakers(sb)) == {"narrator", "妈妈", "林晚"}
    for bad in [{"shots": [{"lines": [{"speaker": "a"}]}]}, {"shots": [{"lines": "x"}]}, {"shots": [{"lines": [{"text": "x", "emotion": "Bad Emotion!"}]}]}]:
        with pytest.raises(ValueError): SB.validate_storyboard(bad)

@FF
def test_render_lines_tags_speakers_and_keeps_timing(lib, tmp_path):
    lib.set("A", preset="en/young_male"); lib.set("B", preset="en/elderly_woman")
    lines = [dict(speaker="A", text="one two"), dict(speaker="B", text="three four five", emotion="sad", pause=0.4), dict(speaker="narrator", text="six")]
    p, words, info = VO.render_lines(lines, tmp_path / "v.wav", lib, lang="en", pref="mock")
    assert Path(p).is_file() and [w["speaker"] for w in words] == ["A", "A", "B", "B", "B", "narrator"]
    assert all(b["start"] >= a["start"] for a, b in zip(words, words[1:])) and words[2]["start"] - words[1]["end"] >= 0.35
    assert [i["speaker"] for i in info] == ["A", "B", "narrator"] and info[1]["style"] == "sad"
    with pytest.raises(ValueError): VO.render_lines([dict(speaker="Nobody", text="x")], tmp_path / "n.wav", lib, lang="en", pref="mock")

def test_subs_speaker_colors_and_breaks():
    ws = [dict(w=w, start=i * .3, end=i * .3 + .25, shot=0, speaker="A" if i < 2 else "B") for i, w in enumerate("one two three four".split())]
    g = chunk(ws, dict(max_chars=30, max_cjk=10)); assert [len(x) for x in g] == [2, 2]
    ass, cues = build_ass(ws, [], 1080, 1920, 2.0, speaker_colors={"B": "#FFB3C7"})
    assert "\\1c&H00C7B3FF" in ass and cues[1]["speaker"] == "B" and ass.count("\\1c") == 1
    cj = [dict(w=c, start=i * .2, end=i * .2 + .15, shot=0) for i, c in enumerate(list("桌上的手机忽然亮了一下。"))]
    assert len(chunk(cj, dict(max_chars=16, max_cjk=10))) == 1           # no orphan "下。"

@FF
def test_workflow_uses_character_voices_and_qc_checks_consistency(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    VO.Library().set("Mom", preset="en/elderly_woman", color="#FFB3C7"); VO.Library().set("narrator", preset="en/narrator_male")
    wf = loader.build("short_video", str(tmp_path / "config.yaml"), str(tmp_path))
    wf.cfg.data["settings"].update(tts_backend="mock", visuals_backend="mock", allow_draft=False)
    wf.size_override = (270, 480); wf.editor_opts = dict(supersample=1, preset="ultrafast", inter_crf=23); wf.qc_total = (1, 200); wf.qc_opts = dict(min_sharpness=0.0)
    it = wf.submit(data=dict(topic="Mom calls", notes="Late at night the phone rings on my desk. It is Mom, asking if I ate dinner today. I want to say I am busy, but I stop. I tell her that I miss her very much.")); wf.run_cycle()
    it = next(i for i in wf.items if i["id"] == it["id"]); d = it["data"]
    qc = {c["name"]: c for c in d["qc"]["checks"]}
    assert qc["voice_consistency"]["ok"], qc["voice_consistency"]
    man = json.loads((wf.item_dir(it) / "work" / "manifest.json").read_text(encoding="utf-8"))
    assert man["voices"] and {v["speaker"] for v in man["voices"]} == {"narrator"}
    man["voices"].append(dict(man["voices"][0], signature="different", shot="sX"))       # same character, another voice -> FAIL
    r = QC.check(man, dict(total_sec=(1, 200)), min_sharpness=0.0)
    c = next(c for c in r["checks"] if c["name"] == "voice_consistency"); assert not c["ok"] and r["send_back"] == "voice"

def test_chief_chat_assigns_voices(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from seatcrew.assistant import Assistant
    wf = loader.build("short_video", str(tmp_path / "config.yaml"), str(tmp_path))
    VO.Library().set("妈妈", preset="zh-CN/mature_female")
    a = Assistant(tmp_path / "chat.json", lang=lambda: "en", config=wf.cfg, cfg=lambda: wf.cfg.data, wf=wf, wf_dir=tmp_path / "wfs")
    for q, adj in [("make mom sound older", "older"), ("让妈妈的声音慢一点", "slower")]:
        tool, args, _ = a.offline_intent(q); assert tool == "set_voice" and args == dict(name="妈妈", adjust=adj)
    before = VO.Library().get("妈妈")
    p = a.propose("set_voice", dict(name="妈妈", adjust="older")); assert "pitch" in p["preview"]
    a.execute(p); after = VO.Library().get("妈妈"); assert after["pitch"] < before["pitch"] and after["voice"] == before["voice"]
    p = a.propose("set_voice", dict(name="妈妈", changes=dict(style="sad"))); a.execute(p); assert VO.Library().get("妈妈")["style"] == "sad"
    with pytest.raises(ValueError): a.propose("set_voice", dict(name="妈妈", changes=dict(voice="sk-abcdefghijklmnopqrstuvwxyz0123")))
    assert a.offline_intent("make the video about cats")[0] != "set_voice"

def test_export_shares_voices_without_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wf = loader.build("short_video", str(tmp_path / "config.yaml"), str(tmp_path))
    VO.Library().set("林晚", preset="zh-CN/young_female_gentle", elevenlabs_voice="21m00Tcm4TlvDq8ikWAM")
    doc = PF.export(wf, PF.current(wf.cfg), "cast"); assert doc["voices"]["林晚"]["voice"] == "zh-CN-XiaoyiNeural"
    txt = json.dumps(doc["voices"], ensure_ascii=False); assert "key" not in txt.lower() and "sk-" not in txt
    doc["voices"]["林晚"]["api_key"] = "sk-abcdefghijklmnopqrstuvwxyz0123"
    (tmp_path / "voices" / "characters.yaml").unlink()
    pv = PF.preview(wf, PF.to_code(doc)); assert "api_key" not in pv["voices"]["林晚"]
    VO.Library().merge_in(pv["voices"]); assert VO.Library().get("林晚")["elevenlabs_voice"] == "21m00Tcm4TlvDq8ikWAM"

def test_dashboard_voice_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import threading, urllib.request
    from seatcrew.server import serve
    wf = loader.build("short_video", str(tmp_path / "config.yaml"), str(tmp_path))
    srv = serve(wf, port=0); threading.Thread(target=srv.serve_forever, daemon=True).start(); base = f"http://127.0.0.1:{srv.server_address[1]}"
    def post(p, b):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(base + p, json.dumps(b).encode(), {"Content-Type": "application/json"})).read())
        except urllib.error.HTTPError as e: return json.loads(e.read())
    try:
        st = json.loads(urllib.request.urlopen(base + "/api/voices").read()); assert len(st["presets"]) >= 60 and "sad" in st["styles"]
        r = post("/api/voices/set", dict(name="Dad", preset="en/elderly_man", style="calm")); assert r["ok"] and r["profile"]["voice"] == "en-GB-ThomasNeural"
        assert post("/api/voices/set", dict(name="Dad", rate=500))["ok"] is False
        assert "Dad" in json.loads(urllib.request.urlopen(base + "/api/voices").read())["characters"]
        assert post("/api/voices/delete", dict(name="Dad"))["ok"]
    finally: srv.shutdown()

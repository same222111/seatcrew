"""v0.9.5 stability regressions: hard cuts are real concats, QC catches a short/frozen picture, global --lang, init language,
configurable title cards."""
import json, shutil, subprocess
from pathlib import Path
import pytest
from seatcrew import cli as CLI
from seatcrew.video import editor as ED, qc as QC, ff, storyboard as SB
from seatcrew.video import cli as VCLI
from seatcrew.video.subs import build_ass, caption_layout, caption_style

FF = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg not installed")
COLORS = [(255, 0, 0), (0, 200, 0), (0, 0, 255), (255, 255, 0)]

def _ff(*a): subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, a)], check=True)

def _stream_durs(p):
    d = ff.probe(p); return {s["codec_type"]: float(s["duration"]) for s in d["streams"]}

def _rgb(p, t):
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(p), "-frames:v", "1", "-vf", "scale=1:1:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
    assert len(out) == 3, f"no video frame at {t}s"
    return tuple(out)

def _near(a, b, tol=60): return all(abs(x - y) <= tol for x, y in zip(a, b))

@FF
@pytest.mark.parametrize("trans", ["cut", "mixed"])
def test_cut_is_a_real_concat_every_shot_shows_and_video_matches_audio(tmp_path, trans):
    shots = []
    for i, c in enumerate(COLORS):
        img = tmp_path / f"c{i}.png"; _ff("-f", "lavfi", "-i", "color=c=0x%02x%02x%02x:s=360x640" % c, "-frames:v", 1, img)
        tr = "cut" if trans == "cut" or i % 2 == 0 else "crossfade"
        shots.append(dict(id=f"s{i + 1:02d}", clip=str(img), camera="static", transition=tr, caption="", duration=3.0))
    man = ED.assemble(shots, tmp_path / "out.mp4", tmp_path / "work", size=(180, 320), preset="ultrafast", motion=0.0, captions=False)
    assert all(t == 0 for t, s in zip(man["timeline"]["T"], shots) if s["transition"] == "cut")
    d = _stream_durs(man["output"])
    assert abs(d["video"] - d["audio"]) <= 0.3, d                        # the bug: video stream ended after shot 1
    assert d["video"] >= sum(s["duration"] for s in shots) - 0.3
    for s, c in zip(man["shots"], COLORS):                              # every shot is on screen in its own slot
        assert _near(_rgb(man["output"], s["start"] + s["dur"] / 2), c), (s["id"], c)
    rep = QC.check(man, dict(total_sec=(1, 60)))
    assert next(x for x in rep["checks"] if x["name"] == "av_stream_sync")["ok"]

@FF
def test_qc_fails_when_video_stream_is_shorter_than_audio(tmp_path):
    p = tmp_path / "short_video.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=2", "-f", "lavfi", "-i", "sine=f=440:d=6:sample_rate=48000",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", p)
    rep = QC.check_external(p)
    c = next(x for x in rep["checks"] if x["name"] == "av_stream_sync")
    assert not c["ok"] and not rep["passed"], c

@FF
def test_qc_fails_on_a_frozen_picture(tmp_path):
    img = tmp_path / "still.png"; _ff("-f", "lavfi", "-i", "testsrc2=s=180x320", "-frames:v", 1, img)
    p = tmp_path / "frozen.mp4"
    _ff("-loop", 1, "-i", img, "-f", "lavfi", "-i", "sine=f=440:d=5:sample_rate=48000", "-t", 5, "-r", 30,
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", p)
    rep = QC.check_external(p)
    assert not next(x for x in rep["checks"] if x["name"] == "frozen_frames")["ok"] and not rep["passed"]
    assert next(x for x in rep["checks"] if x["name"] == "av_stream_sync")["ok"]

def test_stream_dur_reads_field_and_mkv_tag():
    assert QC._stream_dur({"duration": "6.8"}) == 6.8
    assert abs(QC._stream_dur({"tags": {"DURATION": "00:00:27.100000000"}}) - 27.1) < 1e-6
    assert QC._stream_dur({}) is None and QC._stream_dur(None) is None

@pytest.mark.parametrize("argv,glob,rest", [
    (["--lang", "zh-CN", "video", "init", "x"], {"lang": "zh-CN"}, ["video", "init", "x"]),
    (["--lang=zh", "video", "init", "x"], {"lang": "zh-CN"}, ["video", "init", "x"]),
    (["run", "wf", "--lang", "zh-CN"], {"lang": "zh-CN"}, ["run", "wf"]),
    (["--env", "a.env", "--lang", "en", "list"], {"env": "a.env", "lang": "en"}, ["list"]),
    (["video", "voices", "--lang", "zh-CN"], {}, ["video", "voices", "--lang", "zh-CN"]),   # subcommand's own --lang stays put
])
def test_global_options_anywhere(argv, glob, rest):
    assert CLI.split_global(argv) == (glob, rest)

def test_unknown_global_lang_is_a_clear_error():
    with pytest.raises(SystemExit): CLI.split_global(["--lang", "xx-YY", "list"])

@pytest.mark.parametrize("argv", [["--lang", "zh-CN", "video", "init", "--template", "dialogue_scene", "--aspect", "9:16", "{d}"],
                                  ["video", "init", "--template", "dialogue_scene", "{d}", "--lang", "zh"],
                                  ["video", "--lang", "zh-CN", "init", "{d}"]])
def test_init_inherits_language_chinese_placeholders(tmp_path, monkeypatch, argv):
    monkeypatch.setenv("LANG", "en_US.UTF-8"); monkeypatch.delenv("SEATCREW_LANG", raising=False); monkeypatch.chdir(tmp_path)
    d = tmp_path / "ep"
    assert CLI.main([x.replace("{d}", str(d)) for x in argv]) == 0
    sb = SB.load_storyboard(d / "storyboard.yaml")
    assert sb["language"] == "zh-CN"
    assert any("\u4e00" <= ch <= "\u9fff" for ch in sb["title"] + sb["shots"][0]["narration"])

def test_init_english_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("LANG", "en_US.UTF-8"); monkeypatch.delenv("SEATCREW_LANG", raising=False); monkeypatch.chdir(tmp_path)
    assert CLI.main(["video", "init", str(tmp_path / "e")]) == 0
    assert SB.load_storyboard(tmp_path / "e" / "storyboard.yaml")["language"] == "en"

def _title_style(ass):
    f = next(l for l in ass.splitlines() if l.startswith("Style: Title,")).split(","); return int(f[2]), int(f[18]), int(f[21])

def test_title_cards_bigger_and_in_top_safe_area_by_default():
    w, h = 1080, 1920
    ass, _ = build_ass([], [(0.1, 2.0, "减肥第一天")], w, h, 3.0)
    size, align, mv = _title_style(ass)
    assert size >= round(h * 0.048) > round(h * 0.036)                  # was h*0.036 (69px): now ~96px
    assert align == 8 and mv <= h * 0.07                                # top-centre, above faces/hands
    assert "减肥第一天" in ass

def test_title_cards_configurable():
    w, h = 1080, 1920
    big = caption_layout(w, h, {"scale": 1.5}); assert big["size"] == round(h * 0.05 * 1.5)
    low = caption_layout(w, h, {"position": "lower"}); assert low["align"] == 2 and low["margin_v"] > h * 0.22
    up = caption_layout(w, h, {"position": "upper"}); assert up["align"] == 8 and up["margin_v"] > caption_layout(w, h)["margin_v"]
    ass, _ = build_ass([], [(0, 1, "Hi")], w, h, 2.0, caption={"position": "lower", "scale": 1.2})
    assert _title_style(ass)[1] == 2
    with pytest.raises(ValueError): caption_style({"position": "middle"})
    with pytest.raises(ValueError): caption_style({"scale": 9})

def test_caption_style_from_storyboard_and_cli_override(tmp_path):
    sb = SB.validate_storyboard({"caption_style": {"position": "upper", "scale": 1.3}, "shots": [{"id": "s01", "narration": "x"}]})
    assert sb["caption_style"] == {"position": "upper", "scale": 1.3}
    with pytest.raises(ValueError): SB.validate_storyboard({"caption_style": "top", "shots": [{"id": "s01"}]})
    class A: caption_position = "lower"; caption_scale = None
    assert VCLI._caption_style(sb, A) == {"position": "lower", "scale": 1.3}


def test_dashboard_snapshot_localizes_seat_activity_and_item_status():
    from seatcrew import logi18n
    snap = {"seats": {"chief": {"last": "- settings saved: language", "status": "idle"}},
            "items": [{"id": 1, "status": "waiting at APPROVE", "chain": []}, {"id": 2, "status": "blocked at POLICY", "chain": []}], "events": []}
    out = logi18n.localize_snapshot(snap, "zh-CN")
    assert out["seats"]["chief"]["last_l"].startswith("-") and "设置已保存" in out["seats"]["chief"]["last_l"]
    st = [i["status_l"] for i in out["items"]]
    assert st[0].startswith("等待") and st[1].startswith("被") and not any(c.isascii() and c.isalpha() and c.islower() for s in st for c in s)

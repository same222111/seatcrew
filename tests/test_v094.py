"""v0.9.4: 6 seats, honest AI choice, rules-mode rewrite tip, shot hint, parallel items/steps/shots/segments, beginner CLI,
edge-tts / silent draft, QC retry cap, Windows code pages, chat language, voice audition error, CJK wrap."""
import io, json, re, shutil, subprocess, sys, threading, time
from pathlib import Path
import pytest
from seatcrew import loader
from seatcrew.video import tts as TTS, visuals as VIS, editor as ED, qc as QC

ROOT = Path(__file__).resolve().parent.parent
FF = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg not installed")
TINY = dict(supersample=1, preset="ultrafast", inter_crf=23)
LONG = "\n".join(["Sunlight looks white but holds every colour.", "Air scatters short blue waves the most.",
                  "So blue reaches your eyes from all over the sky.", "At sunset the light crosses more air.", "That is why sunsets glow orange and red."])

def wf_(tmp_path, **settings):
    wf = loader.build("short_video", str(tmp_path / "config.yaml"), str(tmp_path))
    wf.cfg.data["settings"].update(dict(tts_backend="mock", visuals_backend="mock", allow_draft=False, load_samples=False), **settings)
    wf.size_override = (270, 480); wf.editor_opts = dict(TINY); wf.qc_total = (1, 200); wf.qc_opts = dict(min_sharpness=0.0)
    return wf

def run(wf, **data):
    it = wf.submit(data=dict(dict(topic="Why is the sky blue?", notes=LONG), **data)); wf.run_cycle()
    return next(i for i in wf.items if i["id"] == it["id"])

# ---- 1. six seats, only the first three choose an AI
def test_six_seats_and_ai_honesty(tmp_path):
    wf = wf_(tmp_path); d = wf.definition()
    assert d["chain"] == ["chief", "writer", "scriptcheck", "production", "editqc", "approve"]
    assert [s["name"] for s in d["seats"]] == d["chain"]
    assert {s["name"] for s in d["seats"] if s["uses_ai"]} == {"chief", "writer", "scriptcheck"}
    assert set(wf.steps) == {"voice", "visuals", "lipsync", "editor", "qc"}

@FF
def test_director_checks_brief_and_production_logs_sub_steps(tmp_path):
    wf = wf_(tmp_path); it = run(wf)
    assert "pending" in it, [c["reason"] for c in it["chain"]]
    assert [c["seat"] for c in it["chain"]] == ["chief", "writer", "scriptcheck", "production", "editqc"]
    assert set(it["data"]["steps"]) == {"voice", "visuals", "lipsync", "editor", "qc"} and all(v["ok"] for v in it["data"]["steps"].values())
    bad = run(wf, topic="  "); assert bad["chain"][-1]["seat"] == "chief" and "no topic" in bad["chain"][-1]["reason"]

@FF
def test_qc_send_back_goes_to_owning_seat_and_resumes_sub_step(tmp_path):
    wf = wf_(tmp_path, max_rewrites=1); wf.qc_opts = dict(min_sharpness=1e9)
    it = run(wf)
    assert it["data"]["rounds"] == {"visuals": 1} and "pending" not in it
    acts = [json.loads(x) for x in (tmp_path / "log.jsonl").read_text().splitlines()]
    rw = [a for a in acts if a["kind"] == "REWRITE"]; assert rw and rw[0]["agent"] == "PRODUCTION" and "VISUALS" in rw[0]["msg"]
    # the resume re-ran visuals but not voice
    assert sum(a["agent"] == "VOICE" and a["kind"].startswith("CHECK") for a in acts) == 1
    assert sum(a["agent"] == "VISUALS" and a["kind"].startswith("CHECK") for a in acts) == 2

# ---- 4. rules-mode rewrite stops with an actionable tip; shot hint = real shots
def test_rules_rewrite_stops_with_tip_instead_of_looping(tmp_path):
    wf = wf_(tmp_path); wf.cfg.data["language"] = "zh-CN"
    it = run(wf, topic="天空为什么是蓝色的?", notes="阳光是白色的。\n蓝光散射更多。")
    assert "pending" not in it and not it["data"].get("rounds", {}).get("writer")
    assert "稿子太短" in it["data"]["tip"] and re.search(r"再加约 \d+ 句", it["data"]["tip"])
    blocked = [c for c in it["chain"] if not c["ok"]]; assert len(blocked) == 1      # one BLOCKED, not three identical ones
    wf.cfg.data["language"] = "en"; it = run(wf, notes="Short line.\nAnother.")
    assert "add about" in it["data"]["tip"]

def test_one_line_is_one_shot(tmp_path):
    wf = wf_(tmp_path); W = wf.seat_map["writer"]
    TEMPLATES = type(wf).__init__.__globals__["TEMPLATES"]
    d = dict(topic="t", aspect="9:16", template="knowledge_explainer", notes="Hi.\nShort.\nA third short line.\nFour."); sb = W.from_notes(d, TEMPLATES["knowledge_explainer"], None)
    assert len(sb["shots"]) == 4
    zh = W.from_notes(dict(topic="t", aspect="9:16", template="knowledge_explainer", notes="阳光是白色的。\n蓝光散射更多。\n所以天空是蓝的。"), TEMPLATES["knowledge_explainer"], None)
    assert len(zh["shots"]) == 3
    lab = next(f["label"] for f in wf.submit_fields if f["name"] == "notes"); assert "one line = one shot" in lab

def test_video_tiles_have_no_pass_rate():
    zh = json.loads((ROOT / "examples/short_video/locales/zh-CN.json").read_text(encoding="utf-8"))
    html = (ROOT / "seatcrew/web/studio.js").read_text(encoding="utf-8")
    assert "tile_passrate" not in html and "tile_net" not in html
    assert "v_tile_making" in zh and "通过率" not in json.dumps(zh, ensure_ascii=False)

# ---- 5 + 9. speed: two videos at once, voice || visuals, parallel shots, ordered parallel segments
@FF
def test_two_videos_run_at_the_same_time(tmp_path, monkeypatch):
    wf = wf_(tmp_path); live = {"n": 0, "max": 0}; lock = threading.Lock()
    real = wf.steps["editor"].rules
    def slow(it):
        with lock: live["n"] += 1; live["max"] = max(live["max"], live["n"])
        time.sleep(0.6)
        try: return real(it)
        finally:
            with lock: live["n"] -= 1
    monkeypatch.setattr(wf.steps["editor"], "rules", slow)
    a = wf.submit(data=dict(topic="A", notes=LONG)); b = wf.submit(data=dict(topic="B", notes=LONG)); wf.run_cycle()
    assert live["max"] == 2 and all("pending" in i for i in wf.items if i["id"] in (a["id"], b["id"]))
    wf.cfg.data["settings"]["parallel_items"] = 1; live["max"] = 0
    wf.submit(data=dict(topic="C", notes=LONG)); wf.submit(data=dict(topic="D", notes=LONG)); wf.run_cycle(); assert live["max"] == 1

@FF
def test_item_submitted_during_a_cycle_starts_immediately(tmp_path, monkeypatch):
    wf = wf_(tmp_path); started = []
    real = wf.steps["editor"].rules
    def slow(it):
        started.append((it["data"]["topic"], time.time()))
        if it["data"]["topic"] == "A": wf.submit(data=dict(topic="B", notes=LONG)); time.sleep(1.0)
        return real(it)
    monkeypatch.setattr(wf.steps["editor"], "rules", slow)
    wf.submit(data=dict(topic="A", notes=LONG)); wf.run_cycle()
    assert [t for t, _ in started] == ["A", "B"] and len([i for i in wf.items if "pending" in i]) == 2

def test_voice_and_visuals_run_in_parallel(tmp_path, monkeypatch):
    wf = wf_(tmp_path); spans = {}
    for n in ("voice", "visuals"):
        def fake(it, n=n): t = time.time(); time.sleep(0.4); spans[n] = (t, time.time(), threading.current_thread().name); return True, "ok"
        monkeypatch.setattr(wf.steps[n], "rules", fake)
    monkeypatch.setattr(wf.steps["lipsync"], "rules", lambda it: (True, "off"))
    it = dict(id=1, data={}); t0 = time.time(); ok, why = wf.seat_map["production"].check(it)
    assert ok and time.time() - t0 < 0.75
    (a0, a1, ta), (b0, b1, tb) = spans["voice"], spans["visuals"]; assert a0 < b1 and b0 < a1 and ta != tb

def test_paid_shots_are_generated_in_parallel(tmp_path, monkeypatch):
    wf = wf_(tmp_path, parallel_shots=3); live = {"n": 0, "max": 0}; lock = threading.Lock()
    def make(sh, work, aspect, **k):
        with lock: live["n"] += 1; live["max"] = max(live["max"], live["n"])
        time.sleep(0.3)
        with lock: live["n"] -= 1
        p = Path(work) / f"{sh['id']}.png"; p.write_bytes(b"x"); return p, dict(backend="kling")
    monkeypatch.setattr(VIS, "make", make)
    shots = [dict(id=f"s{i:02d}", narration="x", caption="", visual="v", camera="push_in", transition="cut", duration=3) for i in range(1, 6)]
    it = dict(id=7, data=dict(template="knowledge_explainer", aspect="9:16", storyboard=dict(shots=shots)))
    t0 = time.time(); ok, why = wf.steps["visuals"].rules(it)
    assert ok and live["max"] == 3 and time.time() - t0 < 1.2 and [s["id"] for s in shots] == ["s01", "s02", "s03", "s04", "s05"]

def test_draft_render_uses_veryfast_and_parallel_segments(tmp_path, monkeypatch):
    wf = wf_(tmp_path); wf.editor_opts = {}; seen = {}
    monkeypatch.setattr(ED, "assemble", lambda *a, **k: seen.update(k) or (_ for _ in ()).throw(ValueError("stop")))
    monkeypatch.setitem(type(wf).__init__.__globals__, "have_ffmpeg", lambda: True)
    shots = [dict(id="s01", clip_path="x.png", camera="push_in", transition="cut", caption="", duration=2)]
    it = dict(id=3, data=dict(template="knowledge_explainer", aspect="9:16", storyboard=dict(shots=shots), voice=dict(draft=True)))
    wf.steps["editor"].rules(it)
    assert seen["preset"] == "veryfast" and seen["workers"] >= 2
    it["data"]["voice"]["draft"] = False; wf.steps["editor"].rules(it); assert seen["preset"] == "slow"

@FF
def test_parallel_segments_keep_order(tmp_path):
    from seatcrew.video import ff
    clips = []
    for i, c in enumerate(("red", "lime", "blue")):
        p = tmp_path / f"c{i}.png"; ff.run(["-f", "lavfi", "-i", f"color=c={c}:s=270x480", "-frames:v", "1", str(p)]); clips.append(p)
    shots = [dict(id=f"s{i}", clip=str(p), camera="static", transition="cut", caption="", duration=1.0) for i, p in enumerate(clips)]
    man = ED.assemble(shots, tmp_path / "o.mp4", tmp_path / "w", size=(270, 480), captions=False, workers=3, **TINY)
    assert [Path(s["seg"]).name for s in man["shots"]] == ["seg00.mp4", "seg01.mp4", "seg02.mp4"]
    assert [s["source"] for s in man["shots"]] == ["c0.png", "c1.png", "c2.png"]

# ---- 6. beginners
@FF
def test_cli_first_run_makes_a_draft_without_flags_and_no_placeholders(tmp_path, monkeypatch):
    from seatcrew.video.cli import main, default_lang
    assert default_lang({"LANG": "zh_CN.UTF-8"}) == "zh-CN" and default_lang({"LANG": "en_US.UTF-8"}) == "en"
    d = tmp_path / "v"; monkeypatch.setenv("LANG", "zh_CN.UTF-8"); monkeypatch.delenv("LC_ALL", raising=False); monkeypatch.delenv("SEATCREW_LANG", raising=False)
    assert main(["init", str(d)]) == 0
    sb = (d / "storyboard.yaml").read_text(encoding="utf-8"); assert not re.search(r"(narration|visual|caption): .*<", sb) and "language: zh-CN" in sb and "天空" in sb
    monkeypatch.setattr(ED, "DEFAULTS", dict(ED.DEFAULTS, supersample=1)); monkeypatch.setattr(TTS, "auto_order", lambda pref="auto": ["mock"])
    main(["assemble", str(d), "--preset", "ultrafast"])                       # no --allow-draft
    assert (d / "final_DRAFT.mp4").is_file()
    (d / "storyboard.yaml").write_text(sb.replace("阳光看起来是白色的，其实混合了所有颜色。", "<hook: one short spoken sentence>", 1), encoding="utf-8")
    assert main(["assemble", str(d)]) == 1                                     # a placeholder is never spoken

def test_placeholders_blocked_by_scriptcheck(tmp_path):
    wf = wf_(tmp_path); it = run(wf, notes="<hook: one short spoken sentence>\n" + LONG)
    assert "pending" not in it and "placeholder" in it["data"]["tip"]

def test_chinese_users_get_chinese_sample(tmp_path):
    (tmp_path / "config.yaml").write_text("language: zh-CN\nsettings:\n  load_samples: true\n", encoding="utf-8")
    wf = loader.build("short_video", str(tmp_path / "config.yaml"), str(tmp_path))
    assert wf.inbox and "天空" in wf.inbox[0]["data"]["topic"]
    from seatcrew.assistant import sample_for
    assert "天空" in sample_for(wf, "zh-CN")["topic"] and "sky" in sample_for(wf, "en")["topic"]

# ---- 7. edge-tts / silent draft / QC retry cap
def test_edge_tts_is_a_default_dependency():
    txt = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    deps = re.search(r"^dependencies = \[(.*?)\]", txt, re.M).group(1); assert "edge-tts" in deps

@FF
def test_silent_chinese_draft_passes_as_draft_without_retries(tmp_path):
    wf = wf_(tmp_path, tts_backend="draft", visuals_backend="draft", allow_draft=True); wf.cfg.data["language"] = "zh-CN"
    it = run(wf, topic="天空为什么是蓝色的?", notes="阳光看起来是白色的，其实混合了所有颜色。\n空气分子更容易散射波长短的蓝光。\n所以无论你看向天空哪里，都有蓝光进入眼睛。\n傍晚时阳光要穿过更厚的空气。\n所以晚霞是橙色和红色的。")
    assert "pending" in it, [c["reason"] for c in it["chain"]]
    assert not it["data"].get("rounds") and it["data"]["voice"]["silent"] and "edge-tts" in it["data"]["steps"]["voice"]["reason"]
    vp = next(c for c in it["data"]["qc"]["checks"] if c["name"] == "voice_present"); assert vp["severity"] == "warn"

def test_qc_retries_are_capped_in_total(tmp_path, monkeypatch):
    wf = wf_(tmp_path, max_rewrites=5, max_total_rewrites=2); n = {"qc": 0}
    for s in ("voice", "visuals", "lipsync", "editor"): monkeypatch.setattr(wf.steps[s], "rules", lambda it: (True, "ok"))
    def qc(it):
        n["qc"] += 1; it["_back"] = ["voice", "editor", "visuals"][n["qc"] % 3]; return False, "FAIL"
    monkeypatch.setattr(wf.steps["qc"], "rules", qc)
    it = run(wf); assert sum(it["data"]["rounds"].values()) == 2 and n["qc"] == 3

def test_futile_voice_retry_stops_with_install_tip(tmp_path, monkeypatch):
    wf = wf_(tmp_path); wf.cfg.data["language"] = "zh-CN"
    monkeypatch.setattr(wf.steps["voice"], "rules", lambda it: (it["data"].setdefault("voice", {}).update(silent=True) or True, "silent"))
    for s in ("visuals", "lipsync", "editor"): monkeypatch.setattr(wf.steps[s], "rules", lambda it: (True, "ok"))
    monkeypatch.setattr(wf.steps["qc"], "rules", lambda it: (it.update(_back="voice") or False, "FAIL -> VOICE"))
    it = run(wf); assert not it["data"].get("rounds") and "pip install edge-tts" in it["data"]["tip"]

# ---- 8. Windows code pages
def test_cli_survives_cp1252_redirect(tmp_path):
    env = dict(__import__("os").environ, PYTHONIOENCODING="cp1252", PYTHONPATH=str(ROOT))
    r = subprocess.run([sys.executable, "-m", "seatcrew", "--lang", "zh-CN", "run", "support_triage", "--yes", "--state", str(tmp_path / "s"), "--config", str(tmp_path / "c.yaml")],
                       capture_output=True, cwd=str(tmp_path), env=env, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-500:]
    assert "通过" in r.stdout.decode("utf-8")

def test_utf8_stdio_reconfigures_any_code_page():
    from seatcrew.textio import utf8_stdio
    buf = io.BytesIO(); w = io.TextIOWrapper(buf, encoding="cp437"); old = sys.stdout; sys.stdout = w
    try: utf8_stdio(); print("中文 · →"); sys.stdout.flush()
    finally: sys.stdout = old
    assert "中文 · →" in buf.getvalue().decode("utf-8")

def test_every_text_subprocess_has_an_explicit_encoding():
    bad = []
    for p in list((ROOT / "seatcrew").rglob("*.py")) + list((ROOT / "examples").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")):
        src = p.read_text(encoding="utf-8")
        for m in re.finditer(r"(subprocess\.(?:run|Popen|check_output)|runner)\((.*?)\)\s*(?:\.stdout|$|\n)", src, re.S):
            call = m.group(0)
            if ("text=True" in call or "universal_newlines" in call) and "encoding=" not in call: bad.append(f"{p.name}: {call[:80]}")
        if ".decode()" in src and "subprocess" in src: bad.append(f"{p.name}: bare .decode()")
    assert not bad, bad
    for f in ("seatcrew/cli.py", "seatcrew/video/cli.py", "seatcrew/desktop.py", "examples/trading/tradecrew/cli.py"):
        assert "utf8_stdio()" in (ROOT / f).read_text(encoding="utf-8"), f

# ---- 10. chat language, audition error, CJK punctuation wrap
def test_chief_answers_chinese_questions_in_chinese(tmp_path):
    from seatcrew.assistant import Assistant
    a = Assistant(tmp_path / "chat.json", ctx=dict(lang=lambda: "en"))
    out = a.send("谁决定什么?")["messages"]; txt = " ".join(m["text"] for m in out if m["role"] == "chief")
    assert re.search(r"[\u4e00-\u9fff]", txt) and "Who decides" not in txt
    out = a.send("who decides?")["messages"]; txt = " ".join(m["text"] for m in out if m["role"] == "chief"); assert "Who decides" in txt or "decide" in txt.lower()

def test_audition_narrator_works_and_unknown_name_is_readable(tmp_path, monkeypatch):
    from seatcrew.video import voices as VO
    lib = VO.Library(tmp_path / "characters.yaml")
    with pytest.raises(ValueError, match="未找到角色"): VO.audition_file(lib, "nobody", None, "你好", None, "zh-CN")
    with pytest.raises(ValueError, match="no character named"): VO.audition_file(lib, "nobody", None, "hi", None, "en")
    seen = {}
    monkeypatch.setattr(VO, "audition", lambda prof, out, txt, lg, emo: (seen.update(prof=prof) or (_ for _ in ()).throw(RuntimeError("stop"))))
    with pytest.raises(RuntimeError): VO.audition_file(lib, "narrator", None, "你好", None, "zh-CN")
    assert "narrator" in str(seen["prof"].get("preset"))

def test_cjk_wrap_never_starts_a_line_with_punctuation():
    from seatcrew.video.visuals import wrap_cjk
    for n in range(2, 12):
        lines = wrap_cjk("天空为什么是蓝色的?", n); assert "".join(lines) == "天空为什么是蓝色的?"
        assert all(l[0] not in "?？。，" for l in lines)
    assert wrap_cjk("天空为什么是蓝色的?", 9) == ["天空为什么是蓝色的?"]


# ---- v0.9.4 round 2: translated log / QC, workflow label, subtitle line breaks ----
def test_log_lines_translate_for_display_only():
    from seatcrew import logi18n as LI
    msgs = ["cycle 3 start", "cycle 2: 0 passed, 0 blocked, 1 waiting / 1", "1 new item(s)", "settings saved: language",
            "[天空] #1 5 shots, ~24s (template)", "[天空] #1 readable, safe words, ~24s", "#1 PASS [DRAFT] · 13/14 checks",
            "[天空] #1 waiting for a human to approve", "#2 sent back to WRITER (round 1): total ~5s outside 8-60s",
            "#1 voice edge voice, exact word timing · visuals draft×5 · DRAFT · lipsync off (shots keep their original mouths)"]
    for m in msgs:
        z = LI.text(m, "zh-CN")
        assert re.search(r"[\u4e00-\u9fff]", z) and not re.search(r"\b(cycle|passed|shots|readable|waiting|sent|round|voice|visuals|lipsync|checks)\b", z), (m, z)
    assert LI.text("cycle 3 start", "zh-TW") == "第 3 輪開始" and LI.kind("CHECK_OK", "zh-CN") == "通过" and LI.text("cycle 3 start", "en") == "cycle 3 start"
    assert LI.text("cycle 3 start", "es").startswith("inicio") and LI.text("cycle 3 start", "ja").startswith("サイクル")
    ev = [dict(agent="CHIEF", kind="CYCLE", sym="-", msg="cycle 1 start", ts="2026-01-01T00:00:00")]
    snap = LI.localize_snapshot(dict(events=ev, items=[]), "zh-CN")
    assert snap["events"][0]["msg_l"] == "第 1 轮开始" and snap["events"][0]["agent_l"] == "导演" and "msg_l" not in ev[0]

def test_qc_details_translate():
    from seatcrew import logi18n as LI
    for d in ["25.8s (planned 25.7s, allowed 10-108s)", "all sources >= 66% of output", "every clip covers its shot", "none", "-14.0 LUFS (target -14 +-1)",
              "true peak -1.5 dBTP (max -1)", "narration audible", "no gap > 1.6s", "100% of subtitle words start on speech", "1 character(s), one voice each",
              "DRAFT PREVIEW - offline voice/visuals; not final quality", "FAIL -> VOICE: voice_present: voice track is silent"]:
        z = LI.text(d, "zh-CN"); assert re.search(r"[\u4e00-\u9fff]", z) and not re.search(r"\b(of|shot|target|max|gap|words|offline|final|silent|voice)\b", z), (d, z)

def test_workflow_label_is_translated():
    for l, want in {"zh-CN": "短视频", "zh-TW": "短影音", "en": "Short video"}.items():
        j = json.loads((ROOT / f"examples/short_video/locales/{l}.json").read_text(encoding="utf-8")); assert j["wf_label"] == want

def _zh_words(text, step=0.3):
    import re as _re
    toks = _re.findall(r"[\u4e00-\u9fff]{1,2}|[，。？！、；：]", text)
    return [dict(w=t, start=i * step, end=i * step + step * .9, shot="s1") for i, t in enumerate(toks)]

@pytest.mark.parametrize("seg", ["jieba", "none"])
def test_subtitles_break_on_punctuation_and_balance(seg, monkeypatch):
    from seatcrew.video import subs as SU
    from seatcrew.video.subs import chunk, NO_START
    if seg == "none": monkeypatch.setattr(SU, "_jieba", None)
    elif SU._jieba is None: pytest.skip("jieba not installed")
    L = dict(max_chars=16, max_cjk=10)
    text = "空气分子更容易散射波长短的蓝光，红光则很少被散射。所以无论你看向天空哪里，都有蓝光进入眼睛。天空为什么是蓝色的？这就是为什么晚霞是橙红色的。"
    lines = ["".join(x["w"] for x in g) for g in chunk(_zh_words(text), L)]
    assert "".join(lines) == text
    for t in lines:
        assert t[0] not in NO_START, lines                      # no punctuation at a line start
        assert len(t.strip("，。？！、；：")) >= 3, lines          # no lone ? / 。 or 1-2 char orphan
        assert len(t) <= L["max_cjk"] + 1, lines
    assert any(t.endswith("？") for t in lines) and "蓝光，" in "".join(lines)
    # a long clause splits into even halves (not 10 + 2)
    g = chunk(_zh_words("傍晚时阳光要穿过更厚的空气层才能到达"), L); n = [len("".join(x["w"] for x in l)) for l in g]
    assert len(n) == 2 and max(n) - min(n) <= 2, n

def test_separate_punctuation_tokens_glue_to_previous_word():
    from seatcrew.video.subs import chunk
    ws = [dict(w=w, start=i * .3, end=i * .3 + .25, shot=0) for i, w in enumerate(["天空", "为什么", "是", "蓝色", "的", "？"])]
    g = chunk(ws, dict(max_chars=16, max_cjk=10)); assert ["".join(x["w"] for x in l) for l in g] == ["天空为什么是蓝色的？"]

def test_cjk_title_is_wrapped_by_hand_without_auto_wrap():
    from seatcrew.video.subs import build_ass, wrap_title, NO_START
    w = wrap_title("为什么天空是蓝色的？晚霞又为什么是红的？", 9).split("\n")
    assert len(w) >= 2 and all(x[0] not in NO_START for x in w) and max(map(len, w)) - min(map(len, w)) <= 3, w
    ass, cues = build_ass(_zh_words("天空为什么是蓝色的？"), [(0, 2, "为什么天空是蓝色的？晚霞又为什么是红的？")], 1080, 1920, 3.0)
    assert "\\q2" in ass and "\\N" in ass and all(not c["text"].startswith("？") for c in cues)

def test_per_character_tokens_break_between_words(monkeypatch):
    """edge-tts gives one token per Chinese character; with jieba a line never splits a word like 散射 / 穿过."""
    from seatcrew.video import subs as SU
    if SU._jieba is None: pytest.skip("jieba not installed")
    t = "空气分子更容易散射波长短的蓝光，傍晚时阳光要穿过更厚的空气，那么，为什么晚霞是橙红色的呢？"
    ws = [dict(w=c, start=i * .2, end=i * .2 + .18, shot=0) for i, c in enumerate(t)]
    lines = ["".join(x["w"] for x in g) for g in SU.chunk(ws, dict(max_chars=16, max_cjk=10))]
    joined = "|".join(lines)
    for w in ("散射", "穿过", "晚霞", "蓝光"): assert w in joined.replace("|", "") and w[0] + "|" + w[1] not in joined, lines
    assert not any(l in ("那么，", "？") for l in lines), lines


# ---- round 3: localized draft banner + shared word-aware line breaking ----
def test_draft_banner_follows_video_language():
    from seatcrew.video import editor as ED
    assert ED.banner_text("zh-CN") == "草稿预览 · 非成品画质"
    assert ED.banner_text("zh-TW") == "草稿預覽 · 非成品畫質"
    assert ED.banner_text("ja").startswith("下書き")
    assert ED.banner_text("es") == "BORRADOR - CALIDAD NO FINAL"
    assert ED.banner_text("en") == ED.banner_text(None) == "DRAFT PREVIEW - NOT FINAL QUALITY"
    assert ED.banner_text("en", "天空为什么是蓝色的") == "草稿预览 · 非成品画质"   # spoken text wins over a wrong config
    assert ED.banner_text("zh-CN", "空はなぜ青いの") .startswith("下書き")
    assert ED.banner_text("xx") == ED.DRAFT_BANNER["en"]

def test_draft_banner_burned_from_textfile(tmp_path, monkeypatch):
    from seatcrew.video import editor as ED
    src = open(ED.__file__, encoding="utf-8").read()
    assert "textfile=banner.txt" in src and "text='DRAFT PREVIEW" not in src

def test_break_text_keeps_words_and_punctuation():
    import pytest
    from seatcrew.video import subs
    if subs._jieba is None: pytest.skip("jieba not installed")
    for per in (5, 6, 7, 8, 9, 10):
        lines = subs.break_text("那么，为什么晚霞是橙红色的呢？", per)
        assert "".join(lines) == "那么，为什么晚霞是橙红色的呢？"
        assert any("橙红色" in l for l in lines), (per, lines)
        assert all(l[0] not in subs.NO_START for l in lines), lines
        assert lines[-1] != "？" and "呢？" in lines[-1]
        if per >= 9: assert lines[0] != "那么，", lines
    lines = subs.break_text("天空为什么是蓝色的？因为空气散射蓝光更多。", 8)
    assert lines[1].endswith("？") and lines[2].startswith("因为")

def test_break_text_latin_and_max_lines():
    from seatcrew.video.subs import break_text
    lines = break_text("Why is the sky blue? Because air scatters blue light more than red light.", 28)
    assert all(len(l) <= 28 for l in lines) and " ".join(lines).split() == "Why is the sky blue? Because air scatters blue light more than red light.".split()
    assert lines[0] == "Why is the sky blue?"
    assert len(break_text("一二三四五六七八九十" * 6, 6, max_lines=4)) == 4

def test_wrap_title_and_draft_card_share_breaker(tmp_path, monkeypatch):
    from seatcrew.video import subs, visuals
    assert subs.wrap_title("那么，为什么晚霞是橙红色的呢？", 9).split("\n") == subs.break_text("那么，为什么晚霞是橙红色的呢？", 9)
    calls = []
    monkeypatch.setattr(visuals.ff, "run", lambda *a, **k: calls.append(a))
    visuals.draft_card(dict(id="s9", caption="那么，为什么晚霞是橙红色的呢？"), tmp_path, "9:16", size=(1080, 1920))
    card = (tmp_path / "s9.card.txt").read_text(encoding="utf-8").split("\n")
    assert any("橙红色" in l for l in card) and all(l[0] not in subs.NO_START for l in card) and calls

"""Docs and locale files must not mix languages (English docs: no Chinese; Chinese docs/locales: no stray English)."""
import importlib.util, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lang_purity", ROOT / "scripts" / "lang_purity.py")
lp = importlib.util.module_from_spec(spec); spec.loader.exec_module(lp)

def test_repo_docs_and_locales_are_language_pure():
    probs = lp.scan()
    assert not probs, "\n".join(f"{f}:{w}: {why} | {t}" for f, w, why, t in probs[:30])

def test_scanner_catches_mixed_strings(tmp_path):
    (tmp_path / "docs").mkdir(); (tmp_path / "seatcrew" / "locales").mkdir(parents=True)
    (tmp_path / "README.md").write_text("# Demo\nEach seat owns one job (八席).\n", encoding="utf-8")
    (tmp_path / "README.zh-CN.md").write_text("# 演示\n这是 the best workflow 工具，运行 `seatcrew ui demo`。\n", encoding="utf-8")
    (tmp_path / "seatcrew" / "locales" / "zh-CN.json").write_text(json.dumps({"a": "等待 approval", "b": "SeatCrew 已就绪 {n}", "c": "AI 席位"}), encoding="utf-8")
    (tmp_path / "seatcrew" / "locales" / "en.json").write_text(json.dumps({"a": "Waiting", "b": "就绪"}), encoding="utf-8")
    got = {(f, str(w)) for f, w, _, _ in lp.scan(tmp_path)}
    assert ("README.md", "2") in got and ("README.zh-CN.md", "2") in got
    assert ("seatcrew/locales/zh-CN.json", "a") in got and ("seatcrew/locales/en.json", "b") in got
    assert ("seatcrew/locales/zh-CN.json", "b") not in got and ("seatcrew/locales/zh-CN.json", "c") not in got   # names, ids, placeholders ok

def test_language_switch_links_are_allowed(tmp_path):
    (tmp_path / "README.md").write_text("# X\n\n[English](README.md) · [简体中文](README.zh-CN.md)\n", encoding="utf-8")
    assert lp.scan(tmp_path) == []

def test_scanner_catches_untranslated_option_values_and_subjects(tmp_path):
    ex = tmp_path / "examples" / "content_review"; (ex / "locales").mkdir(parents=True)
    (ex / "workflow.yaml").write_text("submit:\n  - {name: speed, type: select, options: [auto, slow]}\n", encoding="utf-8")
    full = {"opt_auto": "x", "opt_slow": "x", "subj_post": "x"}
    for l in lp.UI_LANGS: (ex / "locales" / f"{l}.json").write_text(json.dumps(full), encoding="utf-8")
    assert lp.scan_options(tmp_path) == []
    (ex / "locales" / "zh-CN.json").write_text(json.dumps({"opt_auto": "自动"}), encoding="utf-8")
    (ex / "locales" / "es.json").unlink()
    got = {f: why for f, _, why, _ in lp.scan_options(tmp_path)}
    assert "opt_slow" in got["examples/content_review/locales/zh-CN.json"] and "subj_post" in got["examples/content_review/locales/zh-CN.json"]
    assert got["examples/content_review/locales/es.json"] == "missing locale file"

def test_every_real_option_value_is_translated():
    assert lp.scan_options() == []

def test_scanner_catches_unlabelled_settings(tmp_path, monkeypatch):
    ex = tmp_path / "examples" / "demo"; (ex / "locales").mkdir(parents=True)
    for l in lp.UI_LANGS: (ex / "locales" / f"{l}.json").write_text(json.dumps({"set_min_words": "x"}), encoding="utf-8")
    monkeypatch.setattr(lp, "_settings", lambda e: (["min_words", "parallel_items"], None))
    got = lp.scan_options(tmp_path)
    assert len(got) == len(lp.UI_LANGS) and all("set_parallel_items" in why and "set_min_words" not in why for _, _, why, _ in got)

def test_ja_es_locales_do_not_hardcode_the_chief_seat_name():
    for l in ("ja", "es"):
        d = json.loads((ROOT / "seatcrew" / "locales" / f"{l}.json").read_text(encoding="utf-8"))
        assert not [k for k, v in d.items() if isinstance(v, str) and "CHIEF" in v]

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

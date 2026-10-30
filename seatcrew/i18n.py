"""Tiny i18n: JSON files per language. English is the fallback for any missing key.
Core UI strings live in seatcrew/locales/; a workflow may ship its own locales/ folder that overrides/extends them.
Add a language: copy locales/en.json to locales/<code>.json, translate the values, add <code> to config.LANGUAGES."""
import json
from pathlib import Path
CORE = Path(__file__).parent / "locales"

def _read(d, code):
    f = Path(d) / f"{code}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() and f.resolve().parent == Path(d).resolve() else {}

def load(code, extra_dirs=()):
    """Merged dict: core en < workflow en < core <code> < workflow <code>. Path traversal in `code` is ignored."""
    out = {}
    for c in ("en", code):
        for d in (CORE, *extra_dirs): out.update(_read(d, c))
    return out

def t(key, code="en", extra_dirs=(), **kw):
    s = load(code, tuple(extra_dirs)).get(key, key)
    return s.format(**kw) if kw else s

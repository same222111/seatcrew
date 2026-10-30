"""Tiny i18n: tradecrew/locales/<code>.json. English is the fallback for any missing key.
Add a language: copy locales/en.json to locales/<code>.json, translate the values, add <code> to config.LANGUAGES."""
import json
from functools import lru_cache
from pathlib import Path
DIR = Path(__file__).parent / "locales"

@lru_cache(None)
def load(code):
    en = json.loads((DIR / "en.json").read_text(encoding="utf-8"))
    f = DIR / f"{code}.json"
    if code != "en" and f.exists() and f.resolve().parent == DIR.resolve(): en.update(json.loads(f.read_text(encoding="utf-8")))
    return en

def t(key, code="en", **kw):
    s = load(code).get(key, key)
    return s.format(**kw) if kw else s

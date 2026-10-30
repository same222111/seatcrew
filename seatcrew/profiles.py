"""Named, shareable settings profiles for any workflow.

A profile = the user-editable part of a workflow's config (seat AI assignments, prompts, thresholds,
workflow params, display options) - never API keys or other secrets.

* saved locally as  workflows/<workflow>/profiles/<name>.yaml  (relative to the data folder)
* exported as one share file (.seatcrew.json) or a compact share code ("SC1." + base64) for chat
* imported with preview (validation, warnings, list of changes) and explicit confirm"""
import base64, copy, datetime, json, re, zlib
from pathlib import Path
import yaml
from . import __version__
from .config import merge

SCHEMA = 1
CODE_PREFIX = "SC1."
EXCLUDE = {"setup_complete", "broker"}                     # machine state / safety locks, never shared
DISPLAY_DEFAULTS = {"theme": "dark", "font_size": 13, "density": "normal", "animations": True, "simple": True}
THEMES, DENSITIES = ("dark", "light", "contrast"), ("compact", "normal", "comfy")
NAME_RE = re.compile(r"[\w\- ]{1,40}")
SECRET_KEY_RE = re.compile(r"(api[_-]?key|secret|token|password|passwd|credential|private[_-]?key|authorization|bearer)", re.I)
SECRET_VAL_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{12,}|sk-ant-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|xox[abpr]-[A-Za-z0-9\-]{10,}|xai-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,})")

def validate_display(d):
    if d.get("theme") not in THEMES: raise ValueError(f"display.theme must be one of {THEMES}")
    if d.get("density") not in DENSITIES: raise ValueError(f"display.density must be one of {DENSITIES}")
    fs = d.get("font_size")
    if not isinstance(fs, (int, float)) or isinstance(fs, bool) or not 10 <= fs <= 22: raise ValueError("display.font_size must be 10-22")
    if not isinstance(d.get("animations", True), bool): raise ValueError("display.animations must be true or false")
    if not isinstance(d.get("simple", True), bool): raise ValueError("display.simple must be true or false")

def strip_secrets(obj, path="", removed=None):
    """Copy of obj without secret-looking keys/values. Env-var NAMES (key_env: OPENAI_API_KEY) are kept."""
    removed = [] if removed is None else removed
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if SECRET_KEY_RE.search(str(k)) and not str(k).endswith("_env"): removed.append(p); continue
            out[k] = strip_secrets(v, p, removed)
        return out
    if isinstance(obj, list): return [strip_secrets(v, f"{path}[{i}]", removed) for i, v in enumerate(obj)]
    if isinstance(obj, str) and SECRET_VAL_RE.search(obj): removed.append(path); return SECRET_VAL_RE.sub("<removed>", obj)
    return obj

def keys(cfg): return [k for k in cfg.defaults if k not in EXCLUDE]
def current(cfg): return strip_secrets({k: copy.deepcopy(cfg.data[k]) for k in keys(cfg)})
def defaults(cfg): return strip_secrets({k: copy.deepcopy(cfg.defaults[k]) for k in keys(cfg)})

def clean(cfg, data):
    """Validate a profile body against this workflow. Returns (clean_data, warnings); raises ValueError if invalid."""
    if not isinstance(data, dict): raise ValueError("profile data must be an object")
    warnings, removed = [], []
    data = strip_secrets(data, removed=removed)
    if removed: warnings.append("removed secret-looking fields: " + ", ".join(removed))
    allowed = set(keys(cfg)); unknown = [k for k in data if k not in allowed]
    if unknown: warnings.append("ignored unknown settings: " + ", ".join(map(str, unknown)))
    data = {k: v for k, v in data.items() if k in allowed}
    if "seats" in data:
        bad = [s for s in data["seats"] if s not in cfg.defaults["seats"]]
        if bad: warnings.append("ignored unknown seats: " + ", ".join(bad)); data["seats"] = {k: v for k, v in data["seats"].items() if k not in bad}
    trial = merge(cfg.data, data)
    try: cfg.validate(trial)
    except (KeyError, TypeError) as e: raise ValueError(f"invalid profile: {e}")
    return data, warnings

def folder(wf_name):
    d = Path("workflows") / wf_name / "profiles"; return d

def _path(wf_name, name):
    if not isinstance(name, str) or not NAME_RE.fullmatch(name.strip()) or name.strip().startswith("."): raise ValueError("profile name: 1-40 letters, digits, space, - or _")
    return folder(wf_name) / f"{name.strip()}.yaml"

def list_profiles(wf_name):
    d = folder(wf_name); return sorted(p.stem for p in d.glob("*.yaml")) if d.is_dir() else []

def save(wf, name, data):
    data, warnings = clean(wf.cfg, data); p = _path(wf.name, name); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"); return warnings

def read(wf, name):
    p = _path(wf.name, name)
    if not p.exists(): raise ValueError(f"no profile {name}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

def delete(wf, name):
    p = _path(wf.name, name)
    if p.exists(): p.unlink()

def apply(wf, data):
    data, warnings = clean(wf.cfg, data)
    new = merge(wf.cfg.data, data)
    for k, v in data.items():                    # lists/dicts in a profile replace, not merge, so removed entries stay removed
        if isinstance(v, list): new[k] = copy.deepcopy(v)
    wf.cfg.validate(new); wf.cfg.data = new; wf.cfg.save(); return warnings

def reset(wf):
    keep = {k: copy.deepcopy(wf.cfg.data[k]) for k in EXCLUDE if k in wf.cfg.data}
    new = merge(copy.deepcopy(wf.cfg.defaults), keep); wf.cfg.validate(new); wf.cfg.data = new; wf.cfg.save()

def export(wf, data, name="shared", author=""):
    data, _ = clean(wf.cfg, data)
    doc = {"seatcrew_profile": SCHEMA, "workflow": wf.name, "name": name or "shared", "author": (author or "")[:80],
           "app_version": __version__, "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "data": data}
    return doc

def to_code(doc):
    raw = zlib.compress(json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode(), 9)
    return CODE_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")

def parse(text):
    """Share code, JSON or YAML -> share document. Raises ValueError with a readable message."""
    t = (text or "").strip()
    if not t: raise ValueError("empty input")
    if len(t) > 500_000: raise ValueError("too large")
    if t.startswith(CODE_PREFIX):
        try:
            b = t[len(CODE_PREFIX):]; doc = json.loads(zlib.decompress(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)), bufsize=1 << 16))
        except Exception: raise ValueError("share code is damaged or incomplete")
    else:
        try: doc = json.loads(t)
        except json.JSONDecodeError:
            try: doc = yaml.safe_load(t)
            except yaml.YAMLError: raise ValueError("not a SeatCrew share file, JSON, YAML or share code")
    if not isinstance(doc, dict) or "seatcrew_profile" not in doc or not isinstance(doc.get("data"), dict): raise ValueError("not a SeatCrew profile (missing seatcrew_profile/data)")
    return doc

def preview(wf, text):
    """What importing would do. Never changes anything."""
    doc = parse(text); warnings = []
    try: schema = int(doc["seatcrew_profile"])
    except (TypeError, ValueError): raise ValueError("bad schema version")
    if schema > SCHEMA: raise ValueError(f"made with a newer SeatCrew (profile schema {schema}, this app reads up to {SCHEMA}) - please update the app")
    if doc.get("workflow") != wf.name: raise ValueError(f"this profile is for workflow '{doc.get('workflow')}', not '{wf.name}'")
    if doc.get("app_version") and str(doc["app_version"]).split(".")[:2] != __version__.split(".")[:2]:
        warnings.append(f"made with SeatCrew {doc['app_version']} (you have {__version__}); unknown fields will be ignored")
    data, w2 = clean(wf.cfg, doc["data"]); warnings += w2
    changes = []
    def walk(a, b, p):
        if isinstance(b, dict) and isinstance(a, dict):
            for k in b: walk(a.get(k), b[k], f"{p}.{k}" if p else k)
        elif a != b: changes.append({"path": p, "from": a, "to": b})
    walk(current(wf.cfg), data, "")
    return {"ok": True, "name": str(doc.get("name") or "imported")[:40], "author": str(doc.get("author") or ""), "workflow": doc.get("workflow"),
            "app_version": doc.get("app_version"), "created": doc.get("created"), "warnings": warnings, "changes": changes[:200], "n_changes": len(changes), "data": data}

def safe_name(s):
    s = re.sub(r"[^\w\- ]", "", str(s or ""))[:40].strip(); return s or "imported"

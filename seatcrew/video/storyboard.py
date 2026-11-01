"""Storyboard / shot-list format (YAML or JSON). This is what the EDITOR consumes - see docs/VIDEO.md.

title: My video
aspect: "9:16"            # 9:16 -> 1080x1920 (default)   16:9 -> 1920x1080
language: en              # subtitles / TTS language
template: knowledge_explainer
shots:
  - id: s01               # file stem for clips: clips/s01.mp4 | .mov | .png | .jpg | .webp
    narration: "Spoken text for this shot."   # TTS + karaoke subtitles
    duration: 4.0         # planned seconds (stretched to fit the narration + 0.3s)
    caption: "HOOK TEXT"  # optional big on-screen title (top safe area)
    visual: "prompt for the AI image / video generator"
    camera: push_in       # push_in pull_out pan_left pan_right pan_up pan_down static (stills only)
    transition: crossfade # into the next shot: crossfade | fade_black | cut
"""
import json, re
from pathlib import Path
import yaml

SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
CAMERAS = ("push_in", "pull_out", "pan_left", "pan_right", "pan_up", "pan_down", "static")
TRANSITIONS = ("crossfade", "fade_black", "cut")
ID_RE = re.compile(r"[A-Za-z0-9_\-]{1,40}")

def load_storyboard(path):
    t = Path(path).read_text(encoding="utf-8")
    d = json.loads(t) if str(path).endswith(".json") else yaml.safe_load(t)
    return validate_storyboard(d)

def _lines(sid, s):
    """Spoken lines of a shot. `narration:` alone = one narrator line; `lines:` = [{speaker, text, emotion?, pause?}]
    (a line may also be written "林晚: text"). `speaker:`/`emotion:` on the shot apply to its narration."""
    raw = s.get("lines")
    if raw is None:
        t = str(s.get("narration") or "").strip()
        return [dict(speaker=str(s.get("speaker") or "narrator"), text=t, emotion=s.get("emotion"), kind="narration" if not s.get("speaker") or s.get("speaker") == "narrator" else "dialogue")] if t else []
    if not isinstance(raw, list) or len(raw) > 12: raise ValueError(f"shot {sid}: lines must be a list (max 12)")
    out = []
    for j, l in enumerate(raw, 1):
        if isinstance(l, str):
            m = re.match(r"^\s*([^:：]{1,40})[:：]\s*(.+)$", l); l = dict(speaker=m.group(1).strip(), text=m.group(2)) if m else dict(text=l)
        if not isinstance(l, dict) or not str(l.get("text") or "").strip(): raise ValueError(f"shot {sid} line {j}: needs text")
        sp = str(l.get("speaker") or "narrator").strip()[:40]; em = l.get("emotion")
        if em is not None and not re.fullmatch(r"[a-z_]{2,20}", str(em)): raise ValueError(f"shot {sid} line {j}: emotion must be a word like sad / gentle")
        ln = dict(speaker=sp, text=str(l["text"]).strip(), emotion=em, kind="narration" if sp == "narrator" else "dialogue")
        if l.get("pause") is not None:
            try: ln["pause"] = max(0.0, min(2.0, float(l["pause"])))
            except (TypeError, ValueError): raise ValueError(f"shot {sid} line {j}: pause must be seconds")
        out.append(ln)
    return out

def speakers(sb): return sorted({l["speaker"] for s in sb["shots"] for l in s.get("lines", [])})

SHOT_TYPES = ("wide", "two_shot", "ots", "closeup", "reaction", "insert")
def _chars(sid, v):
    if isinstance(v, str): v = [x.strip() for x in re.split(r"[,，、]", v) if x.strip()]
    if not isinstance(v, list) or len(v) > 5: raise ValueError(f"shot {sid}: characters must be a list of up to 5 names")
    return [str(x).strip()[:40] for x in v]

def validate_storyboard(d):
    """Normalize + validate. Raises ValueError with a readable message."""
    if not isinstance(d, dict): raise ValueError("storyboard must be a mapping with a 'shots' list")
    shots = d.get("shots")
    if not isinstance(shots, list) or not shots: raise ValueError("storyboard needs at least one shot")
    if len(shots) > 60: raise ValueError("at most 60 shots")
    aspect = str(d.get("aspect", "9:16"))
    if aspect not in SIZES: raise ValueError(f"aspect must be one of {list(SIZES)}")
    out = dict(title=str(d.get("title") or "Untitled")[:120], aspect=aspect, language=str(d.get("language") or "en"),
               template=str(d.get("template") or ""), shots=[])
    if d.get("caption_style") is not None:
        from .subs import caption_style
        if not isinstance(d["caption_style"], dict): raise ValueError("caption_style must be a mapping like {position: top, scale: 1.2}")
        out["caption_style"] = caption_style(d["caption_style"])
    seen = set()
    for i, s in enumerate(shots, 1):
        if not isinstance(s, dict): raise ValueError(f"shot {i} must be a mapping")
        sid = str(s.get("id") or f"s{i:02d}")
        if not ID_RE.fullmatch(sid) or sid in seen: raise ValueError(f"shot {i}: id '{sid}' must be unique letters/digits/_/-")
        seen.add(sid)
        try: dur = float(s.get("duration", 4.0))
        except (TypeError, ValueError): raise ValueError(f"shot {sid}: duration must be a number")
        if not 0.8 <= dur <= 30: raise ValueError(f"shot {sid}: duration {dur}s out of range 0.8-30")
        cam = str(s.get("camera") or "push_in"); tr = str(s.get("transition") or "crossfade")
        if cam not in CAMERAS: raise ValueError(f"shot {sid}: camera must be one of {CAMERAS}")
        if tr not in TRANSITIONS: raise ValueError(f"shot {sid}: transition must be one of {TRANSITIONS}")
        lines = _lines(sid, s)
        narr = " ".join(l["text"] for l in lines) if s.get("lines") else str(s.get("narration") or "").strip()
        out["shots"].append(dict(id=sid, narration=narr, lines=lines, duration=dur, caption=str(s.get("caption") or "").strip()[:80],
                                 visual=str(s.get("visual") or "").strip(), camera=cam, transition=tr,
                                 **({"clip": str(s["clip"])} if s.get("clip") else {}),
                                 **({"ref_image": str(s["ref_image"])[:200]} if s.get("ref_image") else {}),
                                 **({"characters": _chars(sid, s["characters"])} if s.get("characters") else {}),
                                 **({"shot_type": str(s["shot_type"])} if s.get("shot_type") in SHOT_TYPES else {})))
    return out

def find_clip(folder, sid):
    """clips/<id>.<ext> (video preferred over image)."""
    for ext in (".mp4", ".mov", ".webm", ".mkv", ".png", ".jpg", ".jpeg", ".webp"):
        for d in (Path(folder), Path(folder) / "clips"):
            p = d / f"{sid}{ext}"
            if p.is_file(): return p
    return None

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
def is_image(p): return str(p).lower().endswith(IMAGE_EXT)

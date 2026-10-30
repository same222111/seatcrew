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
        out["shots"].append(dict(id=sid, narration=str(s.get("narration") or "").strip(), duration=dur, caption=str(s.get("caption") or "").strip()[:80],
                                 visual=str(s.get("visual") or "").strip(), camera=cam, transition=tr,
                                 **({"clip": str(s["clip"])} if s.get("clip") else {})))
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

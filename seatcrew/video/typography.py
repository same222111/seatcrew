"""Use installed CJK fonts for titles and subtitles; if none is installed, degrade to the bundled Latin font with a loud warning
(the video still renders - CJK glyphs may show as boxes - instead of the whole PRODUCTION stage failing)."""
import os, shutil, subprocess, warnings
from pathlib import Path
from .tts import CJK
from .ff import FFError

LATIN = Path(__file__).parent / "fonts" / "Montserrat-ExtraBold.ttf"


def text_font(text, extra_dirs=(), strict=False):
    if not CJK.search(text): return LATIN, "Montserrat ExtraBold"
    candidates = []
    dirs = [*extra_dirs, os.environ.get("SEATCREW_FONTS_DIR")]
    for directory in filter(None, dirs):
        for pattern, family in (("NotoSansSC*.ttf", "Noto Sans SC"), ("NotoSansSC*.otf", "Noto Sans SC"),
                                ("NotoSansCJK*.ttc", "Noto Sans CJK SC"), ("NotoSansCJKsc*.otf", "Noto Sans CJK SC")):
            candidates.extend((p, family) for p in sorted(Path(directory).glob(pattern)))
    if os.environ.get("SEATCREW_NO_SYSTEM_FONTS") != "1":            # test hook: simulate a machine without CJK fonts
        candidates += system_fonts()
    for path, family in candidates:
        if path.is_file(): return path, family
    hit = _fc_match() if os.environ.get("SEATCREW_NO_SYSTEM_FONTS") != "1" else None
    if hit: return hit
    if strict: raise FFError(MISSING)
    warnings.warn(MISSING, RuntimeWarning, stacklevel=2); MISSING_SEEN.append(MISSING)
    return LATIN, "Montserrat ExtraBold"

def system_fonts():
    return [
        (Path("/System/Library/Fonts/STHeiti Medium.ttc"), "Heiti SC"),
        (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc", "Microsoft YaHei"),
        (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), "Noto Sans CJK SC"),
        (Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"), "Noto Sans CJK SC"),
    ]

MISSING = "CJK font not found: install Noto Sans CJK (apt install fonts-noto-cjk), or put NotoSansSC .ttf/.otf in SEATCREW_FONTS_DIR"
MISSING_SEEN = []
def _fc_match():
    """Any installed font that covers Chinese, via fontconfig (Linux/macOS with fc-list)."""
    if not shutil.which("fc-list"): return None
    try: out = subprocess.run(["fc-list", ":lang=zh", "file", "family"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10).stdout
    except Exception: return None
    for line in sorted(out.splitlines()):
        path, _, fam = line.partition(":")
        if path.strip() and Path(path.strip()).is_file(): return Path(path.strip()), (fam.split(",")[0].strip() or "Sans")
    return None

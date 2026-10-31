"""Use installed CJK fonts for titles and subtitles; never silently render boxes."""
import os
from pathlib import Path
from .tts import CJK
from .ff import FFError

LATIN = Path(__file__).parent / "fonts" / "Montserrat-ExtraBold.ttf"


def text_font(text, extra_dirs=()):
    if not CJK.search(text): return LATIN, "Montserrat ExtraBold"
    candidates = []
    dirs = [*extra_dirs, os.environ.get("SEATCREW_FONTS_DIR")]
    for directory in filter(None, dirs):
        for pattern, family in (("NotoSansSC*.ttf", "Noto Sans SC"), ("NotoSansSC*.otf", "Noto Sans SC"),
                                ("NotoSansCJK*.ttc", "Noto Sans CJK SC"), ("NotoSansCJKsc*.otf", "Noto Sans CJK SC")):
            candidates.extend((p, family) for p in sorted(Path(directory).glob(pattern)))
    candidates += [
        (Path("/System/Library/Fonts/STHeiti Medium.ttc"), "Heiti SC"),
        (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc", "Microsoft YaHei"),
        (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), "Noto Sans CJK SC"),
        (Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"), "Noto Sans CJK SC"),
    ]
    for path, family in candidates:
        if path.is_file(): return path, family
    raise FFError("CJK font not found: install Noto Sans CJK, or put NotoSansSC .ttf/.otf in SEATCREW_FONTS_DIR")

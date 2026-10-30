"""Word-timed karaoke subtitles (ASS) with safe margins, plus per-shot headline captions."""
import re
from .tts import CJK

ACCENT = "&H0000E5FF"          # sung words: warm yellow (ASS is &HAABBGGRR)
WHITE, BLACK, SHADOW = "&H00FFFFFF", "&H00000000", "&H96000000"
FONT_NAME = "Montserrat ExtraBold"
FONT_CJK = "Noto Sans SC Black"      # OFL; put NotoSansSC-*.ttf/otf in a fonts dir (SEATCREW_FONTS_DIR) or install it system-wide
END_P = re.compile(r"[.!?。！？…]$"); MID_P = re.compile(r"[,;:，、；：]$")

def layout(w, h):
    """Font size, line length and margins for the frame. 9:16 keeps text above the bottom app UI (~22%) and inside 8% side margins."""
    if h > w: return dict(size=round(h * 0.047), max_chars=16, max_cjk=10, margin_v=round(h * 0.22), margin_lr=round(w * 0.08), title=round(h * 0.036), title_v=round(h * 0.12), outline=round(h * 0.0036))
    return dict(size=round(h * 0.058), max_chars=34, max_cjk=20, margin_v=round(h * 0.085), margin_lr=round(w * 0.08), title=round(h * 0.06), title_v=round(h * 0.08), outline=round(h * 0.0045))

def chunk(words, L):
    """Group words into short subtitle lines: break on sentence ends, long pauses, and line length."""
    out, cur = [], []
    def length(ws): return sum(len(x["w"]) for x in ws) + (0 if all(CJK.search(x["w"]) for x in ws) else len(ws) - 1)
    for i, w in enumerate(words):
        lim = L["max_cjk"] if CJK.search(w["w"]) else L["max_chars"]
        if cur and (length(cur + [w]) > lim or w["start"] - cur[-1]["end"] > 0.45 or w.get("shot") != cur[-1].get("shot")): out.append(cur); cur = []
        cur.append(w)
        if END_P.search(w["w"]) or (MID_P.search(w["w"]) and len(cur) >= 3): out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def ts(t):
    t = max(0.0, t); cs = int(round(t * 100)); return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

def esc(s): return s.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", " ")

def build_ass(words, captions, w, h, total, font=None):
    """words: global [{w,start,end,shot}], captions: [(start, end, text)]. Returns (ass_text, cues) where cues are the subtitle events (for QC)."""
    if font is None: font = FONT_CJK if any(CJK.search(x["w"]) for x in words) or any(CJK.search(c[2] or "") for c in captions) else FONT_NAME
    L = layout(w, h)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font},{L['size']},{ACCENT},{WHITE},{BLACK},{SHADOW},0,0,0,0,100,100,0,0,1,{L['outline']},{max(1, L['outline'] // 2)},2,{L['margin_lr']},{L['margin_lr']},{L['margin_v']},1
Style: Title,{font},{L['title']},{WHITE},{WHITE},{BLACK},{SHADOW},0,0,0,0,100,100,1,0,1,{L['outline']},{max(1, L['outline'] // 2)},8,{L['margin_lr']},{L['margin_lr']},{L['title_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines, cues = [], []
    groups = chunk(words, L)
    for gi, g in enumerate(groups):
        st = max(0.0, g[0]["start"] - 0.08)
        if cues: st = max(st, cues[-1]["end"])
        nxt = groups[gi + 1][0]["start"] - 0.08 if gi + 1 < len(groups) else total
        en = min(max(g[-1]["end"] + 0.25, g[-1]["end"]), max(nxt, g[-1]["end"]), total)
        cjk = all(CJK.search(x["w"]) for x in g)
        parts, t_prev, acc = [], st, 0
        k0 = int(round((g[0]["start"] - st) * 100))
        if k0 > 0: parts.append(f"{{\\k{k0}}}"); acc += k0
        for i, x in enumerate(g):
            t_next = g[i + 1]["start"] if i + 1 < len(g) else max(x["end"], x["start"] + 0.05)
            target = int(round((t_next - st) * 100)); k = max(1, target - acc); acc += k
            parts.append(f"{{\\k{k}}}{esc(x['w'])}" + ("" if cjk or i + 1 == len(g) else " "))
        anim = "{\\fad(70,60)\\fscx92\\fscy92\\t(0,100,\\fscx100\\fscy100)}"
        lines.append(f"Dialogue: 0,{ts(st)},{ts(en)},Karaoke,,0,0,0,,{anim}{''.join(parts)}")
        cues.append(dict(start=round(st, 3), end=round(en, 3), text=("" if cjk else " ").join(x["w"] for x in g), first=g[0]["start"], words=[x["start"] for x in g]))
    for s, e, text in captions:
        if text: lines.append(f"Dialogue: 1,{ts(s)},{ts(e)},Title,,0,0,0,,{{\\fad(200,200)}}{esc(text)}")
    return head + "\n".join(lines) + "\n", cues

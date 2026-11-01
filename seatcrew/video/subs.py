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

NO_START = set("，。、；：？！…‥）》」』】〕”’,.;:?!)]}%·")      # never begins a subtitle line
NO_END = set("（《「『【〔“‘([{")                                # never ends one
PUNCT = NO_START | NO_END | set("—-~～ ")

def _is_punct(t): return bool(t) and all(c in PUNCT for c in t)

def _glue(words):
    """Attach punctuation-only tokens to the neighbouring word: closing marks to the previous one, opening marks to the next one."""
    out, pend = [], None
    for w in words:
        t = w["w"]
        if _is_punct(t) and all(c in NO_END for c in t.strip()) and t.strip():
            pend = dict(w) if pend is None else dict(pend, w=pend["w"] + t); continue
        if pend is not None: w = dict(w, w=pend["w"] + t, start=min(pend["start"], w["start"])); pend = None
        if out and _is_punct(w["w"]) and out[-1].get("shot") == w.get("shot") and out[-1].get("speaker") == w.get("speaker"):
            out[-1] = dict(out[-1], w=out[-1]["w"] + w["w"].strip(), end=max(out[-1]["end"], w["end"])); continue
        out.append(dict(w))
    if pend is not None:
        if out: out[-1] = dict(out[-1], w=out[-1]["w"] + pend["w"])
        else: out.append(pend)
    return out

def _len(ws):
    cj = all(CJK.search(x["w"]) or _is_punct(x["w"]) for x in ws)
    return sum(len(x["w"].strip()) for x in ws) + (0 if cj else len(ws) - 1)

def _lim(ws, L): return L["max_cjk"] if any(CJK.search(x["w"]) for x in ws) else L["max_chars"]

BREAK_AFTER = set("的了着过地得么吗呢吧啊呀和与及或但而就都也又还才把被让给从向到在对为是说")
BREAK_BEFORE = set("的是在和与就都也又还才把被让给从向到对为而但所因如")
try:                                                               # optional: real word segmentation for Chinese (pip install jieba)
    import jieba as _jieba; _jieba.setLogLevel(60)
except Exception: _jieba = None

def _cuts(ws):
    """Penalty for breaking a line before word b (b = 1..n-1): 0 after punctuation, small at a word boundary, large inside a word."""
    toks = [x["w"].strip() for x in ws]; pen = [0.0] * (len(ws) + 1)
    if not any(CJK.search(t) for t in toks): return pen
    text = "".join(toks); ends = None
    if _jieba is not None:
        ends, k = set(), 0
        for w_ in _jieba.lcut(text): k += len(w_); ends.add(k)
    pos = 0
    for b in range(1, len(ws)):
        pos += len(toks[b - 1]); l, r = toks[b - 1][-1:], toks[b][:1]
        if l in NO_START or l in PUNCT: pen[b] = 0.0
        elif ends is not None: pen[b] = (0.5 if l in BREAK_AFTER or r in BREAK_BEFORE else 1.0) if pos in ends else 9.0
        else: pen[b] = 1.0 if l in BREAK_AFTER or r in BREAK_BEFORE else (2.0 if len(toks[b - 1]) > 1 and len(toks[b]) > 1 else 4.0)
    return pen

def _balance(ws, lim):
    """Split one clause into the fewest lines that fit, with even line lengths and breaks at punctuation / word boundaries (DP)."""
    n = len(ws)
    if n <= 1 or _len(ws) <= lim: return [ws]
    pen = _cuts(ws); k = -(-_len(ws) // lim)
    for kk in range(k, n + 1):
        target = _len(ws) / kk; INF = float("inf")
        best = [[INF] * (n + 1) for _ in range(kk + 1)]; back = [[0] * (n + 1) for _ in range(kk + 1)]; best[0][0] = 0
        for p in range(1, kk + 1):
            for e in range(1, n + 1):
                for b in range(p - 1, e):
                    if best[p - 1][b] == INF: continue
                    ln = _len(ws[b:e])
                    if ln > lim + (1 if ws[e - 1]["w"][-1:] in NO_START else 0): continue
                    if len(ws[b:e]) and _len(ws[b:e]) - sum(len(x["w"].strip()) for x in ws[b:e] if _is_punct(x["w"])) < 2 and kk > 1: continue
                    c = best[p - 1][b] + (ln - target) ** 2 + 2 * pen[b]
                    if c < best[p][e]: best[p][e], back[p][e] = c, b
        if best[kk][n] < INF:
            out, e = [], n
            for p in range(kk, 0, -1): b = back[p][e]; out.append(ws[b:e]); e = b
            return out[::-1]
    return [[w] for w in ws]

def chunk(words, L):
    """Group words into subtitle lines that follow punctuation and meaning: break at sentence / clause ends, pauses, shot or speaker
    changes; split a long clause into evenly sized lines; punctuation never starts a line and ?/。 never stand alone."""
    words = _glue(words)
    clauses, cur = [], []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > 0.6 or w.get("shot") != cur[-1].get("shot") or w.get("speaker") != cur[-1].get("speaker")):
            clauses.append(cur); cur = []
        cur.append(w)
        if END_P.search(w["w"].rstrip("”’」』）)")) or MID_P.search(w["w"]): clauses.append(cur); cur = []
    if cur: clauses.append(cur)
    merged = []                                                    # short clause of the same sentence joins its neighbour when it fits
    for c in clauses:
        if merged:
            m = merged[-1]; same = c[0].get("speaker") == m[0].get("speaker") and c[0].get("shot") == m[0].get("shot") and c[0]["start"] - m[-1]["end"] < 1.2
            fits = _len(m + c) <= _lim(m + c, L) + 1
            short = (_len(c) <= 3 and (fits or not END_P.search(m[-1]["w"]))) or (_len(m) <= 3 and not END_P.search(m[-1]["w"]))
            if same and short and (fits or _len(m + c) >= 8): merged[-1] = m + c; continue   # merged clause is re-balanced below
        merged.append(c)
    out = []
    for c in merged: out.extend(_balance(c, _lim(c, L)))
    return out

def tokens(text):
    """Split display text into breakable tokens: jieba words for Chinese when available, else characters; Latin by spaces."""
    t = re.sub(r"\s+", " ", str(text or "").strip()); out = []
    for part in re.findall(r"[A-Za-z0-9À-ÿ'’.\-]+|\s|.", t):
        if part == " ": continue
        out.append(part)
    if _jieba is not None and CJK.search(t):
        merged, buf = [], ""
        for seg in _jieba.lcut(t):
            if seg.strip(): merged.append(seg.strip())
        if "".join(merged) == "".join(out): out = merged
    return out

def break_text(text, per_line, max_lines=None):
    """Shared line breaker for subtitles, captions and draft cards: punctuation never starts a line, ?/。 never stand alone,
    words (e.g. 橙红色) are not split when jieba is installed, and line lengths are balanced."""
    toks = tokens(text)
    if not toks: return []
    ws = [dict(w=x if CJK.search(x) or _is_punct(x) or i == 0 else x, start=0.0, end=0.0) for i, x in enumerate(toks)]
    ws = _glue(ws); lim = max(2, int(per_line)); clauses, cur = [], []
    for x in ws:                                                    # clauses end at punctuation -> preferred break points
        cur.append(x)
        if x["w"] and x["w"][-1] in "。！？!?；;，,、：:": clauses.append(cur); cur = []
    if cur: clauses.append(cur)
    groups = []
    for c in clauses:                                               # pack short clauses together, balance long ones
        if groups and _len(groups[-1] + c) <= lim: groups[-1] = groups[-1] + c
        elif groups and _len(groups[-1]) <= max(2, lim // 3):          # no orphan 「那么，」 line
            b = _balance(c, lim)
            if _len(groups[-1] + b[0]) <= lim: groups[-1] = groups[-1] + b[0]; groups.extend(b[1:])
            else: groups[-1:] = _balance(groups[-1] + c, lim)
        else: groups.extend(_balance(c, lim))
    lines = []
    for g in groups:
        cj = all(CJK.search(x["w"]) or _is_punct(x["w"]) for x in g)
        lines.append(("" if cj else " ").join(x["w"] for x in g))
    if max_lines and len(lines) > max_lines: lines = lines[:max_lines]; lines[-1] = lines[-1].rstrip("，、,;；") + "…"
    return lines

def wrap_title(text, per_line):
    """Balanced manual line breaks (joined with newlines) for CJK captions; Latin text is left to the renderer."""
    t = text.strip()
    if not CJK.search(t) or len(t) <= per_line: return t
    return "\n".join(break_text(t, per_line))

def ts(t):
    t = max(0.0, t); cs = int(round(t * 100)); return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

def esc(s): return s.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", " ")

def ass_color(hexrgb):
    """#RRGGBB -> ASS &H00BBGGRR."""
    h = hexrgb.lstrip("#"); return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()

CAPTION_POSITIONS = ("top", "upper", "lower")
CAPTION_DEFAULT = dict(position="top", scale=1.0)

def caption_style(cs=None):
    """Normalize a title-card style {position: top|upper|lower, scale: 0.6-2.0}. Unknown values raise ValueError."""
    cs = dict(CAPTION_DEFAULT, **{k: v for k, v in (cs or {}).items() if v is not None})
    pos = str(cs["position"]).lower()
    if pos not in CAPTION_POSITIONS: raise ValueError(f"caption position must be one of {CAPTION_POSITIONS}")
    try: sc = float(cs["scale"])
    except (TypeError, ValueError): raise ValueError("caption scale must be a number")
    if not 0.6 <= sc <= 2.0: raise ValueError("caption scale must be between 0.6 and 2.0")
    return dict(position=pos, scale=sc)

def caption_layout(w, h, cs=None):
    """Title-card font size and placement. Default: big (about 5% of the height in 9:16) at the top safe area, i.e. just
    below the phone status bar / app header (~5%) and above where faces and hands usually are. `upper` sits a bit lower
    (for footage with sky/ceiling at the top), `lower` sits just above the subtitles."""
    cs = caption_style(cs); L = layout(w, h); portrait = h > w
    size = round((h * 0.05 if portrait else h * 0.068) * cs["scale"])
    if cs["position"] == "top": align, mv = 8, round(h * (0.055 if portrait else 0.05))
    elif cs["position"] == "upper": align, mv = 8, round(h * (0.16 if portrait else 0.12))
    else: align, mv = 2, L["margin_v"] + round(L["size"] * 2.6)        # above two subtitle lines
    return dict(size=size, align=align, margin_v=mv, outline=max(L["outline"], round(size * 0.09)), position=cs["position"], scale=cs["scale"])

def build_ass(words, captions, w, h, total, font=None, speaker_colors=None, caption=None):
    """words: global [{w,start,end,shot,speaker?}], captions: [(start, end, text)]. speaker_colors: {speaker: "#RRGGBB"} colors the
    spoken (highlighted) words of that speaker's lines. Returns (ass_text, cues) where cues are the subtitle events (for QC)."""
    if font is None: font = FONT_CJK if any(CJK.search(x["w"]) for x in words) or any(CJK.search(c[2] or "") for c in captions) else FONT_NAME
    L = layout(w, h); C = caption_layout(w, h, caption)
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
Style: Title,{font},{C['size']},{WHITE},{WHITE},{BLACK},{SHADOW},-1,0,0,0,100,100,1,0,1,{C['outline']},{max(1, C['outline'] // 2)},{C['align']},{L['margin_lr']},{L['margin_lr']},{C['margin_v']},1

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
        cjk = all(CJK.search(x["w"]) or _is_punct(x["w"]) for x in g)
        parts, t_prev, acc = [], st, 0
        k0 = int(round((g[0]["start"] - st) * 100))
        if k0 > 0: parts.append(f"{{\\k{k0}}}"); acc += k0
        for i, x in enumerate(g):
            t_next = g[i + 1]["start"] if i + 1 < len(g) else max(x["end"], x["start"] + 0.05)
            target = int(round((t_next - st) * 100)); k = max(1, target - acc); acc += k
            parts.append(f"{{\\k{k}}}{esc(x['w'])}" + ("" if cjk or i + 1 == len(g) else " "))
        col = (speaker_colors or {}).get(g[0].get("speaker"))
        anim = "{" + ("\\q2" if cjk else "") + "\\fad(70,60)\\fscx92\\fscy92\\t(0,100,\\fscx100\\fscy100)" + (f"\\1c{ass_color(col)}" if col else "") + "}"
        lines.append(f"Dialogue: 0,{ts(st)},{ts(en)},Karaoke,,0,0,0,,{anim}{''.join(parts)}")
        cues.append(dict(start=round(st, 3), end=round(en, 3), text=("" if cjk else " ").join(x["w"] for x in g), first=g[0]["start"], words=[x["start"] for x in g], **({"speaker": g[0]["speaker"]} if g[0].get("speaker") else {})))
    L_ = L
    for s, e, text in captions:
        if text:
            per = max(4, int((w - 2 * L_['margin_lr']) / (C['size'] * 1.05))); q = "\\q2" if CJK.search(text) else ""
            body = "\\N".join(esc(x) for x in wrap_title(text, per).split("\n"))
            lines.append(f"Dialogue: 1,{ts(s)},{ts(e)},Title,,0,0,0,,{{\\fad(200,200){q}}}{body}")
    return head + "\n".join(lines) + "\n", cues

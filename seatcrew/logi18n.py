"""Display-only translation of log lines, check reasons and QC details. The log file keeps English; the API adds *_l fields."""
import re

KINDS = {
 "zh-CN": dict(CYCLE="轮次", PLAN="计划", DONE="完成", SUBMIT="提交", CHECK_OK="通过", CHECK_BLOCKED="拦截", WAITING="等待", HOLD="暂停", REWRITE="退回重做",
               PARALLEL="并行", ERROR="错误", CONFIG="设置", DECIDE="决定", APPROVED="已批准", REJECTED="已驳回", RUN="运行", START="开始", STOP="停止"),
 "zh-TW": dict(CYCLE="輪次", PLAN="計畫", DONE="完成", SUBMIT="提交", CHECK_OK="通過", CHECK_BLOCKED="攔截", WAITING="等待", HOLD="暫停", REWRITE="退回重做",
               PARALLEL="並行", ERROR="錯誤", CONFIG="設定", DECIDE="決定", APPROVED="已核准", REJECTED="已駁回", RUN="執行", START="開始", STOP="停止"),
 "ja": dict(CYCLE="サイクル", PLAN="計画", DONE="完了", SUBMIT="投入", CHECK_OK="OK", CHECK_BLOCKED="ブロック", WAITING="待機", HOLD="保留", REWRITE="差し戻し",
            PARALLEL="並列", ERROR="エラー", CONFIG="設定"),
 "es": dict(CYCLE="CICLO", PLAN="PLAN", DONE="HECHO", SUBMIT="ENVÍO", CHECK_OK="OK", CHECK_BLOCKED="BLOQUEO", WAITING="ESPERA", HOLD="PAUSA", REWRITE="REHACER",
            PARALLEL="PARALELO", ERROR="ERROR", CONFIG="AJUSTES"),
}
SEATS = {
 "zh-CN": dict(chief="导演", topic="选题", writer="编剧", scriptcheck="审稿", production="制作", voice="配音", visuals="画面", lipsync="口型", editqc="剪辑+质检", editor="剪辑", qc="质检", approve="批准"),
 "zh-TW": dict(chief="導演", topic="選題", writer="編劇", scriptcheck="審稿", production="製作", voice="配音", visuals="畫面", lipsync="對嘴", editqc="剪輯+質檢", editor="剪輯", qc="質檢", approve="核准"),
 "ja": dict(chief="ディレクター", writer="脚本", scriptcheck="脚本チェック", production="制作", voice="音声", visuals="映像", lipsync="リップシンク", editqc="編集+QC", editor="編集", qc="QC", approve="承認"),
 "es": dict(chief="director", writer="guion", scriptcheck="revisión", production="producción", voice="voz", visuals="imágenes", lipsync="sincronía", editqc="edición+QC", editor="edición", qc="QC", approve="aprobación"),
}
QC_NAMES = {
 "zh-CN": dict(format="格式", duration="时长", source_resolution="素材分辨率", clip_length="素材长度", sharpness="清晰度", black_frames="黑帧", frozen_frames="冻帧", av_stream_sync="音画时长一致",
               loudness="响度", clipping="削波", voice_present="有人声", silence_gaps="静音间隔", subtitle_sync="字幕同步", voice_consistency="角色声音一致", final_quality="成品质量"),
}
QC_NAMES["zh-TW"] = dict(QC_NAMES["zh-CN"], source_resolution="素材解析度", clip_length="素材長度", sharpness="清晰度", black_frames="黑幀", frozen_frames="凍幀", av_stream_sync="音畫時長一致",
                         loudness="響度", voice_present="有人聲", silence_gaps="靜音間隔", subtitle_sync="字幕同步", voice_consistency="角色聲音一致", final_quality="成品品質", duration="時長")

# (pattern, replacement) applied in order; each lang lists only what it translates. {seat} placeholders are resolved via SEATS.
_ZH = [
 (r"^cycle (\d+) start$", r"第 \1 轮开始"),
 (r"^cycle (\d+): (\d+) passed, (\d+) blocked, (\d+) waiting / (\d+)$", r"第 \1 轮：\2 通过，\3 拦截，\4 等待 / 共 \5"),
 (r"^(\d+) new item\(s\)$", r"\1 个新事项"),
 (r"^CHIEF holds new items this cycle$", "导演本轮暂停接收新事项"),
 (r"^CHIEF holds (\d+) late item\(s\)", r"导演暂缓 \1 个后到的事项"),
 (r"^settings saved: (.+)$", r"设置已保存：\1"),
 (r"\blanguage\b", "语言"),
 (r"waiting for a human to approve", "等待你批准"),
 (r"auto-approved \(setting\)", "已自动批准（设置）"),
 (r"approved by human", "已由你批准"), (r"rejected by human", "已被你驳回"),
 (r"still failing after (\d+) round\(s\) - needs you", r"重做 \1 轮后仍未通过，需要你处理"),
 (r"sent back to ([A-Z]+) \(round (\d+)\)", lambda m, L: f"退回{seat(m.group(1), L)}（第 {m.group(2)} 轮）"),
 (r"(\d+) shots, ~(\d+)s \(template\)", r"\1 个镜头，约 \2 秒（模板）"),
 (r"(\d+) shots, ~(\d+)s \((\w+)\)", r"\1 个镜头，约 \2 秒（\3）"),
 (r"readable, safe words, ~(\d+)s", r"可读、用词安全，约 \1 秒"),
 (r"Knowledge explainer", "知识讲解"),
 (r"\bdraft×(\d+)", r"草稿×\1"), (r"DRAFT PREVIEW - offline voice/visuals", "草稿预览：离线配音/画面"), (r"^not final quality$", "不是成品质量"),
 (r"\[DRAFT\]", "[草稿]"), (r"\bDRAFT\b", "草稿"),
 (r"(\w+) voice, exact word timing", r"\1 配音，逐词时间精确"), (r"(\w+) voice, estimated word timing", r"\1 配音，逐词时间为估算"),
 (r"^voice ", "配音 "), (r"^visuals ", "画面 "), (r"^lipsync ", "口型 "),
 (r"off \(shots keep their original mouths\)", "关闭（镜头保留原口型）"),
 (r"(\w+): synced (\d+) shot\(s\)", r"\1：已同步 \2 个镜头"),
 (r"(\d+)x(\d+) ([\d.]+)s -> (\S+)", r"\1x\2 \3 秒 → \4"),
 (r"^PASS\b", "通过"), (r"FAIL -> ([A-Z]+)", lambda m, L: f"未通过 → {seat(m.group(1), L)}"),
 (r"(\d+)/(\d+) checks", r"\1/\2 项检查"),
 (r"audio=yes", "有音频"), (r"audio=MISSING", "缺少音频"),
 (r"([\d.]+)s \(planned ([\d.]+)s, allowed (\d+)-(\d+)s\)", r"\1 秒（计划 \2 秒，允许 \3–\4 秒）"),
 (r"all sources >= (\d+)% of output", r"所有素材 ≥ 输出的 \1%"), (r"upscaled too much: ", "放大过度："),
 (r"video stream ([\d.]+)s vs audio stream ([\d.]+)s \(max gap ([\d.]+)s\)", r"画面 \1 秒 / 声音 \2 秒（最多相差 \3 秒）"),
 (r"could not read video/audio stream durations", "读不到画面/声音的时长"),
 (r"every clip covers its shot", "每段素材都覆盖了镜头"), (r"clips shorter than their shot \(frozen tail\): ", "素材比镜头短（结尾会定格）："),
 (r"^min ([\d.]+)$", r"最低 \1"), (r"^blurry: ", "模糊："), (r"^black at ", "黑帧位于 "), (r"^frozen at ", "冻帧位于 "),
 (r"^none$", "无"),
 (r"([-\d.]+) LUFS \(target ([-\d.]+) \+-([\d.]+)\)", r"\1 LUFS（目标 \2 ±\3）"), (r" - silent 草稿 voice", "，草稿为无声配音"),
 (r"true peak ([-\d.]+) dBTP \(max ([-\d.]+)\)", r"真峰值 \1 dBTP（上限 \2）"),
 (r"narration audible", "能听到旁白"), (r"voice track is silent \(草稿 - install edge-tts for a real voice\)", "配音轨无声（草稿：安装 edge-tts 可获得真实配音）"),
 (r"voice track is silent", "配音轨无声"), (r"no narration", "没有旁白"), (r"external video - narration checks skipped", "外部视频：跳过旁白检查"),
 (r"no gap > ([\d.]+)s", r"没有超过 \1 秒的停顿"), (r"^gaps ", "停顿 "),
 (r"(\d+)% of subtitle words start on speech", r"\1% 的字幕词与语音对齐"), (r" \(timings estimated - draft voice\)", "（时间为估算：草稿配音）"),
 (r"(\d+) character\(s\), one voice each", r"\1 个角色，各用一个声音"), (r"(\S+) uses (\d+) voices", r"\1 用了 \2 种声音"),
 (r"final backends", "成品后端"),
 (r"no topic", "没有主题"), (r"unknown template (\S+)", r"未知模板 \1"), (r"no storyboard", "没有分镜"),
 (r"unsafe phrase: ", "不安全用语："), (r"not in the cast: ", "不在角色表中："), (r"contains an email address or phone number", "包含邮箱或电话号码"),
 (r"template placeholder text in (.+?) - write the narration first", r"\1 还有模板占位文字，请先写旁白"),
 (r"shots without narration: ", "没有旁白的镜头："), (r"sentences over (\d+) words: ", r"超过 \1 词的句子："),
 (r"shot too long to read: ", "镜头读不完："), (r"(\S+) needs ~([\d.]+)s > (\d+)s", r"\1 需要约 \2 秒 > \3 秒"),
 (r"total ~(\d+)s outside ([\d.]+)-(\d+)s", r"总时长约 \1 秒，不在 \2–\3 秒内"),
 (r"ffmpeg not found - install ffmpeg and retry", "找不到 ffmpeg：请安装后重试"),
 (r"\b(\d+) words\b", r"\1 词"),
]
_TW_CHARS = str.maketrans("轮开个项导暂设语请这认驳处对镜头时约讲词审剪辑质检计划许输盖结会帧删静间隔声轨听获实际选异较备码电话还写须读总内围该后过频没见长迟发运错决缓达终围节绝择维损钟与齐顿无预览画关闭确离线", "輪開個項導暫設語請這認駁處對鏡頭時約講詞審剪輯質檢計劃許輸蓋結會幀刪靜間隔聲軌聽獲實際選異較備碼電話還寫須讀總內圍該後過頻沒見長遲發運錯決緩達終圍節絕擇維損鐘與齊頓無預覽畫關閉確離線")
_ES = [(r"^cycle (\d+) start$", r"inicio del ciclo \1"), (r"^cycle (\d+): (\d+) passed, (\d+) blocked, (\d+) waiting / (\d+)$", r"ciclo \1: \2 aprobados, \3 bloqueados, \4 en espera / \5"),
       (r"^(\d+) new item\(s\)$", r"\1 elemento(s) nuevo(s)"), (r"waiting for a human to approve", "esperando tu aprobación"), (r"^PASS\b", "APROBADO"), (r"(\d+)/(\d+) checks", r"\1/\2 controles"),
       (r"narration audible", "narración audible"), (r"^none$", "ninguno"), (r"no narration", "sin narración")]
_JA = [(r"^cycle (\d+) start$", r"サイクル \1 開始"), (r"^cycle (\d+): (\d+) passed, (\d+) blocked, (\d+) waiting / (\d+)$", r"サイクル \1: 合格 \2・ブロック \3・待機 \4 / \5"),
       (r"^(\d+) new item\(s\)$", r"新規 \1 件"), (r"waiting for a human to approve", "あなたの承認待ち"), (r"^PASS\b", "合格"), (r"(\d+)/(\d+) checks", r"\1/\2 項目"),
       (r"narration audible", "ナレーションあり"), (r"^none$", "なし"), (r"no narration", "ナレーションなし")]

def seat(name, lang): return SEATS.get(lang, {}).get(str(name).lower(), str(name))

def _rules(lang):
    if lang in ("zh-CN", "zh-TW"): return _ZH
    return {"es": _ES, "ja": _JA}.get(lang, [])

def text(s, lang):
    """Translate one English message for display; unknown parts stay as they are."""
    if not s or lang in (None, "", "en") or not isinstance(s, str): return s
    if "; " in s: return ("；" if lang.startswith("zh") else "; ").join(text(p, lang) for p in s.split("; "))
    if " · " in s: return " · ".join(text(p, lang) for p in s.split(" · "))
    out = s
    m = re.match(r"^(\[[^\]]*\] )?(#\d+ )?(.*)$", out, re.S); pre = (m.group(1) or "") + (m.group(2) or ""); body = m.group(3)
    if body.startswith("[") or body.startswith("#"):
        return pre + text(body, lang)
    for n, zh in QC_NAMES.get(lang, {}).items(): body = re.sub(rf"\b{n}: ", zh + "：", body)
    for pat, rep in _rules(lang):
        body = re.sub(pat, (lambda mm, r=rep: r(mm, lang)) if callable(rep) else rep, body)
    if lang == "zh-TW": body = body.translate(_TW_CHARS)
    return pre + body

def kind(k, lang): return KINDS.get(lang, {}).get(k, k)
def qc_name(n, lang): return QC_NAMES.get(lang, {}).get(n)

def localize_snapshot(snap, lang):
    """Add *_l display fields to events, check chains and QC reports (copies only; stored state is untouched)."""
    if lang in (None, "", "en"): return snap
    snap["events"] = [dict(e, kind_l=kind(e.get("kind"), lang), agent_l=seat(e.get("agent", ""), lang), msg_l=text(e.get("msg"), lang)) for e in snap.get("events", [])]
    items = []
    for it in snap.get("items", []):
        it = dict(it); it["chain"] = [dict(c, reason_l=text(c.get("reason"), lang)) for c in it.get("chain") or []]
        d = it.get("data")
        if isinstance(d, dict) and isinstance(d.get("qc"), dict):
            d = dict(d); q = dict(d["qc"]); q["summary_l"] = text(q.get("summary"), lang)
            q["checks"] = [dict(c, detail_l=text(c.get("detail"), lang), name_l=qc_name(c.get("name"), lang)) for c in q.get("checks") or []]
            d["qc"] = q; it["data"] = d
        items.append(it)
    snap["items"] = items
    return snap

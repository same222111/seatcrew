"""Print the Recommended-models tier table (markdown) from seatcrew.video.providers.CATALOG. Usage: python scripts/gen_model_table.py [en|zh]"""
import sys
from seatcrew.video import providers as PV
L = dict(en=dict(t=dict(best_quality="Best quality", best_value="Best value", free_draft="Free / draft"), k=dict(video="Video", tts="Voice / TTS"),
                 h="| Tier | Kind | Provider | Model | Good at | Env var | Docs | Get key | Pricing |", d="Docs", g="Get key", p="Pricing", none="no key"),
         zh=dict(t=dict(best_quality="最佳画质", best_value="性价比", free_draft="免费 / 草稿"), k=dict(video="视频", tts="配音 / TTS"),
                 h="| 档位 | 类型 | 服务商 | 模型 | 擅长 | 环境变量 | 文档 | 获取密钥 | 价格 |", d="文档", g="获取密钥", p="价格", none="无需密钥"))
ZH = dict(kling="电影感运动、人物与面部，3-15 秒，1080p/4K，首尾帧", runway="精致电影镜头、提示词遵循强，2-10 秒", gemini="快速文/图生视频，原生音频，角色一致（Veo 3.1 预览版已于 2026-10-22 关停）",
          minimax="性价比高、物理效果好、参考图保持角色一致，4-15 秒", luma="梦幻运镜、HDR、关键帧，5/10 秒", draft="免费离线，标注 DRAFT，仅用于检查节奏",
          elevenlabs="表现力最强，即时声音克隆，精确词级时间戳", minimax_tts="中文非常自然，情绪参数，10 秒以上样本即可克隆", doubao="自然的中文音色与情绪，声音复刻（seed-icl-2.0）",
          azure="真实 SSML 说话风格（悲伤、温柔、开心……），支持 zh-CN/en/ja", openai_tts="用 instructions 控制语气（已弃用，2027-01-06 关停）", edge="免费无需密钥，神经音色；风格仅近似")
def table(lang="en"):
    s = L[lang]; by = {e["id"]: e for e in PV.CATALOG}; out = [s["h"], "|" + "---|" * 9]
    for kind in ("video", "tts"):
        for tier, ids in PV.TIERS[kind].items():
            for i in ids:
                e = by[i]; lk = lambda u, n: f"[{n}]({u})" if u else "-"
                out.append(f"| {s['t'][tier]} | {s['k'][kind]} | {e['provider']} | `{e['model']}` | {ZH.get(i, e['good_at']) if lang == 'zh' else e['good_at']} | {', '.join('`%s`' % v for v in e['env']) or s['none']} | {lk(e['docs'], s['d'])} | {lk(e['key_url'], s['g'])} | {lk(e['pricing'], s['p'])} |")
    return "\n".join(out)
if __name__ == "__main__": print(table(sys.argv[1] if len(sys.argv) > 1 else "en"))

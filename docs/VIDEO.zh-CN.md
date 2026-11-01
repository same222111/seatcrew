# 视频工作流

[English](VIDEO.md) · [简体中文](VIDEO.zh-CN.md)

`short_video` 工作流可以从主题或脚本生成竖屏（9:16）或横屏（16:9）短视频。席位依次是：导演 · 编剧 → 审稿 → 制作（配音和画面）→ 剪辑 + 质检 → 你来批准。完整的技术说明（命令、分镜脚本格式、质检项目）见英文版 [VIDEO.md](VIDEO.md)。

## 快速开始
```bash
seatcrew --lang zh-CN video init demo              # 生成中文分镜脚本模板
seatcrew video models                               # 推荐模型，以及哪些密钥已经配置
seatcrew video estimate demo --backend kling         # 付费生成前先估算费用和时间
```

- 没有任何密钥时，会用免费的 edge-tts 配音加离线草稿画面生成一条**草稿预览**，画面上标注 DRAFT，只用于检查节奏和字幕，不代表成片效果。
- 分镜里镜头之间可以用 `transition: cut`（硬切）或淡入淡出等转场。从 v0.9.5 起，全硬切的视频也会完整拼接所有镜头。
- 片头标题默认放在顶部安全区并加大字号；可以在分镜里用 `caption_style`（`position`: `top` / `upper` / `lower`，`scale`: 0.6–2.0）调整，或在命令行用 `--caption-position`、`--caption-scale`。
- 自动质检会检查画面和声音的时长是否一致（相差超过 0.3 秒即不通过）、是否有长时间静止的画面，以及分辨率等其他技术项目。

## 推荐模型（2026-10-30 核对，价格请以官网为准）
除 edge-tts 外，各适配器仅做了模拟 HTTP 测试。

| 档位 | 类型 | 服务商 | 模型 | 擅长 | 环境变量 | 文档 | 获取密钥 | 价格 |
|---|---|---|---|---|---|---|---|---|
| 最佳画质 | 视频 | Kling AI（可灵） | `kling-3.0` | 电影感运动、人物与面部，3-15 秒，1080p/4K，首尾帧 | `KLING_API_KEY` | [文档](https://kling.ai/document-api/guides/get-started/quick-start) | [获取密钥](https://kling.ai/dev/api-key) | [价格](https://kling.ai/dev/pricing) |
| 最佳画质 | 视频 | Runway | `gen4.5` | 精致电影镜头、提示词遵循强，2-10 秒 | `RUNWAYML_API_SECRET` | [文档](https://docs.dev.runwayml.com/guides/using-the-api/) | [获取密钥](https://dev.runwayml.com/) | [价格](https://docs.dev.runwayml.com/guides/pricing/) |
| 最佳画质 | 视频 | Google Gemini API | `gemini-omni-1.1-flash` | 快速文/图生视频，原生音频，角色一致（Veo 3.1 预览版已于 2026-10-22 关停） | `GEMINI_API_KEY` | [文档](https://ai.google.dev/gemini-api/docs/omni) | [获取密钥](https://aistudio.google.com/apikey) | [价格](https://ai.google.dev/gemini-api/docs/pricing) |
| 性价比 | 视频 | MiniMax Hailuo（海螺） | `MiniMax-H3` | 性价比高、物理效果好、参考图保持角色一致，4-15 秒 | `MINIMAX_API_KEY` | [文档](https://platform.minimax.io/docs/guides/video-generation) | [获取密钥](https://platform.minimax.io/console/keys) | [价格](https://platform.minimax.io/docs/pricing/overview) |
| 性价比 | 视频 | Luma AI | `ray-3.2` | 梦幻运镜、HDR、关键帧，5/10 秒 | `LUMA_AGENTS_API_KEY` | [文档](https://docs.agents.lumalabs.ai/guides/videos/generation/) | [获取密钥](https://platform.lumalabs.ai/) | [价格](https://docs.agents.lumalabs.ai/guides/pricing/) |
| 免费 / 草稿 | 视频 | 离线草稿画面 | `-` | 免费离线，标注 DRAFT，仅用于检查节奏 | 无需密钥 | - | - | - |
| 最佳画质 | 配音 / TTS | ElevenLabs | `eleven_multilingual_v2 (default) / eleven_v3 / eleven_v4 via SEATCREW_ELEVEN_MODEL` | 表现力最强，即时声音克隆，精确词级时间戳 | `ELEVENLABS_API_KEY` | [文档](https://elevenlabs.io/docs/overview/models) | [获取密钥](https://elevenlabs.io/app/developers/api-keys) | [价格](https://elevenlabs.io/pricing/api) |
| 最佳画质 | 配音 / TTS | MiniMax Speech | `speech-2.8-hd` | 中文非常自然，情绪参数，10 秒以上样本即可克隆 | `MINIMAX_API_KEY` | [文档](https://platform.minimax.io/docs/api-reference/speech-t2a-http) | [获取密钥](https://platform.minimax.io/console/keys) | [价格](https://platform.minimax.io/docs/pricing/overview) |
| 性价比 | 配音 / TTS | ByteDance Doubao / Volcano Engine（豆包语音） | `seed-tts-2.0` | 自然的中文音色与情绪，声音复刻（seed-icl-2.0） | `VOLC_TTS_API_KEY` | [文档](https://docs.volcengine.com/docs/doubao-voice/http-chunked-sse-unidirectional-streaming-v3?lang=zh) | [获取密钥](https://console.volcengine.com/speech/app) | [价格](https://docs.volcengine.com/docs/doubao-voice/billing-instructions?lang=zh) |
| 性价比 | 配音 / TTS | Azure AI Speech | `Neural / HD voices (zh-CN-XiaoxiaoNeural ...)` | 真实 SSML 说话风格（悲伤、温柔、开心……），支持 zh-CN/en/ja | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | [文档](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice) | [获取密钥](https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices) | [价格](https://azure.microsoft.com/en-us/pricing/details/speech/) |
| 性价比 | 配音 / TTS | OpenAI TTS | `gpt-4o-mini-tts` | 用提示词控制语气（已弃用，2027-01-06 关停） | `OPENAI_API_KEY` | [文档](https://developers.openai.com/api/docs/guides/text-to-speech) | [获取密钥](https://platform.openai.com/api-keys) | [价格](https://developers.openai.com/api/docs/pricing) |
| 免费 / 草稿 | 配音 / TTS | 微软 Edge 神经音色（edge-tts） | `zh-CN-XiaoxiaoNeural etc.` | 免费无需密钥，神经音色；风格仅近似 | 无需密钥 | [文档](https://github.com/rany2/edge-tts) | - | - |

## 角色工作室
在视频工作室中打开 `/characters`。可以用照片或文字描述创建角色，生成一致的设定图，锁定参考图，绑定或克隆音色（必须征得本人同意），并组建最多 5 人的剧组拍对话场景。没有密钥时生成带 DRAFT 标记的设定图。所有云端适配器仅做了模拟测试。

中文、日文字幕需要系统里有中日韩字体（macOS 黑体、Windows 微软雅黑、Linux Noto Sans CJK），也可以把 NotoSansSC 字体放进 `SEATCREW_FONTS_DIR` 指定的文件夹。缺字体时会明确报错，而不是显示方框。

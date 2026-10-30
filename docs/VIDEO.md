# Short-video studio (`short_video` workflow)

Every video walks a chain of seats. A seat that finds a problem sends the item back to the seat that can fix it:

| Seat | Job | On failure |
|---|---|---|
| TOPIC | checks the brief: topic, template, aspect | blocks |
| WRITER | script + storyboard (shots, durations, camera moves, captions). Uses AI if one is configured, otherwise turns your notes into shots and never makes up facts | - |
| SCRIPT CHECK | readability (words per sentence), unsafe phrases, personal data, total timing | back to WRITER, with the reason |
| VOICE | narration with word timings: ElevenLabs, MiniMax, Doubao, Azure, OpenAI or edge-tts (free), or the labeled draft voice. Each character profile can use any backend | blocks |
| VISUALS | one clip/image per shot: your clips folder → Kling / Runway / Gemini / MiniMax Hailuo / Luma / Replicate video → OpenAI images → Stability, or a labeled draft card. Shows a cost/time estimate first and stops above `max_video_usd` | blocks |
| EDITOR | ffmpeg: 1080×1920 (or 1920×1080), Ken Burns on stills (2× supersampled, eased), crossfades, word-timed karaoke subtitles (Montserrat ExtraBold, outlined, safe margins), music ducked under the voice, two-pass loudness to -14 LUFS / -1.5 dBTP, H.264 High CRF 18 `slow`, BT.709, AAC 192k, faststart | - |
| QUALITY CHECK | resolution and format, source resolution (no upscaling below 66 %), sharpness (per shot, before subtitles), black and frozen frames, loudness, clipping, voice present, silence gaps, subtitle/voice sync, duration | back to the responsible seat (max `max_rewrites` rounds, then holds for you) |
| APPROVE | you watch it and approve | - |

## Quality policy
* Final quality needs a real voice (ElevenLabs, OpenAI or edge-tts) **and** real pictures (your own clips, a Replicate video model, or OpenAI/Stability images).
* Without them SeatCrew can still make an offline **draft preview**. It is labeled `DRAFT PREVIEW - NOT FINAL QUALITY` in the UI, as a banner burned into the video, in the file name (`final_DRAFT.mp4`) and in the quality report. Drafts are not for publishing. Turn them off with `allow_draft: false`.
* Keys are read from the environment only (see the env var column below) and are never written to config, items, voice profiles or reports.

## Shot list (storyboard.yaml)
```yaml
title: Why is the sky blue?
aspect: "9:16"            # or "16:9"
language: en
template: knowledge_explainer   # emotional_story | knowledge_explainer | product_promo
shots:
  - id: s01                # clip file: clips/s01.mp4|mov|webm|mkv|png|jpg|webp
    narration: "Sunlight looks white, but it holds every colour."
    caption: "Every colour"        # on-screen title, <= 80 chars, optional
    duration: 4.0                  # minimum seconds; stretched to fit the narration
    visual: "sunlight through a prism, macro, cinematic"   # prompt for AI visuals
    camera: push_in        # push_in pull_out pan_left pan_right pan_up pan_down static (stills only)
    transition: crossfade  # crossfade fade_black cut (into the next shot)
    clip: path/to/file.mp4 # optional, overrides clips/<id>.*
```
Clips should be at least 66 % of the output resolution (≥ 720×1280 for 9:16) and at least as long as the shot.

## CLI
```bash
pip install "seatcrew[video]"            # adds edge-tts; ffmpeg must be installed
seatcrew video init my_video --template knowledge_explainer --aspect 9:16
# put clips/s01.mp4 ... into my_video/, edit my_video/storyboard.yaml
seatcrew video assemble my_video --bgm music.mp3                  # TTS: best available
seatcrew video assemble my_video --voice narration.wav --words words.json -o out.mp4   # your own voice
seatcrew video qc my_video/work/manifest.json
```
`assemble` writes `final.mp4` and `quality_report.json`, and exits with code 1 if a check fails.
`words.json` is `[{"w": "Sunlight", "start": 0.12, "end": 0.48}, ...]` for your own narration; without it the timings are estimated and the report says so.

## Dashboard
`seatcrew ui short_video`: type a topic (and optionally your script) and press Submit. The Video studio panel shows the storyboard, a preview player, the quality report and a download link. CHIEF chat understands "make a video about …", "switch to 16:9" and "use the product promo template". Three shareable profiles are in `examples/short_video/profiles/`.

### Chinese / Japanese subtitles and voice tuning

Subtitles switch automatically to `Noto Sans SC Black` when the narration contains CJK text. That font is not bundled
(it is ~9 MB); install it system-wide or download the OFL `NotoSansSC-Black.otf` from
https://github.com/notofonts/noto-cjk and point the editor at it:

```bash
seatcrew video assemble my_video --tts edge --tts-voice zh-CN-XiaoxiaoNeural \
  --tts-rate=-6% --tts-pitch=-2Hz --fonts-dir ~/fonts --bgm piano.wav
# or: export SEATCREW_FONTS_DIR=~/fonts
```

`seatcrew video qc` accepts the video folder, its `final.mp4`, or `work/manifest.json`.

## Character voices

Each character gets one persistent voice profile, stored in `voices/characters.yaml` inside the data folder. The same profile is used in every shot and every later video. Profile exports include it, and exports never contain keys.

```bash
python -m seatcrew video voices presets --lang zh-CN          # list the curated presets (zh-CN, zh-TW, en, ja, es)
python -m seatcrew video voices set 妈妈 --preset zh-CN/elderly_woman --style tender --color "#FFB3C7"
python -m seatcrew video voices audition 妈妈 --emotion worried -o mom.wav
```

Storyboard shots can carry `lines:` in either form: `[{speaker: 林晚, text: "妈？", emotion: tired}]` or `"林晚: 妈？"`. Plain `narration:` still works, and the `narrator` profile reads it. The VOICE seat renders each line with that speaker's profile and keeps word timings. `--speaker-colors` (or the `speaker_colors` setting) colors each speaker's subtitles. The QC check `voice_consistency` confirms that every character used exactly one voice. In CHIEF chat you can say things like "make mom sound older" (`set_voice`).

Note: the free edge-tts endpoint has no SSML speaking styles. For edge, emotions are approximated with rate, pitch, and volume offsets. On OpenAI gpt-4o-mini-tts they are sent as `instructions`, and on ElevenLabs they map to `stability`.


## Recommended models (checked 2026-10-30)

The same three-tier list appears in the setup wizard (step 3), in the Video studio, and in CHIEF chat (ask "which video model should I use?"). Each entry has a **Test key** button that makes one cheap authenticated request; the key itself is never shown or stored. In the terminal: `python -m seatcrew video models` and `python -m seatcrew video models --test kling`.

**Recommended combos**
* **Best quality:** Kling 3.0 (or Runway Gen-4.5) + ElevenLabs (or MiniMax Speech for Chinese).
* **Best value:** MiniMax Hailuo H3 + Doubao (Chinese) or Azure Speech (multilingual, real SSML styles).
* **Free draft:** offline draft cards + edge-tts. Clearly labeled DRAFT; good for checking timing and script.

Prices change often and the numbers SeatCrew shows are **rough estimates - check current pricing** on the official page before a paid run. Regenerate this table with `python scripts/gen_model_table.py en|zh`.

| Tier | Kind | Provider | Model | Good at | Env var | Docs | Get key | Pricing |
|---|---|---|---|---|---|---|---|---|
| Best quality | Video | Kling AI (可灵) | `kling-3.0` | cinematic motion, people & faces, 3-15 s, 1080p/4K, first/last frame | `KLING_API_KEY` | [Docs](https://kling.ai/document-api/guides/get-started/quick-start) | [Get key](https://kling.ai/dev/api-key) | [Pricing](https://kling.ai/dev/pricing) |
| Best quality | Video | Runway | `gen4.5` | polished cinematic shots, strong prompt following, 2-10 s; one key also reaches partner models | `RUNWAYML_API_SECRET` | [Docs](https://docs.dev.runwayml.com/guides/using-the-api/) | [Get key](https://dev.runwayml.com/) | [Pricing](https://docs.dev.runwayml.com/guides/pricing/) |
| Best quality | Video | Google Gemini API | `gemini-omni-1.1-flash` | fast text/image-to-video with native audio, character consistency, 3-10 s (Veo 3.1 Preview shut down 2026-10-22) | `GEMINI_API_KEY` | [Docs](https://ai.google.dev/gemini-api/docs/omni) | [Get key](https://aistudio.google.com/apikey) | [Pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Best value | Video | MiniMax Hailuo (海螺) | `MiniMax-H3` | great value, physics, reference-to-video for consistent characters, 4-15 s | `MINIMAX_API_KEY` | [Docs](https://platform.minimax.io/docs/guides/video-generation) | [Get key](https://platform.minimax.io/console/keys) | [Pricing](https://platform.minimax.io/docs/pricing/overview) |
| Best value | Video | Luma AI | `ray-3.2` | dreamy camera moves, HDR, keyframes, 5/10 s | `LUMA_AGENTS_API_KEY` | [Docs](https://docs.agents.lumalabs.ai/guides/videos/generation/) | [Get key](https://platform.lumalabs.ai/) | [Pricing](https://docs.agents.lumalabs.ai/guides/pricing/) |
| Free / draft | Video | Offline draft cards | `-` | free, offline, labeled DRAFT - for checking timing only | no key | - | - | - |
| Best quality | Voice / TTS | ElevenLabs | `eleven_multilingual_v2 (default) / eleven_v3 / eleven_v4 via SEATCREW_ELEVEN_MODEL` | most expressive voices, instant voice cloning, exact word timestamps | `ELEVENLABS_API_KEY` | [Docs](https://elevenlabs.io/docs/overview/models) | [Get key](https://elevenlabs.io/app/developers/api-keys) | [Pricing](https://elevenlabs.io/pricing/api) |
| Best quality | Voice / TTS | MiniMax Speech | `speech-2.8-hd` | very natural Chinese, emotion parameter, voice clone from 10 s+ | `MINIMAX_API_KEY` | [Docs](https://platform.minimax.io/docs/api-reference/speech-t2a-http) | [Get key](https://platform.minimax.io/console/keys) | [Pricing](https://platform.minimax.io/docs/pricing/overview) |
| Best value | Voice / TTS | ByteDance Doubao / Volcano Engine (豆包语音) | `seed-tts-2.0` | natural zh-CN voices with emotions, voice clone (seed-icl-2.0) | `VOLC_TTS_API_KEY` | [Docs](https://docs.volcengine.com/docs/doubao-voice/http-chunked-sse-unidirectional-streaming-v3?lang=zh) | [Get key](https://console.volcengine.com/speech/app) | [Pricing](https://docs.volcengine.com/docs/doubao-voice/billing-instructions?lang=zh) |
| Best value | Voice / TTS | Azure AI Speech | `Neural / HD voices (zh-CN-XiaoxiaoNeural ...)` | real SSML speaking styles (sad, gentle, cheerful ...) for zh-CN/en/ja voices | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | [Docs](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice) | [Get key](https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices) | [Pricing](https://azure.microsoft.com/en-us/pricing/details/speech/) |
| Best value | Voice / TTS | OpenAI TTS | `gpt-4o-mini-tts` | tone via instructions; whisper word timing (deprecated, shuts down 2027-01-06) | `OPENAI_API_KEY` | [Docs](https://developers.openai.com/api/docs/guides/text-to-speech) | [Get key](https://platform.openai.com/api-keys) | [Pricing](https://developers.openai.com/api/docs/pricing) |
| Free / draft | Voice / TTS | Microsoft Edge neural voices (edge-tts) | `zh-CN-XiaoxiaoNeural etc.` | free, no key, good neural voices; styles only approximated | no key | [Docs](https://github.com/rany2/edge-tts) | - | - |

### 中文

| 档位 | 类型 | 服务商 | 模型 | 擅长 | 环境变量 | 文档 | 获取密钥 | 价格 |
|---|---|---|---|---|---|---|---|---|
| 最佳画质 | 视频 | Kling AI (可灵) | `kling-3.0` | 电影感运动、人物与面部，3-15 秒，1080p/4K，首尾帧 | `KLING_API_KEY` | [文档](https://kling.ai/document-api/guides/get-started/quick-start) | [获取密钥](https://kling.ai/dev/api-key) | [价格](https://kling.ai/dev/pricing) |
| 最佳画质 | 视频 | Runway | `gen4.5` | 精致电影镜头、提示词遵循强，2-10 秒 | `RUNWAYML_API_SECRET` | [文档](https://docs.dev.runwayml.com/guides/using-the-api/) | [获取密钥](https://dev.runwayml.com/) | [价格](https://docs.dev.runwayml.com/guides/pricing/) |
| 最佳画质 | 视频 | Google Gemini API | `gemini-omni-1.1-flash` | 快速文/图生视频，原生音频，角色一致（Veo 3.1 预览版已于 2026-10-22 关停） | `GEMINI_API_KEY` | [文档](https://ai.google.dev/gemini-api/docs/omni) | [获取密钥](https://aistudio.google.com/apikey) | [价格](https://ai.google.dev/gemini-api/docs/pricing) |
| 性价比 | 视频 | MiniMax Hailuo (海螺) | `MiniMax-H3` | 性价比高、物理效果好、参考图保持角色一致，4-15 秒 | `MINIMAX_API_KEY` | [文档](https://platform.minimax.io/docs/guides/video-generation) | [获取密钥](https://platform.minimax.io/console/keys) | [价格](https://platform.minimax.io/docs/pricing/overview) |
| 性价比 | 视频 | Luma AI | `ray-3.2` | 梦幻运镜、HDR、关键帧，5/10 秒 | `LUMA_AGENTS_API_KEY` | [文档](https://docs.agents.lumalabs.ai/guides/videos/generation/) | [获取密钥](https://platform.lumalabs.ai/) | [价格](https://docs.agents.lumalabs.ai/guides/pricing/) |
| 免费 / 草稿 | 视频 | Offline draft cards | `-` | 免费离线，标注 DRAFT，仅用于检查节奏 | 无需密钥 | - | - | - |
| 最佳画质 | 配音 / TTS | ElevenLabs | `eleven_multilingual_v2 (default) / eleven_v3 / eleven_v4 via SEATCREW_ELEVEN_MODEL` | 表现力最强，即时声音克隆，精确词级时间戳 | `ELEVENLABS_API_KEY` | [文档](https://elevenlabs.io/docs/overview/models) | [获取密钥](https://elevenlabs.io/app/developers/api-keys) | [价格](https://elevenlabs.io/pricing/api) |
| 最佳画质 | 配音 / TTS | MiniMax Speech | `speech-2.8-hd` | 中文非常自然，情绪参数，10 秒以上样本即可克隆 | `MINIMAX_API_KEY` | [文档](https://platform.minimax.io/docs/api-reference/speech-t2a-http) | [获取密钥](https://platform.minimax.io/console/keys) | [价格](https://platform.minimax.io/docs/pricing/overview) |
| 性价比 | 配音 / TTS | ByteDance Doubao / Volcano Engine (豆包语音) | `seed-tts-2.0` | 自然的中文音色与情绪，声音复刻（seed-icl-2.0） | `VOLC_TTS_API_KEY` | [文档](https://docs.volcengine.com/docs/doubao-voice/http-chunked-sse-unidirectional-streaming-v3?lang=zh) | [获取密钥](https://console.volcengine.com/speech/app) | [价格](https://docs.volcengine.com/docs/doubao-voice/billing-instructions?lang=zh) |
| 性价比 | 配音 / TTS | Azure AI Speech | `Neural / HD voices (zh-CN-XiaoxiaoNeural ...)` | 真实 SSML 说话风格（悲伤、温柔、开心……），支持 zh-CN/en/ja | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | [文档](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice) | [获取密钥](https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices) | [价格](https://azure.microsoft.com/en-us/pricing/details/speech/) |
| 性价比 | 配音 / TTS | OpenAI TTS | `gpt-4o-mini-tts` | 用 instructions 控制语气（已弃用，2027-01-06 关停） | `OPENAI_API_KEY` | [文档](https://developers.openai.com/api/docs/guides/text-to-speech) | [获取密钥](https://platform.openai.com/api-keys) | [价格](https://developers.openai.com/api/docs/pricing) |
| 免费 / 草稿 | 配音 / TTS | Microsoft Edge neural voices (edge-tts) | `zh-CN-XiaoxiaoNeural etc.` | 免费无需密钥，神经音色；风格仅近似 | 无需密钥 | [文档](https://github.com/rany2/edge-tts) | - | - |

**Retired / not in the tiers:** OpenAI Sora (Videos API discontinued 2026-09-24; the adapter refuses unless you point `SEATCREW_SORA_BASE` at a compatible endpoint). Google Veo 3.1 Preview in the Gemini API shut down on 2026-10-22, so SeatCrew uses `gemini-omni-1.1-flash`; Vertex AI Veo is **not** wired. Replicate stays available for any model slug (`REPLICATE_API_TOKEN`).

### How to get a key
1. Open the "Get key" link for the provider and sign in (most need billing enabled; MiniMax, Kling and Volcano Engine sell prepaid credit).
2. Put the key in your shell or a local `.env` that is not committed, e.g. `export KLING_API_KEY=...`. Azure needs both `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION`. Doubao clone upload needs `VOLC_TTS_APPID` + `VOLC_TTS_ACCESS_KEY`.
3. Press **Test key** in the panel (or `video models --test <id>`).

### Emotion and voice cloning
| Backend | Emotion | Clone |
|---|---|---|
| ElevenLabs | stability per emotion | `video voices clone 妈妈 --backend elevenlabs --sample me.wav` (Instant Voice Clone) |
| MiniMax | `voice_setting.emotion` (happy, sad, angry, fearful, surprised, calm ...) | `--backend minimax --voice-id SeatCrewMom01` (upload + voice_clone) |
| Doubao | `audio_params.emotion` | `--backend doubao --voice-id S_xxxx` (speaker id bought in the Volcano console; uses `seed-icl-2.0`) |
| Azure | real SSML `mstts:express-as` styles, zh-CN included (e.g. sad, affectionate, cheerful, whispering) | not supported (Custom Neural Voice is a separate gated product) |
| OpenAI | `instructions` | not supported |
| edge-tts | approximated with rate/pitch/volume | not supported |

Only the returned voice id is saved in the profile (`minimax_voice`, `doubao_voice`, `elevenlabs_voice`). Profiles can also carry `ref_image` (a character reference picture); the VISUALS seat sends it as the first frame / reference image where the API allows (Kling, Runway, Luma, Gemini, MiniMax). Reference images are your files: keep them out of the repo.

### What was tested live vs. mock only
All adapters have mocked-HTTP tests (`tests/test_providers.py`: request shape, polling, retries on 429/5xx, timeouts, failure messages, clone flows). **Only edge-tts and the offline draft path were run live.** Kling, Runway, Luma, Gemini Omni, MiniMax (video, speech, clone), Doubao (speech, clone), Azure, ElevenLabs clone and the Sora-compatible path are **mock-only**: they follow each provider's public docs as of 2026-10-30 but have not been run against the real service. The Doubao clone upload flow is the least certain. Please report issues.

## Character Studio (`/characters`)
Make reusable characters, group them into a cast (剧组) of up to 5, and shoot a dialogue scene where every line, face and voice comes from that cast.

**1. Characters** - from 1-6 photos, a text description, or both. Files live in `characters/<name>/` (next to your config, never in the repo):
`character.yaml`, `refs/` (your photos), `sheet/` (front, side, full body, expressions), `angles/` (stills from the 3D viewer), `model.glb`.

| Step | Backends (env var) | Without a key |
|---|---|---|
| Character sheet | OpenAI `gpt-image-1` edits, up to 10 refs (`OPENAI_API_KEY`) · Gemini image, up to 4 refs (`GEMINI_API_KEY`) · MiniMax `image-01` subject reference (`MINIMAX_API_KEY`) · Replicate `flux-kontext-pro` (`REPLICATE_API_TOKEN`) | labeled DRAFT cards made from your photo |
| Image to 3D (optional) | Meshy (`MESHY_API_KEY`) · Tripo v3 (`TRIPO_API_KEY`) · Replicate TRELLIS / any slug in `SEATCREW_3D_MODEL` | a flat textured "standee" GLB, so you can try the viewer. Not a real model |
| 360° viewer | bundled `model-viewer` 4.4.0 (Apache-2.0, `seatcrew/web/vendor/`), no CDN. "Save angle stills" stores 0/45/.../315° PNGs as extra refs | - |
| Voice | bind any Voice Library voice or preset · clone from a 10 s+ sample (MiniMax, Doubao, ElevenLabs) · audition | edge-tts preset |

The sheet is generated front first; side, full body and expressions are conditioned on your photos plus the generated front, to keep the same face.
**Lock** a character to freeze its refs (front, side and full body by default). Locked refs go to every shot the character appears in (VISUALS sends them to providers that take references).

**2. Cast (剧组)** - 1-5 characters with a role (lead, supporting, comic, antagonist, narrator, cameo) and notes, plus an optional plot and **set sheet** (one picture of the location, props and wardrobe). Save, load, delete, **export / import** as JSON. Exports include the images by default, never keys, voice clone secrets or absolute paths. Key-looking strings are removed on save.

**3. Shoot with this cast** - picks the `dialogue_scene` template:
- WRITER only gives lines to cast members. With a plot written as `Name: line` it uses those lines verbatim; otherwise the AI writer gets the cast brief. SCRIPT CHECK rejects any speaker or on-screen character outside the cast.
- Every shot is tagged with its speaker(s) and `characters` in frame, plus a `shot_type`. Coverage: wide establishing → over-the-shoulder → close-up on the speaker, then shot / reverse-shot.
- Dialogue template: 16:9, hard cuts, **no music**, a room-tone bed (-42 dB pink noise) with light reverb.
- VISUALS uses each character's locked refs plus the set sheet. VOICE uses each member's bound voice.
- **LIP-SYNC** seat (`lipsync_backend`: `none` | `kling` | `replicate`) re-times mouths on close-up and OTS video clips. Wide shots and still keyframes are skipped. Kling needs a public clip URL (`SEATCREW_PUBLIC_MEDIA_URL`). On failure, the original clip is kept and the reason is noted. **Mock-tested only.**
- QUALITY CHECK adds **continuity** checks and sends failing shots back to VISUALS. You approve at the end.

### Continuity QC
Available after a run, or on any video: `python -m seatcrew video check final.mp4 --storyboard sb.yaml --cast "My cast" [--set-sheet set.jpg] [--json report.json]`

| Check | What it does | Severity |
|---|---|---|
| `shot_drift` | first vs last sampled frame of a static shot (a person or scene morphs or vanishes) | fail |
| `local_change` | one region of a static shot changes a lot (a prop, hand or accessory appears or vanishes) | warn |
| `glitch_jump` | per-frame difference spikes inside a shot (flash frames, jump cuts, glitches), ignoring ±0.3 s around planned cuts | fail |
| `character_consistency` | each tagged character vs their locked refs (CLIP when `open_clip` + torch are installed, otherwise a colour/structure fallback) | fail with CLIP, **warn with the fallback** |
| `set_continuity` | each shot vs the cast's set sheet (palette and layout) | fail |
| `lighting_continuity` | palette and brightness jumps across cuts | warn |
| `stray_text` | OCR (tesseract) for text that is not a subtitle: signs, garbled letters, watermarks | fail. **Skipped with a warning if tesseract is not installed** |

**Limits (honest):** the fallback cannot verify identity. It compares whole frames with portrait sheets, so expect warnings on correct shots. It also cannot count objects, check which wrist a bracelet is on, or judge whether an expression fits the line. Natural gestures trigger `local_change` warnings. Those still need a human eye, which is why approval stays at the end.

### What was tested
Image, 3D and lip-sync adapters were tested with **mocked HTTP only** (`tests/test_characters.py`); none has been run against the real services. Store, cast rules, export/import, continuity checks on synthetic clips, the dialogue template, the cast workflow, server routes, CHIEF intents and the CLI were tested offline with ffmpeg.

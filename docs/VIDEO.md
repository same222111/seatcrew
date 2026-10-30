# Short-video studio (`short_video` workflow)

Every video walks a chain of seats. A seat that finds a problem sends the item back to the seat that can fix it:

| Seat | Job | On failure |
|---|---|---|
| TOPIC | checks the brief: topic, template, aspect | blocks |
| WRITER | script + storyboard (shots, durations, camera moves, captions). Uses AI if one is configured, otherwise turns your notes into shots and never makes up facts | - |
| SCRIPT CHECK | readability (words per sentence), unsafe phrases, personal data, total timing | back to WRITER, with the reason |
| VOICE | narration with word timings: ElevenLabs → OpenAI → edge-tts (free), or the labeled draft voice | blocks |
| VISUALS | one clip/image per shot: your clips folder → Replicate video model → OpenAI images → Stability, or a labeled draft card | blocks |
| EDITOR | ffmpeg: 1080×1920 (or 1920×1080), Ken Burns on stills (2× supersampled, eased), crossfades, word-timed karaoke subtitles (Montserrat ExtraBold, outlined, safe margins), music ducked under the voice, two-pass loudness to -14 LUFS / -1.5 dBTP, H.264 High CRF 18 `slow`, BT.709, AAC 192k, faststart | - |
| QUALITY CHECK | resolution and format, source resolution (no upscaling below 66 %), sharpness (per shot, before subtitles), black and frozen frames, loudness, clipping, voice present, silence gaps, subtitle/voice sync, duration | back to the responsible seat (max `max_rewrites` rounds, then holds for you) |
| APPROVE | you watch it and approve | - |

## Quality policy
* Final quality needs a real voice (ElevenLabs, OpenAI or edge-tts) **and** real pictures (your own clips, a Replicate video model, or OpenAI/Stability images).
* Without them SeatCrew can still make an offline **draft preview**. It is labeled `DRAFT PREVIEW - NOT FINAL QUALITY` in the UI, as a banner burned into the video, in the file name (`final_DRAFT.mp4`) and in the quality report. Drafts are not for publishing. Turn them off with `allow_draft: false`.
* Keys are read from the environment only (`OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `REPLICATE_API_TOKEN`, `STABILITY_API_KEY`) and are never written to config, items or reports.

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

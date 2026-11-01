# Changelog

## 0.9.5 - 2026-11-01 — Stability

### Fixed
- `transition: cut` no longer freezes the picture after the first shots: cuts are real concatenations, so every shot is in the video and the video track is as long as the audio.
- `--lang` works before or after the subcommand (`seatcrew --lang zh-CN video init x` and `seatcrew video init x --lang zh`), and `video init` inherits the global language.
- Dashboard in Chinese: seat activity, item status, rule reasons, the log seat names, the workflow title and the display toggles are translated; the support-triage example ships its own locales.
- A timing-sensitive test no longer depends on a fixed sleep.
- Per-shot voice tracks are mixed onto an exact-length silent bed: under load the voice stem could end at the last line, leaving the audio shorter than the video (seen as a flaky QC `av_stream_sync` failure).
- Draft title cards render in parallel without sharing one font file (flaky on Linux CI).
- The dashboard's net tile no longer goes negative for items that were blocked once and passed on a retry: "blocked" counts items blocked now, and the tile is labelled "Passed − blocked".
- Every UI language: option values (backends, presets, templates, aspect ratios), the content-review sample subject, settings labels, statuses with the seat's own name, support-triage check notes (no raw `category=…` / `reply written`), the CHIEF seat name and the Japanese/Spanish log lines are translated.

### Added
- QC check `av_stream_sync`: fails when the video and audio streams differ by more than 0.3 s (or a duration can't be read); the frozen-frame check stays on.
- Title cards are larger and sit in the top safe area by default; `caption_style` in the storyboard (`position`: top / upper / lower, `scale`: 0.6-2.0) or `--caption-position` / `--caption-scale` on `video assemble` change them.
- `scripts/lang_purity.py` (run in CI and by `tests/test_lang_purity.py`) flags Chinese text in English docs/locales and stray English in Chinese ones, and fails when an option value, sample subject or setting has no label in one of the five UI languages.
- Japanese and Spanish locales for the support-triage example.
- `README.zh-CN.md`, `docs/VIDEO.zh-CN.md`, `examples/trading/README.zh-CN.md` and a release-notes template (`docs/RELEASE_TEMPLATE.md`).

### Removed
- Outdated media: the v0.6 demo GIF/MP4, all pre-v0.9.4 screenshots in `docs/`, the low-resolution v0.8 video stills and the old Character Studio thumbnail. README screenshots are new v0.9.4 captures in `docs/img/`.

## 0.9.4 - 2026-10-31 — Video studio redesign

### Changed
- Short video now uses 6 visible seats (director, writer, script check, production, edit/QC, approve) instead of 10; voice and visuals run in parallel, shots render in parallel, and up to `parallel_items` videos run at once.
- Two-column video studio: approve bar under the video, models/voices tabs, AI picker only on AI seats, 390 px header; chat relabels when the language changes.
- Beginner first run: Chinese default, automatic draft, no placeholders; the shot hint comes from the real shot count; one line = one shot.
- The log panel and QC report are shown in the UI language (the log file stays English); the workflow is labelled by name (for example the Chinese name of the short-video studio) instead of `short_video`; larger flow-node labels.
- The draft banner is in the video's language.
- edge-tts is part of the default install.

### Fixed
- Subtitles break lines at punctuation/word boundaries with balanced lines, no punctuation at a line start and no lone `?`/`。`; titles and draft cards share the same word-aware `break_text`. Optional `jieba` improves Chinese word breaks.
- A rules-mode rewrite that would produce the same script stops with an actionable tip instead of futile rounds; QC retries are capped; a silent draft voice is a warning, not a failure.
- Chat answers in the question's language; audition defaults to the narrator and shows a readable not-found error.
- Windows: UTF-8 stdout/stderr in every entry point and explicit encoding for text subprocesses; `--lang` sets the UI language.
- A source checkout without `tradecrew` can open every non-trading workflow; the loader prefers the checkout's examples over a stale editable install.
- State saves retry on concurrent mutation; ffmpeg segments render in parallel but stay in order; draft renders use `veryfast`.

### Known limitations
- Not tested on a real Windows PC (only CI runners).
- Paid providers are verified with mocked tests only.
- The macOS app is not signed.
- Japanese and Spanish log translations are incomplete.
- Without `jieba`, subtitles may still split words.
- Korean fonts may be missing glyphs.

## 0.9.1 — Reliability and desktop verification

- Restore the first-run hardware/account/voice panels in all five languages.
- Reject malformed approvals and automatic-approval settings, bind browser approvals to their displayed gate, prevent duplicate concurrent actions, and retain all pending approvals.
- HTTP clients must send the current integer `pending` gate with `/api/decide` (read it from `/api/state`).
- Validate configuration types and timer values; recover cleanly from failed saves.
- Render Chinese/Japanese titles and subtitles with installed CJK fonts instead of missing-glyph boxes; support TTC font collections.
- Fix false character-consistency warnings caused by video/image colour conversion; reuse shot decoding.
- Include model-card translations and free Edge TTS in desktop builds; resolve bundled workflows correctly.
- Start local servers without slow reverse DNS lookups; open the full trading terminal from the launcher. Demo trading also disables news feeds, and workflows keep absolute data paths.
- Add keyboard/touch-friendly click selection to the cast builder in all five languages.
- Correct the API-key counter and isolate offline tests from logged-in CLI accounts.
- Expand regression and installed-app smoke coverage; support version-checked release branches.

See [QA evidence and limitations](docs/qa-v0.9.1.md).

## 0.9.0 - 2026-10-31

### Added
- **Character Studio** (`/characters` in the Video studio): characters from photos or a description, consistent sheets (front / side / full body / expressions), optional image-to-3D with a bundled 360° viewer, locked refs, voice binding and cloning, casts of up to 5 with roles, and **Shoot with this cast** (dialogue scene with coverage, hard cuts, room tone, optional lip-sync, continuity QC). Cast export/import as a `.cast.json` file.
- Model cards in the setup wizard, Video studio and CHIEF chat, translated in 5 languages, with key paste (validated, never echoed back).
- Zero-key sample: the **Fill in a sample** button and `/api/sample` give a ready short video in the UI language (free edge-tts voice + labeled DRAFT visuals).
- CHIEF chat drawer and a shared design system (`neon.css`).
- Headless smoke test (`scripts/smoke_app.py`) for an installed app. CI runs it on the built wheel (Linux, Windows, macOS) and on the real installers (Windows setup.exe after a silent install, the macOS dmg, the Linux AppImage). The release fails if any of them does not start.
- The Playwright overflow test now runs in CI with Playwright's own Chromium (it no longer skips).

### Fixed
- `pip install` from the wheel was missing the `seatcrew.video` package, so the desktop app crashed on start (`ImportError: localvoice`). The installers were not affected.
- Ollama: the default model `llama3.2` was hard-coded. When it is not installed, SeatCrew now uses the first installed model. Requests send `num_predict` and use a longer timeout.
- A small model's almost-JSON reply no longer crashes a seat (it parses the label or abstains).
- CHIEF no longer says "no AI connected" when the AI is connected but did not answer.
- Profile import: a section or setting with the wrong type is now a clean error instead of HTTP 500.
- The writer's "no AI and no script" stop message is translated, and an AI storyboard with an invalid camera, transition or duration is repaired instead of rejected.
- Content review counted Chinese/Japanese text as a handful of words. Word counts are now CJK-aware.
- Dialogue scenes from draft (still) images failed QC as "frozen frames". Still shots now get a barely visible drift.
- Cast members without a voice blocked the VOICE seat. They now get a free default voice that matches their gender and age, which you can change in Character Studio.
- Importing a damaged cast file shows a clear message.
- Setup recommendations are translated. The launcher clock uses 24-hour time. The default UI font size is now 14.

### Honest notes
- **Paid providers (Kling, Runway, Gemini, MiniMax, Luma, ElevenLabs, Doubao, Azure, OpenAI, Meshy, Tripo, Replicate and the paid LLMs) have NOT been tested with real keys.** Their adapters are tested with mocked HTTP only. Expect rough edges, and please report them.
- Real end-to-end runs were done with no keys (edge-tts plus DRAFT visuals) and with a local Ollama model (`qwen2.5:0.5b`). A model that small can chat and review, but writes poor storyboards, which the script check correctly rejects.
- The Codex / Claude CLI sign-in was checked up to the sign-in link only.
- **Voice cloning needs consent.** Only clone your own voice, or a recording whose speaker explicitly agreed. SeatCrew asks for a consent checkbox per cloned voice and stores the statement and date.
- The macOS app is unsigned (first open: right-click → Open).

# Changelog

## 0.9.1 — Reliability and desktop verification

- Restore the first-run hardware/account/voice panels in all five languages.
- Reject malformed approvals and automatic-approval settings, bind browser approvals to their displayed gate, prevent duplicate concurrent actions, and retain all pending approvals.
- HTTP clients must send the current integer `pending` gate with `/api/decide` (read it from `/api/state`).
- Validate configuration types and timer values; recover cleanly from failed saves.
- Fix false character-consistency warnings caused by video/image colour conversion; reuse shot decoding.
- Include model-card translations and free Edge TTS in desktop builds; resolve bundled workflows correctly.
- Start local servers without slow reverse DNS lookups; open the full trading terminal from the launcher. Demo trading also disables news feeds, and workflows keep absolute data paths.
- Add keyboard/touch-friendly click selection to the cast builder in all five languages.
- Correct the API-key counter and isolate offline tests from logged-in CLI accounts.
- Expand regression and installed-app smoke coverage; support version-checked release branches.

See [QA evidence and limitations](docs/qa-v0.9.1.md).

## 0.9.0 - 2026-10-31

### Added
- **Character Studio** (`/characters` in the Video studio): characters from photos or a description, consistent sheets (front / side / full body / expressions), optional image-to-3D with a bundled 360° viewer, locked refs, voice binding and cloning, casts (剧组) of up to 5 with roles, and **Shoot with this cast** (dialogue scene with coverage, hard cuts, room tone, optional lip-sync, continuity QC). Cast export/import as a `.cast.json` file.
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

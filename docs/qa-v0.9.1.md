# SeatCrew 0.9.1 quality release

Scope: audit the v0.9.0 release, reproduce defects before fixing them, exercise all four shipped workflows and shared services, and deliver tested desktop artifacts. No live trading, no cloud-provider spend, and no claim that finite testing proves every possible bug absent.

## Reproduced and fixed

- The first-run detection renderer called an out-of-scope `lang()` and collided with the language input. Detection, account login and local voice panels disappeared. The real renderer is now exercised for all five UI languages.
- Human approval accepted non-boolean values (including the string `false`) as approval. It now rejects malformed decisions before mutating the item.
- Stale HTTP approvals now carry the rendered `pending` gate index and cannot approve a later, unseen human gate. `/api/decide` requires this integer from `/api/state`; Python/CLI callers retain optional keyword compatibility.
- Boolean workflow settings (including `*_auto_approve`) reject strings/numbers; the gate itself accepts only literal `true`, including for hand-edited legacy files.
- Concurrent human approvals executed downstream actions twice. Decision validation and chain resumption are serialized without holding the dashboard/event lock.
- The 200-item history cap discarded outstanding approvals; the 40-item dashboard cap hid them. Outstanding approvals are retained, persisted and visible beyond those limits. Item snapshots are replaced atomically.
- Malformed configuration shapes, string booleans, non-finite intervals and out-of-range timers were accepted or produced internal errors. Updates validate before application, serialize concurrent saves, and roll back memory if persistence fails.
- Continuity QC falsely rejected an extracted reference of the same video frame. RGB conversion now precedes resizing for both sources (measured fallback similarity 0.616 before, 1.0 after). Multi-character shots share decoded frames and reference images beyond the four-image limit are no longer decoded.
- Desktop bundles omitted model-card translations. The bundle now includes video JSON resources; installed-app smoke tests fetch the actual model catalog.
- Desktop installations omitted the free Edge TTS dependency. The desktop extra includes it. FFmpeg/ffprobe remain external prerequisites for video; the local QA environment supplies them.
- The homepage counted logged-in CLI accounts as API keys. The count now excludes account and key-free providers.
- Offline tests discovered and called a developer's signed-in CLI. Tests now isolate CLI discovery, provider keys, cache state and HTTP calls, while allowing explicit fake-CLI fixtures.

- Frozen bundles exposed the workflow folder as a namespace package (`__file__ = None`); loader now resolves its package search path.
- Local server startup waited tens of seconds in reverse DNS. Loopback servers now bind without hostname resolution.
- The desktop trading entry opened the generic dashboard, hiding Strategy Lab. It now opens the full paper terminal.
- Cast selection required drag-and-drop. Character buttons now also support click, keyboard activation and touch, with translated guidance.

## Verification matrix

| Area | Verification |
| --- | --- |
| Engine | Rules, AI veto/abstention, first block, human approve/reject, concurrency, restart, history retention, runner |
| Config/profiles | Type validation, atomic saves, failed-write rollback, save/load/reset, export/import, secret stripping |
| Onboarding | Actual browser: Chinese language, detection, recommended account panel, demo mode, starter selection |
| Content review | Actual browser: sample checks, local publish after approval, rejection, saved profile/share code, offline CHIEF explanation |
| Support triage | Actual browser and API tests: classification, privacy rejection, human approval |
| Short video | Actual Edge TTS + DRAFT visuals: Chinese sample, 1080x1920, 25.7 seconds, QC and human gate; synthetic video/audio regression tests |
| Character Studio | Actual browser: character creation, DRAFT sheet, lock, voice binding, 3D standee, six camera-angle captures, click-to-add cast save; mocked provider and cast tests |
| Paper trading | Demo-price strategy, backtest and check-chain tests; browser terminal verification |
| Providers | Mocked request/response/error/polling tests. No paid live-provider validation |
| Packaging | Wheel in clean environment; actual macOS app; Windows/macOS/Linux CI builds and installed-app smoke required before release |

- Demo-mode trading disables news feeds as well as live prices; desktop workflows use absolute data paths so another working-directory change cannot redirect their writes.

## Limits

Paid image/video/3D/LLM/TTS services are validated with mocks only. Ollama and GPU voice engines require separately installed models/hardware and were not exercised live on this Mac. Voice-clone consent rejection is tested; no real person's voice was cloned. A DRAFT standee is not a generated 3D character. Tesseract OCR and CLIP are optional and were not installed; fallback QC reports its limitations. The local PowerShell and standalone Playwright checks are unavailable; platform CI is configured for Windows/Chromium, and local UI testing uses the connected in-app browser. This is not a full accessibility certification.

## Release

The package version must match the tag or `release/v<version>` branch. A release branch is created from reviewed main; artifacts publish only after every platform build and smoke test succeeds. Existing tag-triggered releases remain supported. The macOS app is ad-hoc signed, not Apple-notarized.

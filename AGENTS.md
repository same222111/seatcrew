# AGENTS.md: read this first (for humans and coding AIs)

> If you are an AI coding assistant (Codex, Claude Code, Cursor, Copilot, ChatGPT…) asked to modify or extend this repo, read this file and [ARCHITECTURE.md](ARCHITECTURE.md) first. The trading example has its own map in [examples/trading/AGENTS.md](examples/trading/AGENTS.md).

## Hard rules (do not break)
1. **Every action goes through the check chain.** Never perform a side effect (publish, send, order, write) outside a seat's `check`/`rules`. Put irreversible actions **after** a human seat or a strict check seat.
2. **AI can only make things more cautious.** A seat's AI answers with a label. Only `block_labels` may block, and nothing may un-block or skip a seat. AI failures abstain.
3. **Rules-only must always work.** Every workflow must run with no API key. Tests must be offline and mock HTTP (`monkeypatch` `seatcrew.llm._post`).
4. **Never write API keys** into config files, logs, the UI, the API or tests. Keys come only from the environment or `.env`.
5. **All UI strings go through locales.** Core keys live in `seatcrew/locales/*.json`, and workflow keys live in the workflow's `locales/`. When you add a key, add it to every language.
6. **Trading stays paper-only.** `examples/trading` must never send real orders.
7. Keep `pytest -q` green and add a test for every new seat or rule.

## Map
```
seatcrew/                 the framework (domain-agnostic)
  core.py                 Seat, HumanSeat, Chief, Workflow, Runner
  llm.py                  providers + ask_role / write / test_connection
  config.py               Config, base_defaults, LANGUAGES
  yamlflow.py             YAML -> workflow (rule types listed at the top of the file)
  loader.py  cli.py       find/build workflows; seatcrew list|new|run|ui|test-ai
  server.py  web/         generic dashboard + JSON API
  locales/   templates/   core strings; scaffolds for `seatcrew new`
examples/
  trading/                flagship: the full TradeCrew app (tradecrew package, its own UI, tests, AGENTS.md)
  content_review/         Python workflow with a human gate and publish/unpublish
  support_triage/         YAML-only workflow
tests/                    framework tests (engine, YAML, examples, CLI, HTTP, locales)
```

## Recipes
- **New workflow (YAML, no code):** run `seatcrew new <name>`, edit `workflows/<name>/workflow.yaml` (seats, rules, `ai:` labels, `human: true`, `chain`, `submit` form, `sample_items`), then run `seatcrew ui workflows/<name>`.
- **New workflow (Python):** run `seatcrew new <name> --python`. Write one `Seat` subclass per job (`rules(item) -> (ok, reason)`, plus `labels`/`block_labels` for AI), then call `setup([...seats], chain)` in your `Workflow`. Implement `build(config_path, state_dir)`.
- **Where items come from:** override `Workflow.collect()` to pull from an inbox, an RSS feed, a folder or an API. By default items come from the dashboard form or `submit()`.
- **Human approval:** add a `HumanSeat` (or `human: true` in YAML). The setting `<seat>_auto_approve: true` approves automatically (useful for demos). The CLI flag `run --yes` approves everything.
- **Undo on review:** in your REVIEW seat, revert the side effect when the check fails (as content_review un-publishes and trading reverts the paper fill).
- **Producer seat** (generates content): use `llm.write(seat, prompt, cfg)` with a rules/template fallback.
- **Extra dashboard tables:** return `[dict(title, columns, rows)]` from `Workflow.panels()`.
- **New AI provider:** add one entry to `PROVIDERS` in `seatcrew/llm.py` if it is OpenAI-compatible. Otherwise add a branch in `chat()` and a mocked test.
- **New language:** see "Adding a language" in the README.

## Desktop app / installers
- `seatcrew/desktop.py` must stay importable without pywebview (falls back to the browser); tests run it with `--no-window --smoke`.
- Change install steps in **both** `install.sh` and `install.ps1`, keep `--dry-run` printing every step and the final `RESULT` line (tests and INSTALL_WITH_AI.md rely on it).
- Bump the version in `pyproject.toml`, `seatcrew/__init__.py`, `packaging/seatcrew.spec` and `packaging/seatcrew.iss` together (a test checks this).
- README screenshots live in `docs/img/` (PNG, taken from the current UI, one English and one zh-CN where it matters). Replace them rather than adding old ones back.

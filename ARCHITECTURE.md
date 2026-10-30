# Architecture

```
                 ┌──────────────── Runner (every N s, or "Run now") ────────────────┐
                 ▼                                                                   │
  collect() ──► CHIEF.plan(items) ──► for each item:                                 │
  (form/API/      (may HOLD)            seat1.check ─OK─► seat2.check ─OK─► … ─► REVIEW ─► done
   feed/file)                              │BLOCKED         │WAITING (human)
                                           ▼                ▼
                                     item stops      parks until decide(id, approve)
  every step ──► event log (state/<wf>/log.jsonl) ──► dashboard (seat grid · timelines · live log)
```

## Modules (`seatcrew/`)
| File | Responsibility |
|---|---|
| `core.py` | `Seat` (rules + optional AI labels), `HumanSeat`, `Chief`, `Workflow` (check chain, `submit`/`collect`/`run_cycle`/`decide`, log, items, `snapshot`/`definition`), `Runner` |
| `llm.py` | Provider registry `PROVIDERS`, `chat()`, `test_connection()`, `ask_role(seat, prompt, labels, cfg)`, `write()` (free text for producer seats), budget, key scrubbing |
| `config.py` | `Config` (YAML + defaults + validation, atomic save), `base_defaults(seats, prompts, settings)`, `load_env`, `LANGUAGES` |
| `yamlflow.py` | Builds a workflow from YAML (`RuleSeat`, rule types, `human: true`, `ai:` labels, sample items) |
| `loader.py` | Resolves `name` / folder / file to a workflow (`workflow.yaml` or `workflow.py` with `build(config_path, state_dir)`) |
| `server.py` + `web/index.html` | Generic dashboard + JSON API: `/api/state`, `/api/config` (GET/POST), `/api/submit`, `/api/decide`, `/api/run`, `/api/test-connection`, `/api/locale/<code>` |
| `i18n.py` + `locales/` | Core strings; workflow `locales/` override and extend them (seat names `seat_<name>`, form fields `field_<name>`, settings `set_<key>`) |
| `cli.py` | `list`, `new`, `run`, `ui`, `test-ai` |
| `templates/` | Scaffolds used by `seatcrew new` |

## Semantics (tested in `tests/test_engine.py`)
- `check(item)` returns `(True, why)` for OK, `(False, why)` for BLOCKED (the item stops) or `(None, why)` for WAITING (it parks at a human seat).
- A seat that raises an exception counts as BLOCKED, with the error as the reason.
- Default `Seat.check` runs `rules(item)` first. Only if the rules pass and the seat has `labels` is the assigned AI asked. A label in `block_labels` blocks, so the AI can never un-block.
- `Workflow.gate(seat, item)` is a hook that overrides a seat for an item (CHIEF hold uses it).
- Items persist to `state/<wf>/items.json`, so a waiting item survives a restart. Set `persist_items = False` for transient items (trading orders).
- `snapshot()` and `definition()` are all the dashboard needs. `panels()` adds extra tables, such as the trading portfolios.

## Trading on the framework
`examples/trading/tradecrew/seats.py`: `Crew(seatcrew.Workflow)` has nine seats with chain SCAN → JUDGE → RISK → SIZE → FILLS → REVIEW, `interval_key = "scan_interval_sec"`, `done_status = "filled"`, and a `gate()` for CHIEF hold. `tradecrew.providers` *is* `seatcrew.llm`. The full TradeCrew terminal (`tradecrew start`) and the generic dashboard (`seatcrew ui trading`) drive the same `Crew`.

## Desktop app and packaging
```
seatcrew/desktop.py   App: launcher server (wizard + workflow picker, web/launcher.html) on a free port
                      -> open_workflow(name): loader.build + server.serve on another free port + Runner
                      -> pywebview window (WebView2 / WebKit / Qt or GTK); window closed -> App.stop() shuts every server
packaging/            seatcrew.spec (PyInstaller, all OS) · build_appimage.sh · build_macos.sh (.app + .dmg)
                      seatcrew.iss (Windows installer, desktop shortcut) · icons · make_icon.py
install.sh / .ps1     per-user venv install + shortcuts, --dry-run; see INSTALL_WITH_AI.md
.github/workflows/release.yml   tag v* -> builds Win/macOS/Linux artifacts -> GitHub Release
```
User data (config.<workflow>.yaml, state/, .env, workflows/) lives in the per-user data folder (`SEATCREW_HOME` overrides), never inside the program folder.

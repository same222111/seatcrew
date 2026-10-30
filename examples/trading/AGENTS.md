# examples/trading/AGENTS.md: TradeCrew architecture map (flagship example)

> Framework-level rules and the core map are in the root [AGENTS.md](../../AGENTS.md). Paths below are relative to `examples/trading/`.

> If you are an AI coding assistant (Codex, Claude Code, Cursor, Copilot, ChatGPT…) asked to modify this repo, read this file first. It lists every module, the extension points and the rules you must keep.

## Hard rules (do not break)
1. **Paper trading only.** Never add code that sends real orders. `broker.LiveBroker` must stay a disabled stub.
2. **Never write API keys** into `config.yaml`, logs, the UI or the API. Keys are read only from the environment or `.env` (`providers.py`, `config.key_status()` returns booleans).
3. **AI can only make trades more conservative.** A seat's AI may block, veto, halve or wait. It must never create or enlarge an order. AI errors abstain (`ok=False`) and never block.
4. **Idea ≠ trigger.** Every order must walk the full check chain; never call `broker.fill` outside `Fills.check`.
5. Keep `pytest -q` green and offline. Tests use mocked HTTP and the `demo` price source.
6. All user-visible UI strings go through `locales/*.json`. When you add a key, add it to **every** locale (`tests/test_i18n.py` enforces this).

## Map
```
examples/trading/tradecrew/
  config.py      DEFAULTS, SEATS, PROVIDERS, LANGUAGES, Config (load/merge/validate/save config.yaml), legacy migration
  seats.py       ★ the crew: Seat base class, the 9 seats, Crew (shared state + check chain), Runner (schedule)
  providers.py   alias of seatcrew.llm (the framework LLM layer)
  strategies.py  strategy functions -> target-weight DataFrames, registry STRATEGIES, explain()
  backtest.py    vectorized backtester (costs, train/test split) + SCAN->JUDGE research loop
  data.py        price sources (yfinance/alpaca/polygon/demo) with fallback, RSS headlines, hard timeouts
  broker.py      sessions (pre/regular/after/overnight/closed), PaperBroker (fill/revert), LiveBroker stub
  server.py      stdlib HTTP server: dashboard + JSON API (/api/state, /api/config, /api/test-connection, /api/backtest, /api/research, /api/locale/<code>)
  i18n.py        locale loader with English fallback (also used by the CLI)
  cli.py         `tradecrew start|init|test-ai|backtest|research|config [--lang]`
  web/index.html single-file dashboard (no build step); strings via T(key)
  locales/*.json en, zh-CN, zh-TW, ja, es
tests/           pytest; test_check_chain.py documents the blocking semantics
```

## The eight seats (+ REVIEW) and the Runner
| Seat | Owns | Rule logic | Optional AI labels |
|---|---|---|---|
| CHIEF | commander: plans each cycle | logs the plan | `proceed` / `hold` (hold = no new entries this cycle) |
| QUANT | risk dial | benchmark < 200d SMA → cautious, 20d vol > 35% → defensive, or a manual setting | `normal` / `cautious` / `defensive` (more cautious only) |
| STOCKS | universe + information | watchlist ∪ strategy symbols, price data, RSS news | headline sentiment `bullish` / `bearish` / `neutral` |
| SCAN | research → ideas | strategy target weights → order ideas; ranks candidates | `candidate` / `skip`; picks params in the Lab |
| JUDGE | evaluates ideas | blocks falling knives (≤ −5% day) and bearish news | `approve` / `reject`; judges robustness in the Lab |
| RISK | hard limits | kill switch, daily loss cap, orders/day, market closed | `approve` / `veto` |
| SIZE | sizing | dollars × dial → shares; whole shares off-hours; min $1 | `keep` / `halve` |
| FILLS | order desk | PaperBroker fill with session slippage | `now` / `wait` |
| REVIEW | post-trade replay | slippage ≤ 2× session estimate, no overfill, no negative cash; failure **reverts** the paper fill | `ok` / `flag` |
| Runner | schedule | runs `Crew.run_cycle()` every `scan_interval_sec`; "Run now" wakes it | n/a |

**Cycle:** CHIEF starts → STOCKS loads data → QUANT sets the dial → SCAN ranks and turns strategies into ideas → CHIEF approves the plan → each idea walks the **check chain** `SCAN → JUDGE → RISK → SIZE → FILLS → REVIEW`. Each step logs `CHECK_OK` or `CHECK_BLOCKED` with a reason. The first block stops that order, and the order card in the dashboard shows where it stopped.

## Extension points (recipes)
- **Add a seat:** subclass `Seat` in `seats.py` and implement `check(self, order) -> (ok: bool, reason: str)`. Insert it into `Crew.chain` (order matters), then add its name to `config.SEATS` and `DEFAULT_PROMPTS`, add `seat_<name>` to every locale file, and add it to `SEATORDER` in `web/index.html`. Add a blocking test in `tests/test_check_chain.py`.
- **Add a strategy:** write `def my_strat(C, V, p) -> DataFrame[weights]` in `strategies.py` (C = closes, V = volumes, decided at close t). Register it in `STRATEGIES`, add defaults under `DEFAULTS["strategies"]`, and if it uses special symbols update `symbols_for`. It then gets its own paper portfolio, Settings fields and Lab backtests automatically. Add a grid to `backtest.GRID` for the research loop.
- **Add a price source:** write `def my_source(symbols, days) -> {sym: DataFrame[Open,High,Low,Close,Volume]}` in `data.py`. Register it in `PRICE_SOURCES` and `DEFAULTS["data"]["sources"]` (with `key_env` if needed).
- **Add a news source:** no code needed. Add an RSS URL with `{symbol}` in Settings.
- **Add an AI provider:** if it is OpenAI-compatible, just add a `PROVIDERS` entry in `seatcrew/llm.py` (`kind: "openai"`, base_url, model, key_env). Otherwise add a `kind` branch in `seatcrew/llm.py chat()` and a mocked case in `tests/test_providers.py`.
- **Add a language:** copy `locales/en.json` to `locales/<code>.json`, translate the values (keep `{placeholders}`), and add `<code>: "Native name"` to `config.LANGUAGES`. Run `pytest tests/test_i18n.py`.

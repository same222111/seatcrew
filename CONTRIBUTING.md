# Contributing

Thanks for helping! SeatCrew is a domain-agnostic seat-workflow framework; read [AGENTS.md](AGENTS.md) first. The trading example (TradeCrew) is **paper-trading only**; PRs that add live order routing will not be merged.

## Dev setup
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q            # all tests are offline (mocked HTTP + synthetic "demo" prices)
seatcrew ui content_review   # http://127.0.0.1:8800
tradecrew start              # trading example, http://127.0.0.1:8787
```

## Adding things
- **Workflow / example**: `seatcrew new <name>` (YAML) or `--python`; contribute it under `examples/<name>/` with tests in `tests/`.
- **AI provider**: add an entry to `PROVIDERS` in `seatcrew/llm.py`; if it is not OpenAI-compatible add a branch in `chat()` and a mocked test.
- **Price source**: write `fn(symbols, days) -> {symbol: DataFrame[Open,High,Low,Close,Volume]}` in `examples/trading/tradecrew/data.py`, register it in `PRICE_SOURCES` and `DEFAULTS["data"]["sources"]`.
- **Strategy**: write `fn(C, V, params) -> DataFrame of target weights` in `examples/trading/tradecrew/strategies.py`, register it in `STRATEGIES`, add default params in `config.py`. It is automatically backtestable and gets its own paper portfolio.
- Please include an honest out-of-sample backtest vs buy-and-hold in your PR description.

## Rules
- Never commit keys, `.env`, `config*.yaml` or `state/`.
- Keep the dependency footprint small (stdlib HTTP for providers).
- Run `pytest -q` before opening a PR.

# Honest research notes

Daily data from yfinance, 2016-09 → 2026-10, 3 bp per side costs, last 30% of the period held out as out-of-sample (TEST, ≈ Nov 2023 → Oct 2026). Default parameters. Benchmark: buy & hold QQQ (TEST: CAGR 23.8%, max drawdown −22.8%, Sharpe 1.14).

| Strategy | Full CAGR | Full max DD | TEST CAGR | TEST max DD | TEST Sharpe |
|---|---|---|---|---|---|
| Trend + RSI(2) on QQQ | 21.9% | −21.9% | 23.5% | −13.5% | 1.24 |
| Vol-managed QQQ | 18.2% | −27.1% | 20.9% | −19.0% | 1.15 |
| Momentum swing (watchlist) | 23.0% | −32.2% | 23.2% | −27.1% | 0.97 |
| Rotation (5 stocks) | 23.2% | −35.3% | 19.1% | −33.3% | 0.78 |
| Short-term team (daily proxy) | 15.0% | −24.3% | 12.4% | −14.8% | 0.94 |

**Takeaways:** none of them clearly beat holding QQQ on return out-of-sample. The trend filters mostly cut drawdowns. Single-stock universes were picked with hindsight, which flatters them. Treat the Strategy Lab as a tool for finding out what does *not* work.

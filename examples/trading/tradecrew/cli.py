"""Command line: tradecrew start | init | test-ai | backtest | research | config"""
import argparse, json, sys, threading, webbrowser
from .config import Config, PROVIDERS, SEATS, LANGUAGES, load_env
from .i18n import t
DISCLAIMER = "TradeCrew is PAPER TRADING ONLY. Educational software, not financial advice. No live orders are ever sent."

def main(argv=None):
    from seatcrew.textio import utf8_stdio; utf8_stdio()
    ap = argparse.ArgumentParser(prog="tradecrew", description=DISCLAIMER)
    ap.add_argument("--config", default="config.yaml"); ap.add_argument("--env", default=".env")
    ap.add_argument("--lang", choices=list(LANGUAGES), help="message language (default: config.yaml language)")
    sp = ap.add_subparsers(dest="cmd")
    s = sp.add_parser("start", help="run the agent team + dashboard"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8787)
    s.add_argument("--state", default="state"); s.add_argument("--open", action="store_true")
    sp.add_parser("init", help="interactive first-run setup in the terminal")
    ta = sp.add_parser("test-ai", help="real minimal call to a provider"); ta.add_argument("provider", nargs="?", help="omit = all providers with a key"); ta.add_argument("--model")
    b = sp.add_parser("backtest"); b.add_argument("strategy"); b.add_argument("--years", type=float, default=5)
    r = sp.add_parser("research", help="proposer -> validator loop"); r.add_argument("strategy"); r.add_argument("--rounds", type=int, default=3); r.add_argument("--years", type=float, default=5)
    c = sp.add_parser("config", help="show or set config"); c.add_argument("--set", nargs=2, action="append", metavar=("KEY.PATH", "JSON_VALUE"), default=[])
    a = ap.parse_args(argv); load_env(a.env); cfg = Config(a.config); L = a.lang or cfg["language"]
    if a.cmd in (None, "start"):
        from .seats import Crew, Runner; from .server import serve
        print(t("cli_disclaimer", L)); team = Crew(cfg, getattr(a, "state", "state"))
        host, port = getattr(a, "host", "127.0.0.1"), getattr(a, "port", 8787); url = f"http://{host}:{port}"
        try: srv = serve(cfg, team, host, port)
        except OSError as e: print(t("cli_bind", L, addr=f"{host}:{port}", err=e.strerror)); return 1
        Runner(team).start()
        print(t("cli_dashboard", L, url=url))
        if getattr(a, "open", False): webbrowser.open(url)
        try: srv.serve_forever()
        except KeyboardInterrupt: team.stop.set()
    elif a.cmd == "test-ai":
        from .providers import test_connection
        from .config import key_status
        names = [a.provider] if a.provider else [n for n, ok in key_status().items() if ok and PROVIDERS[n]["key_env"]]
        if not names: print(t("cli_nokeys", L)); return 1
        bad = 0
        for n in names:
            r = test_connection(n, cfg.data, a.model)
            print(f"{'OK ' if r['ok'] else 'ERR'} {n:<10} {r.get('model')}  {r['latency_ms']}ms  {r.get('reply') or r.get('error')}"); bad += not r["ok"]
        return 1 if bad else 0
    elif a.cmd == "backtest":
        from .backtest import backtest
        r = backtest(a.strategy, cfg.data, a.years); r.pop("equity"); r.pop("benchmark_equity", None); print(json.dumps(r, indent=1))
    elif a.cmd == "research":
        from .backtest import research
        r = research(a.strategy, cfg.data, a.rounds, a.years, log=lambda who, m: print(f"{who:>9}: {m}")); print(json.dumps(r["best"], indent=1))
    elif a.cmd == "config":
        for k, v in a.set:
            patch = cur = {}; parts = k.split(".")
            for x in parts[:-1]: cur[x] = {}; cur = cur[x]
            try: cur[parts[-1]] = json.loads(v)
            except json.JSONDecodeError: cur[parts[-1]] = v
            cfg.update(patch); print(f"set {k}")
        if not a.set: print(json.dumps(cfg.data, indent=1))
    elif a.cmd == "init":
        print(t("cli_disclaimer", L) + "\n")
        lang = input(f"Language {list(LANGUAGES)} [{cfg['language']}]: ").strip() or cfg["language"]
        cap = input(f"Starting paper capital [{cfg['capital']}]: ").strip(); wl = input(f"Watchlist, comma separated [{','.join(cfg['watchlist'])}]: ").strip()
        prov = input(f"AI provider for all seats ({'/'.join(['rules', *PROVIDERS])}) [rules]: ").strip() or "rules"
        patch = dict(setup_complete=True, language=lang, seats={r: dict(provider=prov) for r in SEATS})
        if cap: patch["capital"] = float(cap)
        if wl: patch["watchlist"] = [s.strip() for s in wl.split(",") if s.strip()]
        cfg.update(patch); print(t("cli_saved", lang, path=cfg.path))
    return 0

if __name__ == "__main__": sys.exit(main())

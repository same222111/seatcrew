"""seatcrew CLI:  list | new <name> [--python] | run <workflow> [--yes] [--cycles N] | ui <workflow> [--port] | test-ai
<workflow> is a bundled example name (trading, content_review, support_triage), a folder, or a workflow.yaml/.py path."""
import argparse, json, re, sys, time, webbrowser
from pathlib import Path
from .config import LANGUAGES, load_env
from .i18n import t
from . import loader

def _lang(a, wf=None): return a.lang or (wf.cfg.data.get("language") if wf else None) or "en"

VIDEO_LANG_CMDS = ("init",)

def split_global(argv):
    """Pull the global options (--lang X / --lang=X / --env X) out of argv wherever they are, so
    `seatcrew --lang zh-CN video init x` and `seatcrew video init x --lang zh-CN` both work.
    Only the video subcommands that take their own --lang keep a trailing --lang (it is re-added there)."""
    glob, rest, i = {}, [], 0
    in_video = False
    while i < len(argv):
        x = argv[i]
        if not rest and x == "video": in_video = True
        key = next((k for k in ("lang", "env") if x == f"--{k}" or x.startswith(f"--{k}=")), None)
        # inside `video`, --lang belongs to the subcommand once it is named (e.g. voices --lang); only lift it before that
        if key and not (in_video and len(rest) >= 2):
            if "=" in x: val = x.split("=", 1)[1]; i += 1
            elif i + 1 < len(argv): val = argv[i + 1]; i += 2
            else: rest.append(x); i += 1; continue
            if key == "lang":
                val = _norm_lang(val, LANGUAGES)
                if val is None: raise SystemExit(f"seatcrew: error: --lang: unknown language {argv[i - 1]!r} (choose from {', '.join(LANGUAGES)})")
            glob[key] = val; continue
        rest.append(x); i += 1
    return glob, rest

def _norm_lang(v, langs):
    v = (v or "").replace("_", "-")
    for l in langs:
        if l.lower() == v.lower(): return l
    if v.lower() in ("zh", "zh-cn", "zh-hans", "cn"): return next((l for l in langs if l == "zh-CN"), None)
    if v.lower() in ("zh-tw", "zh-hk", "zh-hant"): return next((l for l in langs if l.startswith("zh-T")), None)
    base = v.split("-")[0].lower(); return next((l for l in langs if l.lower() == base), None)

def main(argv=None):
    from .textio import utf8_stdio; utf8_stdio()
    ap = argparse.ArgumentParser(prog="seatcrew", description="Multi-AI seat workflows: every job gets a seat, every item walks a check chain.")
    ap.add_argument("--env", default=".env"); ap.add_argument("--lang", choices=list(LANGUAGES))
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list", help="list bundled example workflows")
    sp.add_parser("app", help="open the desktop app (launcher window)", add_help=False)
    sp.add_parser("video", help="short-video tools: init / assemble / qc (see: seatcrew video -h)", add_help=False)
    n = sp.add_parser("new", help="scaffold a new workflow folder"); n.add_argument("name"); n.add_argument("--python", action="store_true", help="Python instead of YAML"); n.add_argument("--dir", default="workflows")
    for c in ("run", "ui"):
        x = sp.add_parser(c, help="run cycles headless" if c == "run" else "start the dashboard + Runner")
        x.add_argument("workflow"); x.add_argument("--config"); x.add_argument("--state")
        if c == "run": x.add_argument("--yes", action="store_true", help="approve every human gate"); x.add_argument("--cycles", type=int, default=1); x.add_argument("--json", action="store_true")
        else: x.add_argument("--host", default="127.0.0.1"); x.add_argument("--port", type=int, default=8800); x.add_argument("--open", action="store_true")
    ta = sp.add_parser("test-ai", help="real minimal call to a provider"); ta.add_argument("provider", nargs="?"); ta.add_argument("--model")
    argv = sys.argv[1:] if argv is None else argv
    glob, rest = split_global(argv)
    if rest[:1] == ["video"]:
        load_env(glob.get("env", ".env")); from .video.cli import main as vid
        sub = rest[1:]
        if glob.get("lang") and len(sub) >= 1 and "--lang" not in sub and not any(x.startswith("--lang=") for x in sub) and sub[0] in VIDEO_LANG_CMDS:
            sub = [*sub, "--lang", glob["lang"]]          # global --lang flows into the video subcommand (init -> Chinese placeholders)
        return vid(sub)
    if rest[:1] == ["app"]:
        argv = rest
        from .desktop import main as desk; return desk(argv[1:])
    a = ap.parse_args(rest)
    for k, v in glob.items(): setattr(a, k, v)
    load_env(a.env)

    if a.cmd == "list":
        for e in loader.list_examples(): print(e)
        return 0
    if a.cmd == "new":
        if not re.fullmatch(r"[a-z][a-z0-9_]*", a.name): print("name must be lowercase letters, digits, _"); return 2
        d = Path(a.dir) / a.name; f = d / ("workflow.py" if a.python else "workflow.yaml")
        if f.exists(): print(t("cli_exists", _lang(a), path=f)); return 1
        d.mkdir(parents=True, exist_ok=True)
        tpl = (Path(__file__).parent / "templates" / f.name).read_text(encoding="utf-8")
        f.write_text(tpl.format(name=a.name, title=a.name.replace("_", " ").title(), path=d, cls="".join(w.title() for w in a.name.split("_")) + "Workflow"), encoding="utf-8")
        print(t("cli_created", _lang(a), path=f, cmd=f"seatcrew ui {d}")); return 0
    if a.cmd == "test-ai":
        from .llm import PROVIDERS, key_status, test_connection
        from .config import base_defaults
        cfg = base_defaults([]); names = [a.provider] if a.provider else [n for n, ok in key_status().items() if ok and PROVIDERS[n]["key_env"]]
        if not names: print(t("cli_nokeys", _lang(a))); return 1
        bad = 0
        for nme in names:
            r = test_connection(nme, cfg, a.model); bad += not r["ok"]
            print(f"{'OK ' if r['ok'] else 'ERR'} {nme:<10} {r.get('model')}  {r['latency_ms']}ms  {r.get('reply') or r.get('error')}")
        return 1 if bad else 0

    wf = loader.build(a.workflow, a.config, a.state); L = _lang(a, wf)
    if a.cmd == "run":
        for _ in range(a.cycles):
            wf.run_cycle()
            if a.yes:
                for it in [i for i in wf.items if "pending" in i]: wf.decide(it["id"], True, "--yes")
        items = [wf.item_view(i) for i in wf.items]
        if a.json: print(json.dumps(items, indent=1, ensure_ascii=False, default=str)); return 0
        for it in items:
            print(f"#{it['id']} {it.get('title', '')}  ->  {it.get('status')}")
            for c in it.get("chain", []): print(f"    {'OK ' if c['ok'] else 'BLK'} {c['seat'].upper():<10} {c['reason']}")
        print(t("cli_summary", L, ok=sum(i.get("status") in ("done", "filled") for i in items), blocked=sum(str(i.get("status", "")).startswith("blocked") for i in items),
                waiting=sum("pending" in i for i in items))); return 0
    if a.lang: wf.cfg.data["language"] = a.lang          # --lang also sets the dashboard / CHIEF chat language for this session
    from .core import Runner
    from .server import serve
    url = f"http://{a.host}:{a.port}"
    try: srv = serve(wf, a.host, a.port)
    except OSError as e: print(t("cli_bind", L, addr=f"{a.host}:{a.port}", err=e.strerror)); return 1
    Runner(wf).start(); print(t("cli_dashboard", L, url=url, name=wf.title))
    if a.open: webbrowser.open(url)
    try: srv.serve_forever()
    except KeyboardInterrupt: wf.stop.set()
    return 0

if __name__ == "__main__": sys.exit(main())

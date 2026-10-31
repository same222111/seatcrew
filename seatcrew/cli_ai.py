"""Use your own AI subscription through the vendors' official command-line tools - no API key needed.

  codex   OpenAI Codex CLI   - `codex login` ("Sign in with ChatGPT"), seats call `codex exec`
  claude  Claude Code        - `claude auth login` (Claude.ai account),  seats call `claude -p`

SeatCrew only starts these official programs. It never opens, copies, parses or stores their login files or tokens:
login state comes from `codex login status` / `claude auth status` (exit code only), and every call is a fresh
subprocess with a read-only sandbox and no tools. Usage counts against your own plan's limits."""
import os, re, shutil, subprocess, tempfile, threading, time, uuid

TOOLS = {
    "codex": dict(label="ChatGPT / Codex", bin="codex", install="npm install -g @openai/codex", install_alt="brew install --cask codex",
                  docs="https://developers.openai.com/codex/cli", login=["login"], device=["login", "--device-auth"], status=["login", "status"]),
    "claude": dict(label="Claude (Claude Code)", bin="claude", install="npm install -g @anthropic-ai/claude-code",
                   install_alt="curl -fsSL https://claude.ai/install.sh | bash   (Windows: irm https://claude.ai/install.ps1 | iex)",
                   docs="https://code.claude.com/docs/en/authentication", login=["auth", "login"], device=None, status=["auth", "status"]),
}
PROVIDER = {"codex_cli": "codex", "claude_cli": "claude"}
URL_RE = re.compile(r"https://[^\s'\"<>]+")
CODE_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4,5})\b")
_cache, _jobs, _lock = {}, {}, threading.Lock()

class CLIError(RuntimeError): pass

def which(tool):
    """Path of the CLI: PATH, then SEATCREW_<TOOL>_BIN, then the usual npm/user install spots."""
    t = TOOLS[tool]; env = os.getenv(f"SEATCREW_{tool.upper()}_BIN")
    if env and os.path.isfile(env): return env
    p = shutil.which(t["bin"])
    if p: return p
    home = os.path.expanduser("~")
    for d in (os.path.join(home, ".local", "bin"), os.path.join(home, ".npm-global", "bin"), os.path.join(os.getenv("APPDATA", ""), "npm"),
              "/opt/homebrew/bin", "/usr/local/bin", os.path.join(home, ".claude", "local")):
        for name in (t["bin"], t["bin"] + ".cmd", t["bin"] + ".exe"):
            if d and os.path.isfile(os.path.join(d, name)): return os.path.join(d, name)
    return None

def _run(args, timeout=20, stdin=None, cwd=None):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, input=stdin, cwd=cwd,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

def status(tool, fresh=False):
    """dict(installed, version, logged_in, path). Cached 60 s. Login = exit code of the official status command only."""
    now = time.time()
    with _lock:
        c = _cache.get(tool)
        if c and not fresh and now - c[0] < 60: return dict(c[1])
    p = which(tool); out = dict(tool=tool, label=TOOLS[tool]["label"], installed=bool(p), version=None, logged_in=False,
                                install=TOOLS[tool]["install"], install_alt=TOOLS[tool]["install_alt"], docs=TOOLS[tool]["docs"])
    if p:
        try: out["version"] = (_run([p, "--version"], 15).stdout.strip().splitlines() or [""])[0][:60]
        except (OSError, subprocess.SubprocessError): pass
        try: out["logged_in"] = _run([p, *TOOLS[tool]["status"]], 20).returncode == 0
        except (OSError, subprocess.SubprocessError): pass
    with _lock: _cache[tool] = (now, out)
    return dict(out)

def all_status(fresh=False): return {t: status(t, fresh) for t in TOOLS}

def login(tool, device=False):
    """Start the official login in the background. Its own browser page / device code does the sign-in.
    We only relay the URL / one-time code it prints so you can open it; nothing it writes is read by SeatCrew."""
    p = which(tool)
    if not p: raise CLIError(f"{TOOLS[tool]['label']} is not installed - run: {TOOLS[tool]['install']}")
    args = TOOLS[tool]["device"] if device and TOOLS[tool]["device"] else TOOLS[tool]["login"]
    jid = uuid.uuid4().hex[:10]; job = dict(id=jid, tool=tool, lines=[], url=None, code=None, done=False, ok=None, started=time.time())
    proc = subprocess.Popen([p, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    def pump():
        for line in proc.stdout:
            line = _clean(line.rstrip())
            if not line: continue
            job["lines"] = (job["lines"] + [line])[-12:]
            u = URL_RE.search(line); c = CODE_RE.search(line)
            if u and not job["url"]: job["url"] = u.group(0)
            if c and not job["code"]: job["code"] = c.group(1)
        proc.wait(); job["done"] = True; job["ok"] = proc.returncode == 0; status(tool, fresh=True)
    threading.Thread(target=pump, daemon=True).start()
    def reaper():
        time.sleep(900)
        if proc.poll() is None: proc.kill()
    threading.Thread(target=reaper, daemon=True).start()
    _procs[jid] = proc; _jobs[jid] = job; return {k: v for k, v in job.items()}

_procs = {}
def login_send(jid, code):
    """Paste-back step (Claude shows a code on its callback page). The code goes straight to the CLI's stdin, never stored."""
    pr = _procs.get(jid)
    if not pr or pr.poll() is not None: raise CLIError("login is not waiting for a code")
    pr.stdin.write(str(code).strip()[:400] + "\n"); pr.stdin.flush(); return login_job(jid)

def cancel(jid):
    pr = _procs.pop(jid, None)
    if pr and pr.poll() is None: pr.kill()

def login_job(jid):
    j = _jobs.get(jid)
    if not j: raise CLIError("unknown login job")
    return {k: v for k, v in j.items()}

def _clean(s):
    s = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)
    return re.sub(r"(sk-[A-Za-z0-9_\-]{8,}|eyJ[A-Za-z0-9_\-.]{20,})", "***", s)[:300]

def ask(tool, system, user, model=None, timeout=120):
    """One non-interactive answer from the CLI (no tools, read-only, throwaway folder). -> text."""
    p = which(tool)
    if not p: raise CLIError(f"{TOOLS[tool]['label']} is not installed ({TOOLS[tool]['install']})")
    prompt = f"{system}\n\n---\n\n{user}" if tool == "codex" else user
    with tempfile.TemporaryDirectory(prefix="seatcrew-ai-") as d:
        if tool == "codex":
            outf = os.path.join(d, "last.txt")
            args = [p, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral", "--color", "never", "-o", outf]
            if model: args += ["-m", model]
            args.append("-")
        else:
            args = [p, "-p", "--output-format", "text", "--tools", "", "--system-prompt", system]
            if model: args += ["--model", model]
        try: r = _run(args, timeout, stdin=prompt, cwd=d)
        except subprocess.TimeoutExpired: raise CLIError(f"{tool}: no answer within {timeout}s") from None
        except OSError as e: raise CLIError(f"{tool}: {e}") from None
        txt = ""
        if tool == "codex" and os.path.isfile(outf):
            with open(outf, encoding="utf-8", errors="replace") as f: txt = f.read()
        txt = (txt or r.stdout or "").strip()
        if r.returncode != 0:
            err = _clean((r.stderr or r.stdout or "").strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else f"exit {r.returncode}")
            if re.search(r"log ?in|auth|credential|401|not signed", err, re.I): err += f" - sign in first ({' '.join([TOOLS[tool]['bin'], *TOOLS[tool]['login']])})"
            raise CLIError(f"{tool}: {err}")
        if not txt: raise CLIError(f"{tool}: empty answer")
        return txt

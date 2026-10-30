"""Privacy / secrets scan of tracked files (run in CI): API keys, tokens, private keys, .env/state/config files,
absolute home paths, personal e-mail addresses, sample media and large binaries. Exit 1 on any finding."""
import re, subprocess, sys
from pathlib import Path

KEY = re.compile(r"(sk-(?:proj-)?[A-Za-z0-9_\-]{20,}|sk-ant-[A-Za-z0-9_\-]{20,}|r8_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{35}|xai-[A-Za-z0-9]{20,}"
                 r"|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
                 r"|eyJ[A-Za-z0-9_\-]{30,}\.[A-Za-z0-9_\-]{30,}\.[A-Za-z0-9_\-]{10,})")
HOME = re.compile(r"(/home/(?!user\b|runner\b|box\b|me\b)[a-z][\w.-]+/|/Users/(?!me\b|you\b)[A-Za-z][\w.-]+/|C:\\\\Users\\\\(?!you\b)[A-Za-z]\w+)")
MAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|example\.(?:com|org)|localhost)[A-Za-z0-9.-]+\.[a-z]{2,}\b")
BAD_NAMES = re.compile(r"(^|/)(\.env(\.(?!example$).*)?|.*\.pem|.*\.key|id_rsa.*|state\.json|.*\.sqlite3?|config\.local\.ya?ml)$")
MEDIA = (".mp4", ".mov", ".webm", ".mkv", ".wav", ".mp3", ".m4a", ".flac", ".otf", ".ttc")
ALLOW_MEDIA = re.compile(r"^(docs/|assets/|packaging/).*\.(png|jpg|gif|svg|ico|icns)$")
ALLOW_MAIL = {"noreply@anthropic.com"}
MAX_BYTES = 2_000_000
FAKE = re.compile(r"(test|abcdef|zzzz|xxxx|SECRET|REAL|FAKE|EXAMPLE|ABCDEFGHIJ|0000)", re.I)   # obvious fixture keys in tests
KNOWN = {"docs/demo.mp4", "docs/demo.gif"}   # the project's own UI demo (no personal data), reviewed in v0.6.0

def main():
    files = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout.decode().split("\0")
    bad = []
    for f in filter(None, files):
        p = Path(f)
        if not p.is_file(): continue
        if BAD_NAMES.search(f): bad.append(f"{f}: secret/state file must not be committed")
        if f in KNOWN: continue
        if p.suffix.lower() in MEDIA: bad.append(f"{f}: sample media / font must not be committed")
        size = p.stat().st_size
        if size > MAX_BYTES and not f.startswith("seatcrew/web/vendor/"): bad.append(f"{f}: {size // 1024} KB binary/large file")
        try: text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError): continue
        if f == "scripts/privacy_scan.py": continue
        for i, line in enumerate(text.splitlines(), 1):
            k = KEY.search(line)
            if k and not (f.startswith(("tests/", "examples/trading/tests/")) and FAKE.search(k.group(0))): bad.append(f"{f}:{i}: looks like a real key/token")
            if HOME.search(line): bad.append(f"{f}:{i}: absolute personal path")
            for m in MAIL.findall(line):
                if m not in ALLOW_MAIL and not f.startswith("seatcrew/web/vendor/"): bad.append(f"{f}:{i}: e-mail address {m}")
    for b in bad: print("PRIVACY:", b)
    print(f"privacy scan: {len([f for f in files if f])} tracked files, {len(bad)} finding(s)")
    return 1 if bad else 0

if __name__ == "__main__": sys.exit(main())

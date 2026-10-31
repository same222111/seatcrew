"""Smoke test for an INSTALLED SeatCrew (wheel / pip): start the desktop app headless, run the setup wizard in
demo mode, open every workflow and check its page + assets load. Exit 1 on any failure.
Usage: python scripts/smoke_app.py [path-to-seatcrew-desktop executable]   (default: python -m seatcrew.desktop)"""
import json, os, subprocess, sys, tempfile, time, urllib.request

def req(url, body=None):
    r = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as f: return f.status, f.read()

def main():
    home = tempfile.mkdtemp(prefix="seatcrew-smoke-"); log = os.path.join(home, "app.log")
    cmd = ([os.path.abspath(sys.argv[1])] + sys.argv[2:] if sys.argv[1:] else [sys.executable, "-m", "seatcrew.desktop"]) + ["--no-window", "--home", os.path.join(home, "data")]
    uf = os.path.join(home, "url.txt"); env = dict(os.environ, SEATCREW_URL_FILE=uf)
    p = subprocess.Popen(cmd, stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT, cwd=home, env=env)
    try:
        url = None
        for _ in range(240):
            time.sleep(0.5)
            if os.path.exists(uf) and open(uf).read().strip(): url = open(uf).read().strip(); break
            if p.poll() is not None: break
        if not url: print(open(log, encoding="utf-8", errors="replace").read()); sys.exit("app did not start")
        assert req(url)[0] == 200
        assert json.loads(req(url + "api/setup", {"language": "en", "mode": "demo"})[1])["ok"]
        for wf in ("short_video", "content_review", "support_triage", "trading"):
            u = json.loads(req(url + "api/open", {"workflow": wf})[1])["url"].split("/?")[0]
            for path in ("/", "/neon.css", "/api/state"): assert req(u + path)[0] == 200, (wf, path)
            if wf == "short_video": assert req(u + "/characters")[0] == 200 and req(u + "/api/characters")[0] == 200
            print("ok", wf, u)
        shots = os.environ.get("SMOKE_SHOTS")             # optional: screenshots of the real UI on this OS (CI artifact)
        if shots:
            from playwright.sync_api import sync_playwright
            os.makedirs(shots, exist_ok=True); req(url + "api/setup", {"language": "zh-CN", "mode": "demo"})
            sv = json.loads(req(url + "api/open", {"workflow": "short_video"})[1])["url"].split("/?")[0]
            with sync_playwright() as pw:
                b = pw.chromium.launch(); pg = b.new_page(viewport=dict(width=1440, height=900))
                for name, u in (("launcher", url), ("short_video", sv + "/"), ("characters", sv + "/characters")):
                    pg.goto(u); pg.wait_for_timeout(1500); pg.screenshot(path=os.path.join(shots, f"{sys.platform}_{name}.png")); print("shot", name)
                b.close()
        print("SMOKE OK")
    finally:
        p.terminate()
        try: p.wait(10)
        except subprocess.TimeoutExpired: p.kill()

if __name__ == "__main__": main()

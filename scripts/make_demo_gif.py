"""Record docs/demo.gif (~30 s): seat grid lighting up, items walking the check chain, one getting blocked.
Needs: pip install playwright pillow && playwright install chromium (or CHROME=/path/to/chrome), ffmpeg on PATH.
    python scripts/make_demo_gif.py [out.gif]
    python scripts/make_demo_gif.py --frames /path/to/captured/pngs [out.gif]"""
import os, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path[:0] = [str(ROOT), str(ROOT / "examples" / "trading")]
# A connected browser can supply real UI captures without a second browser driver.
if len(sys.argv) > 2 and sys.argv[1] == "--frames":
    from PIL import Image
    paths = sorted(Path(sys.argv[2]).glob("*.png"))
    if not paths: raise SystemExit("No PNG frames found")
    frames = [Image.open(p).convert("RGB") for p in paths]
    if len({im.size for im in frames}) != 1: raise SystemExit("Frames must have matching dimensions")
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "docs" / "demo.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=1800, loop=0)
    print(f"{out}: {len(frames)} captured frames")
    raise SystemExit(0)

from playwright.sync_api import sync_playwright
from seatcrew import loader
from seatcrew.server import serve

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "demo.gif"
FPS, SECONDS, STEP = 4, 30, 0.45            # STEP = artificial think time per seat so the grid visibly lights up

tmp = Path(tempfile.mkdtemp()); os.chdir(tmp)
wf = loader.build("content_review", str(tmp / "c.yaml"), str(tmp / "state"))
for s in wf.seat_map.values():                # slow every seat down a little, for the camera only
    orig = s.check
    def slow(item, _o=orig):
        time.sleep(STEP); return _o(item)
    s.check = slow
srv = serve(wf, "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_port}/"
frames = tmp / "f"; frames.mkdir()

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1280, "height": 1060}); pg.goto(url); pg.wait_for_selector(".seat")
    pg.evaluate("setInterval(tick, 250)")
    n = [0]; t0 = time.time()
    def shoot(until):
        while time.time() - t0 < until:
            pg.screenshot(path=str(frames / f"{n[0]:04d}.png")); n[0] += 1
            time.sleep(max(0, t0 + n[0] / FPS - time.time()))
    shoot(2.5)
    threading.Thread(target=wf.run_cycle, daemon=True).start()            # samples: one passes, two blocked, one waits
    shoot(15)
    pg.fill("[data-f=topic]", "Why our product is the best"); pg.fill("[data-f=notes]", "It is guaranteed to double your revenue in 30 days, risk-free.")
    pg.fill("[data-f=sources]", "")
    shoot(17.5); pg.click("#submitBtn"); threading.Thread(target=wf.run_cycle, daemon=True).start()
    shoot(24)
    pg.locator(".it:has-text('Team offsite') [data-ap]").click(); pg.evaluate("scrollTo(0, 0)")  # human approves -> publish -> review light up
    shoot(SECONDS)
    b.close()
srv.shutdown()
pal = tmp / "pal.png"
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(frames / "%04d.png"), "-vf", "scale=960:-1:flags=lanczos,palettegen=max_colors=96", str(pal)], check=True)
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(frames / "%04d.png"), "-i", str(pal),
                "-lavfi", "scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4", str(OUT)], check=True)
print(f"{OUT}  {n[0]} frames  {OUT.stat().st_size // 1024} KB"); shutil.rmtree(tmp, ignore_errors=True)

"""v0.9.4 UI: two-column video studio, approve bar under the video, tabs, Chinese UI, 390 px header, chat language refresh."""
import json, os, re, shutil, subprocess, sys, time, urllib.request, asyncio
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
CHROME = shutil.which("google-chrome") or "/usr/bin/google-chrome"
pw = pytest.importorskip("playwright.async_api")
pytestmark = pytest.mark.skipif(not os.path.exists(CHROME), reason="needs chrome")
# Text that may stay Latin in the Chinese UI: product names, codecs, data values, logs.
ALLOW = re.compile(r"^(SeatCrew|short_video|AI|CHIEF|edge|draft|ffmpeg|DRAFT PREVIEW.*|PASS.*|FAIL.*|[A-Za-z0-9_.:/\-+×%() \[\]|·,<>=~]*\d[A-Za-z0-9_.:/\-+×%() \[\]|·,<>=~]*|zh-CN.*|exact|none|ok|v\d.*)$")

def api(base, p, d=None):
    r = urllib.request.Request(base + p, data=json.dumps(d).encode() if d is not None else None, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())

@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ui"); cfg = tmp / "config.yaml"
    cfg.write_text("language: zh-CN\nauto_run: true\nrun_interval_sec: 1\n", encoding="utf-8")
    import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = dict(os.environ, PYTHONPATH=f"{ROOT}{os.pathsep}{ROOT/'examples'/'trading'}", HOME=str(tmp))
    p = subprocess.Popen([sys.executable, "-m", "seatcrew", "ui", str(ROOT / "examples/short_video/workflow.py"), "--config", str(cfg), "--state", str(tmp / "st"), "--port", str(port)],
                         cwd=tmp, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try: api(base, "/api/state"); break
        except Exception: time.sleep(0.25)
    api(base, "/api/submit", dict(data=dict(topic="天空为什么是蓝色的？", notes="阳光看起来是白色的，其实混合了所有颜色。\n空气分子更容易散射波长短的蓝光，红光则很少被散射。\n所以无论你看向天空哪里，都有蓝光进入眼睛。\n傍晚时阳光要穿过更厚的空气，蓝光在路上就被散射掉了。\n这就是为什么晚霞是橙红色的。", template="knowledge_explainer", aspect="9:16")))
    api(base, "/api/run", {}); t0 = time.time()
    while time.time() - t0 < 120 and not any(i.get("pending") is not None for i in api(base, "/api/state")["items"]): time.sleep(1)
    st = api(base, "/api/state")["items"]
    assert any(i.get("pending") is not None for i in st), [(i.get("status"), (i.get("data") or {}).get("tip")) for i in st]
    yield base
    p.terminate(); p.wait(10)

def page_run(base, fn, w=1280, h=800):
    async def go():
        async with pw.async_playwright() as p:
            b = await p.chromium.launch(executable_path=CHROME)
            try:
                pg = await b.new_page(viewport=dict(width=w, height=h)); await pg.goto(base + "/"); await pg.wait_for_selector("#apbar", timeout=20000)
                return await fn(pg)
            finally: await b.close()
    return asyncio.run(go())

def test_two_columns_and_approve_under_video_in_first_view(server):
    async def f(pg):
        return await pg.evaluate("""()=>{const r=e=>document.querySelector(e).getBoundingClientRect();const v=r('#studio video'),a=r('#apbar'),f=r('.vleft');
          const vis=s=>{const e=document.querySelector(s);return !!e&&e.offsetParent!==null};
          return {vb:v.bottom,at:a.top,ab:a.bottom,fl:f.right,vl:v.left,seats:vis('#seats'),items:vis('#items'),who:vis('#whoCard'),tiles:vis('.tiles')}}""")
    m = page_run(server, f)
    assert m["at"] >= m["vb"] - 1 and m["ab"] <= 800, m           # bar right under the video, inside the first screen
    assert m["fl"] <= m["vl"], m                                    # form column left of the player
    assert not (m["seats"] or m["items"] or m["who"] or m["tiles"]), m   # duplicated seat lists / pass-rate tiles gone

def test_models_and_voices_are_tabs(server):
    async def f(pg):
        await pg.click("nav button[data-t=tvoices]"); a = await pg.is_visible("#voices"); b = await pg.is_visible("#models")
        await pg.click("nav button[data-t=tmodels]"); c = await pg.is_visible("#models"); d = await pg.is_visible("#studio")
        return a, b, c, d, await pg.inner_text("nav")
    a, b, c, d, nav = page_run(server, f)
    assert a and not b and c and not d and "模型" in nav and "配音库" in nav

def test_only_ai_seats_offer_a_model(server):
    async def f(pg):
        await pg.click("nav button[data-t=team]")
        return await pg.evaluate("[[...document.querySelectorAll('[data-sp]')].map(e=>e.dataset.sp),[...document.querySelectorAll('[data-noai]')].map(e=>e.dataset.noai)]")
    ai, noai = page_run(server, f)
    assert set(ai) == {"chief", "writer", "scriptcheck"} and set(noai) == {"production", "editqc", "approve"}

def test_chinese_dashboard_has_no_english_chrome(server):
    async def f(pg):
        return await pg.evaluate("""()=>{const out=[];const skip=e=>e.closest('.term,#log,table,.qc,.sum,.adv,video,#ccM,#ccG,.vst+.steps~.dim,.bk,[data-v],option,.tip,.mono');
          const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode()){const e=n.parentElement;const t=n.textContent.trim();
          if(!t||!/[A-Za-z]{3,}/.test(t)||/[\\u4e00-\\u9fff]/.test(t)||!e||e.offsetParent===null||skip(e)||e.closest('script,style'))continue;out.push(t)}return out}""")
    leak = [t for t in page_run(server, f) if not ALLOW.match(t)]
    assert not leak, leak

def test_header_two_rows_at_390(server):
    async def f(pg): return await pg.evaluate("[document.querySelector('header').offsetHeight,document.documentElement.scrollWidth]")
    h, sw = page_run(server, f, 390, 844)
    assert h <= 96 and sw <= 392, (h, sw)                            # was 174 px tall / 444 px wide

def test_chat_relabels_on_language_change(server):
    async def f(pg):
        await pg.click("#ccBtn"); await pg.wait_for_timeout(500); zh = await pg.inner_text("#ccP .hd b")
        await pg.select_option("#langSel", "en"); await pg.wait_for_timeout(1200)
        en = await pg.inner_text("#ccP .hd b"); btn = await pg.inner_text("#ccF button"); tab = await pg.inner_text("nav button[data-t=tvoices]")
        await pg.select_option("#langSel", "zh-CN"); await pg.wait_for_timeout(800)
        return zh, en, btn, tab
    zh, en, btn, tab = page_run(server, f)
    assert "总指挥" in zh and "CHIEF chat" in en and btn == "Send" and tab == "Voices"

def test_storyboard_cells_do_not_wrap_per_character(server):
    async def f(pg):
        return await pg.evaluate("Math.min(...[...document.querySelectorAll('#studio .sbt td.n')].map(e=>e.getBoundingClientRect().width))")
    assert page_run(server, f) >= 150

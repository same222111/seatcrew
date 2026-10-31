"""CHIEF chat - the built-in helper ("总指挥对话"). Reachable from the launcher and every dashboard.

Safety model
  * Uses whichever provider the user configured (any of the 7, incl. local Ollama). With none it runs an offline FAQ.
  * The AI may only PROPOSE actions through a small tool list. Read-only tools (who_decides, troubleshoot, explain)
    answer at once; changing tools (create_workflow, set_config, run_sample) become a pending proposal with a
    preview/diff and run ONLY after the user clicks Confirm (POST /api/chat/confirm). Nothing is auto-applied.
  * API keys never reach the AI, the history file or a reply: the context holds key *booleans* only, and every
    message is scrubbed of key-shaped strings before it is stored or sent. Keys are entered in the wizard/settings.
  * Trading stays paper-only: broker/live settings are refused here, and the trading config validator rejects them too.
History lives in a local JSON file (chat.json) and can be cleared."""
import copy, json, os, re, threading, time, uuid
from pathlib import Path
import yaml
from . import llm
from .config import LLM_LIMITS, merge
from .profiles import SECRET_KEY_RE, SECRET_VAL_RE

KEY_LINKS = {"openai": "https://platform.openai.com/api-keys", "anthropic": "https://console.anthropic.com/settings/keys",
             "gemini": "https://aistudio.google.com/apikey", "xai": "https://console.x.ai", "deepseek": "https://platform.deepseek.com/api_keys",
             "custom": "https://openrouter.ai/keys", "ollama": "https://ollama.com/download"}
ACTION_TOOLS = ("create_workflow", "set_config", "run_sample", "set_voice", "create_character", "create_cast")
READ_TOOLS = ("who_decides", "troubleshoot", "explain")
RULE_OPS = {"require", "max_len", "min_len", "block_if_match", "require_match", "classify", "template", "set"}
SLUG = re.compile(r"[a-z][a-z0-9_]{1,39}")
BLOCKED_PATCH = re.compile(r"(broker|live|real_money|base_url|providers|llm_limits|setup_complete)", re.I)
LOCK = threading.Lock()

def scrub(text):
    """Remove anything that looks like a key. Returns (clean_text, removed?)."""
    t = str(text or ""); before = t
    t = SECRET_VAL_RE.sub("***", t); t = llm._scrub(t)
    t = re.sub(r"\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET))\s*=\s*\S+", r"\1=***", t)
    return t, t != before

# ---------------------------------------------------------------- canned texts (offline FAQ + tool wording) --
TXT = {
 "en": dict(
  hi="Hi, I'm CHIEF. Ask me how SeatCrew works, who decides what, or say \"create a workflow that ...\".",
  offline="No AI is connected, so I'm answering from the built-in FAQ. Connect one (even free local Ollama) for full chat.",
  key_removed="I removed something that looked like an API key from your message. Paste keys only in the setup wizard or the AI Seats tab - never in chat.",
  confirm_needed="Nothing is changed yet - review the preview and press Confirm.", done="Done.", cancelled="Cancelled - nothing was changed.",
  no_wf="Open a workflow first (from Home) to change its settings or run it.", no_seats="(open a workflow to see its seats)", fallback="I didn't find that in the offline FAQ. Try: what is a seat? who decides? how do I connect an AI? create a workflow ...",
  who="Who decides?\n1. CHIEF (commander) starts each cycle and assigns work - it never approves anything by itself.\n2. Each seat judges one thing with its rules, then optionally its AI. An AI can only make a seat MORE cautious.\n3. Checks gate: one BLOCKED check stops the item (single point of failure = intercepted).\n4. A human seat (if any) approves or rejects.\nCurrent assignment:",
  trouble="Troubleshooting:", t_ok="looks fine", t_nokey="seat '{s}' uses {p} but {env} is not set - add it in the wizard or the AI Seats tab, or switch the seat to rules / ollama.",
  t_none="No AI provider has a key. Everything still runs on rules. To chat with an AI: run the wizard, or install free Ollama.", t_ollama="Ollama/custom need a local server running (e.g. `ollama serve`, then `ollama pull llama3.2`).",
  faq=[("seat|席位|what is a seat", "A seat is one job (e.g. RISK, POLICY). It checks every item with plain rules and, if you assign one, an AI."),
       ("chain|check|链|gate", "Every item walks the check chain seat by seat. OK -> next seat, BLOCKED -> stops with a reason and a stamp, WAITING -> parks for a human."),
       ("ai|key|connect|provider|model", "Any of 7 providers works: OpenAI, Anthropic, Gemini, xAI, DeepSeek, any OpenAI-compatible endpoint, or free local Ollama. Keys stay in .env on this computer."),
       ("ollama|free|local|offline", "Free option: install Ollama (ollama.com/download), run `ollama pull llama3.2`, then pick 'ollama' in the wizard or AI Seats tab. No key needed."),
       ("trad|money|broker|paper|stock", "TradeCrew is paper trading only: simulated fills, no broker, no real money. Not financial advice."),
       ("create|new workflow|build|make", "Say \"create a workflow that ...\" and I'll draft the seats and checks as YAML, show a preview, and save it only after you confirm."),
       ("simple|advanced|hide", "Simple mode (on by default) hides advanced parameters like prompts, models and limits. Turn it off with the 'Simple' button."),
       ("what|seatcrew|help|how", "SeatCrew runs a small team of 'seats'. Each item walks a check chain; one failed check stops it. Rules work without AI; AI can be added per seat.")]),
 "zh-CN": dict(
  hi="你好,我是总指挥 CHIEF。可以问我 SeatCrew 怎么用、谁来做决定,或者说「创建一个工作流,用来……」。",
  offline="当前没有连接 AI,我先用内置的离线问答回答你。连接一个 AI(本地免费的 Ollama 也行)即可完整对话。",
  key_removed="你的消息里有像 API 密钥的内容,我已经删掉了。密钥只在设置向导或「AI 席位」页填写,不要发在聊天里。",
  confirm_needed="还没有做任何修改 - 请看预览,然后点「确认」。", done="已完成。", cancelled="已取消 - 没有修改任何东西。",
  no_wf="请先从首页打开一个工作流,才能修改它的设置或运行。", no_seats="(打开一个工作流即可看到它的席位)", fallback="离线问答里没找到。试试:什么是席位?谁来做决定?怎么连接 AI?创建一个工作流……",
  who="谁来做决定?\n1. 总指挥 CHIEF 启动每一轮并分派任务 - 它自己不批准任何事。\n2. 每个席位用规则判断一件事,可选再问它的 AI。AI 只能让席位更谨慎。\n3. 检查把关:任何一个检查 BLOCKED,事项就停下(单点失败即拦截)。\n4. 人工席位(如有)最后批准或驳回。\n当前分工:",
  trouble="故障排查:", t_ok="正常", t_nokey="席位 '{s}' 用的是 {p},但没有设置 {env} - 在向导或「AI 席位」页填写,或把席位改成 rules / ollama。",
  t_none="还没有任何 AI 密钥。一切仍可只靠规则运行。想和 AI 对话:重新运行向导,或安装免费的 Ollama。", t_ollama="Ollama/custom 需要本地服务在运行(如 `ollama serve`,再 `ollama pull llama3.2`)。",
  faq=[("席位|岗位|seat", "席位就是一个岗位(如 RISK 风控、POLICY 合规)。它用简单规则检查每个事项,你也可以给它分配一个 AI。"),
       ("链|检查|chain|拦截", "每个事项按顺序走过检查链。通过 -> 下一个席位;BLOCKED -> 停下并盖章说明原因;WAITING -> 等人工处理。"),
       ("ai|密钥|key|连接|模型|服务商", "支持 7 种:OpenAI、Anthropic、Gemini、xAI、DeepSeek、任意 OpenAI 兼容接口,以及本地免费的 Ollama。密钥只存在本机 .env。"),
       ("ollama|免费|本地|离线", "免费方案:安装 Ollama(ollama.com/download),运行 `ollama pull llama3.2`,然后在向导或「AI 席位」页选 ollama,无需密钥。"),
       ("交易|炒股|钱|券商|模拟|股票", "TradeCrew 只做模拟盘:模拟成交、不连券商、不用真钱,不构成投资建议。"),
       ("创建|新建|工作流|做一个", "说「创建一个工作流,用来……」,我会生成席位和检查的 YAML,先给你预览,你确认后才保存。"),
       ("简单|高级|隐藏", "简单模式(默认开启)会隐藏提示词、模型、限额等高级参数。点「简单」按钮可关闭。"),
       ("什么|怎么|帮助|介绍|seatcrew", "SeatCrew 让一个小团队的「席位」协作:每个事项走检查链,任何一个检查不通过就拦下。不接 AI 也能靠规则运行。")]),
}
TXT["zh-TW"] = dict(TXT["zh-CN"], hi="你好,我是總指揮 CHIEF。可以問我 SeatCrew 怎麼用、誰來做決定,或說「建立一個流程,用來……」。",
  offline="目前沒有連接 AI,先用內建離線問答回答。連接一個 AI(本機免費的 Ollama 也可以)即可完整對話。",
  confirm_needed="尚未做任何修改 - 請看預覽後按「確認」。", done="完成。", cancelled="已取消 - 沒有任何修改。",
  key_removed="你的訊息裡有像 API 金鑰的內容,已刪除。金鑰只在設定精靈或「AI 席位」頁填寫。",
  no_wf="請先從首頁開啟一個流程,才能修改設定或執行。", no_seats="(開啟一個流程即可看到它的席位)", who="誰來做決定?\n1. 總指揮 CHIEF 啟動每一輪並分派任務 - 它自己不核准任何事。\n2. 每個席位用規則判斷一件事,可選再問它的 AI。AI 只能讓席位更謹慎。\n3. 檢查把關:任何一個檢查 BLOCKED,項目就停下。\n4. 人工席位(如有)最後核准或駁回。\n目前分工:",
  fallback="離線問答裡沒找到。試試:什麼是席位?誰來做決定?怎麼連接 AI?建立一個流程……", trouble="故障排除:", t_ok="正常")
TXT["ja"] = dict(TXT["en"], hi="こんにちは、CHIEF です。SeatCrew の使い方、誰が何を決めるか、または「…するワークフローを作って」と話しかけてください。",
  offline="AI が未接続のため、内蔵のオフライン FAQ で回答します。AI(無料のローカル Ollama でも可)を接続すると会話できます。",
  confirm_needed="まだ何も変更していません - プレビューを確認して「確認」を押してください。", done="完了しました。", cancelled="キャンセルしました - 変更はありません。",
  key_removed="API キーのような文字列を削除しました。キーはセットアップか AI シート画面でのみ入力してください。",
  no_wf="設定変更や実行の前に、ホームからワークフローを開いてください。", no_seats="(ワークフローを開くとシートが表示されます)", fallback="オフライン FAQ に見つかりませんでした。例: シートとは? 誰が決める? AI の接続方法は? ワークフローを作って…", trouble="トラブルシュート:", t_ok="問題なし",
  who="誰が決める?\n1. CHIEF(指揮官)が各サイクルを開始し仕事を割り当てる - 自分では承認しない。\n2. 各シートがルールで判断し、任意で AI に聞く。AI は慎重にする方向にしか働かない。\n3. チェックが関門: 1 つでも BLOCKED なら止まる。\n4. 人間のシート(あれば)が承認/却下。\n現在の割り当て:")
TXT["es"] = dict(TXT["en"], hi="Hola, soy CHIEF. Pregúntame cómo funciona SeatCrew, quién decide qué, o di \"crea un flujo que ...\".",
  offline="No hay IA conectada; respondo con las preguntas frecuentes integradas. Conecta una (incluso Ollama local gratis) para chatear.",
  confirm_needed="Aún no se cambió nada - revisa la vista previa y pulsa Confirmar.", done="Hecho.", cancelled="Cancelado - no se cambió nada.",
  key_removed="Quité algo que parecía una clave API. Pega las claves solo en el asistente inicial o en la pestaña de puestos IA.",
  no_wf="Abre primero un flujo (desde Inicio) para cambiar su configuración o ejecutarlo.", no_seats="(abre un flujo para ver sus puestos)", fallback="No lo encontré en las FAQ sin conexión. Prueba: ¿qué es un puesto? ¿quién decide? ¿cómo conecto una IA? crea un flujo…", trouble="Diagnóstico:", t_ok="todo bien",
  who="¿Quién decide?\n1. CHIEF (comandante) inicia cada ciclo y reparte el trabajo - nunca aprueba nada solo.\n2. Cada puesto juzga con sus reglas y, opcionalmente, su IA. La IA solo puede volverlo MÁS prudente.\n3. Los controles filtran: un BLOCKED detiene el elemento.\n4. Un puesto humano (si existe) aprueba o rechaza.\nAsignación actual:")

def sample_for(wf, lang):
    """One sample item for this workflow, in the UI language when the workflow ships one ("lang" key), else the first."""
    samples = (getattr(wf, "spec", {}) or {}).get("sample_items") or type(wf).__init__.__globals__.get("SAMPLES") or []
    if not samples: return None
    s = next((x for x in samples if x.get("lang") == lang), None) or next((x for x in samples if (x.get("lang") or "")[:2] == (lang or "")[:2]), None) \
        or next((x for x in samples if x.get("lang") in (None, "en")), samples[0])
    return {k: v for k, v in s.items() if k != "lang"}

def tx(lang, k): return TXT.get(lang, TXT["en"]).get(k) or TXT["en"][k]

# ------------------------------------------------------------------------------------------- workflow specs --
def validate_spec(text, taken=()):
    """Plain-language -> YAML from the AI is untrusted: parse safely and check the structure. Returns (spec, yaml_text)."""
    t, removed = scrub(text)
    if removed: raise ValueError("workflow text contained something that looks like a key")
    try: spec = yaml.safe_load(t)
    except yaml.YAMLError as e: raise ValueError(f"not valid YAML: {str(e)[:120]}")
    if not isinstance(spec, dict): raise ValueError("workflow must be a YAML mapping")
    name = str(spec.get("name", ""))
    if not SLUG.fullmatch(name): raise ValueError("name: lowercase letters, digits, _ (2-40 chars)")
    if name in taken: raise ValueError(f"a workflow named '{name}' already exists")
    seats = spec.get("seats")
    if not isinstance(seats, list) or not seats: raise ValueError("seats: need a non-empty list")
    names = []
    for s in seats:
        if not isinstance(s, dict) or not SLUG.fullmatch(str(s.get("name", ""))): raise ValueError("every seat needs a lowercase name")
        for r in s.get("rules") or []:
            if not isinstance(r, dict) or len(r) != 1 or next(iter(r)) not in RULE_OPS: raise ValueError(f"seat {s['name']}: unknown rule {r}")
        names.append(s["name"])
    chain = spec.setdefault("chain", [n for n in names if n != "chief"])
    if not isinstance(chain, list) or any(c not in names for c in chain): raise ValueError("chain may only list seat names")
    for f in spec.get("submit") or []:
        if not isinstance(f, dict) or "name" not in f: raise ValueError("submit fields need a name")
    return spec, yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)

def starter_spec(description):
    """Offline (no-AI) draft: a safe 4-seat review flow named after the description. The user still confirms."""
    description = re.sub(r"^\s*(?:please\s+)?(?:create|make|build)\s+(?:me\s+)?(?:a|an)?\s*(?:new\s+)?workflow\s*(?:that|which|to|for)?\s*|^\s*(?:请)?(?:帮我)?(?:创建|新建|建立|做)一个?(?:工作流|流程)[,，:：]?\s*(?:用来|用於|用于|来|來)?", "", description, flags=re.I).strip() or description
    words = re.findall(r"[a-z]+", description.lower())
    if not words:   # CJK description -> readable English slug from keywords
        kw = [("review", r"审|審|校|レビュー|revis"), ("support", r"客服|工单|工單|サポート|soporte"), ("blog", r"博客|部落格|文章|ブログ"), ("video", r"视频|影片|動画|vídeo"), ("trade", r"交易|股票|トレード")]
        words = ([k for k, rx in kw if re.search(rx, description)] + ["flow"]) if any(re.search(rx, description) for _, rx in kw) else []
    stop = {"create", "a", "an", "the", "workflow", "that", "which", "for", "to", "new", "make", "build", "and", "of", "with", "me", "please"}
    name = "_".join([w for w in words if w not in stop][:3]) or "my_flow"
    name = (name if SLUG.fullmatch(name) else "my_flow")[:40]
    return dict(name=name, title=description.strip()[:80] or "My workflow", title_field="text", submit=[{"name": "text", "label": "Text", "type": "textarea"}],
                seats=[dict(name="intake", job="checks the input is there", rules=[{"require": ["text"]}, {"max_len": {"field": "text", "max": 4000}}]),
                       dict(name="safety", job="no secrets or card numbers", rules=[{"block_if_match": {"field": "text", "pattern": r"\b(?:\d[ -]?){13,16}\b", "reason": "card number"}}],
                            ai={"labels": ["ok", "flag"], "block": ["flag"], "prompt": "Text: {text}\nIs this safe to process (ok) or risky (flag)?"}),
                       dict(name="approve", job="human sign-off", human=True),
                       dict(name="review", job="final check", rules=[{"min_len": {"field": "text", "min": 3}}])],
                chain=["intake", "safety", "approve", "review"], sample_items=[{"text": "Example item for " + (description.strip()[:60] or "my workflow")}])

def flat(d, p=""):
    out = {}
    for k, v in (d or {}).items():
        q = f"{p}.{k}" if p else str(k)
        if isinstance(v, dict): out.update(flat(v, q))
        else: out[q] = v
    return out

def diff(old, new):
    a, b = flat(old), flat(new); return [dict(path=k, old=a.get(k), new=b[k]) for k in sorted(b) if a.get(k) != b[k]]

# ------------------------------------------------------------------------------------------------ assistant --
class Assistant:
    """ctx keys: lang() -> str; cfg() -> dict (providers/llm_limits/seats) or None; config (Config to edit) or None;
    wf (Workflow) or None; wf_dir (Path for new workflows); taken() -> names; prefer() -> preferred provider or None;
    demo() -> True for mock/demo mode; on_change(kind) optional."""
    def __init__(self, history_path, **ctx):
        self.path = Path(history_path); self.ctx = ctx; self.lock = threading.Lock()
        self.hist = self._load()

    def _load(self):
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError): return []
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True); tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.hist[-200:], ensure_ascii=False, indent=1), encoding="utf-8"); os.replace(tmp, self.path)
    def _add(self, role, text, **extra):
        m = dict(id=uuid.uuid4().hex[:10], role=role, text=scrub(text)[0], t=time.strftime("%Y-%m-%dT%H:%M:%S"), **extra)
        self.hist.append(m); return m

    lang = property(lambda self: (self.ctx.get("lang") or (lambda: "en"))())
    def cfg(self):
        c = (self.ctx.get("cfg") or (lambda: None))() or {}
        return dict(providers=c.get("providers", {}), llm_limits=dict(LLM_LIMITS, **c.get("llm_limits", {})), seats=c.get("seats", {}))

    def provider(self):
        """Configured provider for chat, or None (offline). Ollama/custom only when the user chose them."""
        if (self.ctx.get("demo") or (lambda: False))(): return None
        keys = llm.key_status(); chosen = (self.ctx.get("prefer") or (lambda: None))()
        cands = [chosen] + [s.get("provider") for s in self.cfg()["seats"].values()]
        for p in cands:
            if p in llm.PROVIDERS and (p in ("ollama", "custom") or keys.get(p)): return p
        return next((p for p in llm.PROVIDERS if p not in ("ollama", "custom") and keys.get(p)), None)  # cli = installed+signed in

    def status(self):
        p = self.provider()
        return dict(provider=p, model=llm.resolve(p, self.cfg())["model"] if p else None, offline=p is None, lang=self.lang,
                    demo=bool((self.ctx.get("demo") or (lambda: False))()), history=self.hist[-100:], links=KEY_LINKS,
                    keys=llm.key_status(), workflow=getattr(self.ctx.get("wf"), "name", None), hi=tx(self.lang, "hi"))

    def clear(self):
        with self.lock: self.hist = []; self._save()
        return dict(ok=True)

    # ---- read-only tools
    def who_decides(self):
        wf = self.ctx.get("wf"); seats = self.cfg()["seats"]; rows = []
        kinds = {s.name: s.kind for s in wf.seat_map.values()} if wf else {}
        order = ([s.name for s in wf.seat_map.values()] if wf else list(seats))
        for n in order:
            s = seats.get(n, {}); who = s.get("provider", "rules") + (f"/{s['model']}" if s.get("model") else "")
            rows.append(dict(seat=n, ai=who, kind="human" if kinds.get(n) == "human" else ("commander" if n == "chief" else kinds.get(n, "check"))))
        lines = [f"  {r['seat'].upper():<10} {r['kind']:<9} -> {r['ai'] if r['kind'] != 'human' else 'you'}" for r in rows]
        if wf: lines.append("  chain: " + " -> ".join(c.upper() for c in [x.name for x in wf.chain]))
        if not rows: lines.append("  " + tx(self.lang, "no_seats"))
        return tx(self.lang, "who") + "\n" + "\n".join(lines), dict(table=rows)

    def troubleshoot(self):
        keys = llm.key_status(); out = []
        for n, s in self.cfg()["seats"].items():
            p = s.get("provider", "rules")
            if p in llm.PROVIDERS and not keys.get(p): out.append(tx(self.lang, "t_nokey").format(s=n, p=p, env=llm.PROVIDERS[p]["key_env"]))
            if p in ("ollama", "custom"): out.append(tx(self.lang, "t_ollama"))
        if not any(v for k, v in keys.items() if k not in ("ollama", "custom")) and not self.provider(): out.append(tx(self.lang, "t_none"))
        wf = self.ctx.get("wf")
        if wf:
            errs = [e for e in wf.events[-60:] if e.get("kind") in ("AI-ERR", "ERROR")][-3:]
            out += [f"{e['agent']}: {e['msg'][:140]}" for e in errs]
        return tx(self.lang, "trouble") + "\n- " + ("\n- ".join(dict.fromkeys(out)) if out else tx(self.lang, "t_ok")), {}

    def faq(self, q):
        ql = q.lower()
        for pat, ans in tx(self.lang, "faq"):
            if re.search(pat, ql): return ans
        return tx(self.lang, "fallback")

    # ---- proposals (never applied without confirm)
    def propose(self, tool, args):
        wf = self.ctx.get("wf"); config = self.ctx.get("config")
        if tool == "create_workflow":
            taken = set((self.ctx.get("taken") or (lambda: []))())
            if args.get("yaml"): spec_text = args["yaml"]
            else:
                sp = starter_spec(args.get("description", "")); base, n = sp["name"], 2
                while sp["name"] in taken: sp["name"] = f"{base[:36]}_{n}"; n += 1
                spec_text = yaml.safe_dump(sp, sort_keys=False, allow_unicode=True)
            spec, text = validate_spec(spec_text, taken)
            return dict(tool=tool, args=dict(yaml=text, name=spec["name"]), preview=text, title=f"create workflow '{spec['name']}'")
        if tool == "set_config":
            if config is None: raise ValueError(tx(self.lang, "no_wf"))
            patch = args.get("patch")
            if not isinstance(patch, dict) or not patch: raise ValueError("set_config needs a non-empty patch object")
            bad = [k for k in flat(patch) if BLOCKED_PATCH.search(k) or SECRET_KEY_RE.search(k)]
            if bad: raise ValueError("not allowed from chat (paper-only / no keys): " + ", ".join(bad))
            if scrub(json.dumps(patch))[1]: raise ValueError("patch contains something that looks like a key")
            unknown = [k for k in patch if k not in config.defaults]
            if unknown: raise ValueError(f"unknown settings: {unknown}")
            new = merge(config.data, patch); config.validate(new)
            d = diff(config.data, new)
            if not d: raise ValueError("that is already the current value")
            return dict(tool=tool, args=dict(patch=patch), preview="\n".join(f"{x['path']}: {json.dumps(x['old'], ensure_ascii=False)} -> {json.dumps(x['new'], ensure_ascii=False)}" for x in d),
                        diff=d, title="change settings")
        if tool == "run_sample":
            if wf is None: raise ValueError(tx(self.lang, "no_wf"))
            data = args.get("data") if isinstance(args.get("data"), dict) else None
            if data is None: data = sample_for(wf, self.lang)
            if data is not None and scrub(json.dumps(data))[1]: raise ValueError("sample contains something that looks like a key")
            return dict(tool=tool, args=dict(data=data), preview=json.dumps(data, ensure_ascii=False, indent=1) if data else "run one cycle now", title=f"run {wf.name} on a sample item")
        if tool == "set_voice":
            if getattr(wf, "studio", None) != "video": raise ValueError("character voices exist only in the video studio")
            from .video import voices as VO
            name = str(args.get("name") or "").strip(); lib = VO.Library(); cur = lib.all().get(name)
            ch = {k: v for k, v in (args.get("changes") or {}).items() if k in VO.FIELDS}
            if args.get("adjust"):
                if args["adjust"] not in VO.ADJUST: raise ValueError(f"adjust must be one of {list(VO.ADJUST)}")
                if not cur: raise ValueError(f"no character '{name}' yet - add it first (Character voices panel)")
                for k, v in VO.adjusted(cur, args["adjust"]).items():
                    if v != cur.get(k): ch[k] = v
            if not ch: raise ValueError("nothing to change")
            if scrub(json.dumps(ch, ensure_ascii=False))[1]: raise ValueError("looks like a key")
            new = VO.clean_profile(name, dict({k: v for k, v in (cur or {}).items() if not ch.get("preset") or k in ("description", "color")}, **ch))
            d = [f"{k}: {json.dumps((cur or {}).get(k), ensure_ascii=False)} -> {json.dumps(new[k], ensure_ascii=False)}" for k in new if (cur or {}).get(k) != new[k] and k != "preset"]
            return dict(tool=tool, args=dict(name=name, changes=ch), preview=f"{name}\n" + "\n".join(d), title=f"voice for {name}")
        if tool in ("create_character", "create_cast"):
            if getattr(wf, "studio", None) != "video": raise ValueError("characters and casts exist only in the video studio")
            from .video import characters as CH
            if scrub(json.dumps(args, ensure_ascii=False))[1]: raise ValueError("looks like a key")
            st = CH.Store(); name = str(args.get("name") or "").strip(); CH.slug(name)
            if tool == "create_character":
                desc = str(args.get("description") or "").strip()[:800]
                if not desc: raise ValueError("describe the character (look, age, outfit) - or upload photos in Character Studio")
                if (st.path(name) / "character.yaml").is_file(): raise ValueError(f"character '{name}' already exists")
                return dict(tool=tool, args=dict(name=name, description=desc, personality=str(args.get("personality") or "")[:300]),
                            preview=f"{name}: {desc}", title=f"new character {name}")
            mem = [m if isinstance(m, dict) else dict(character=str(m)) for m in args.get("members") or []]
            if not mem or len(mem) > CH.MAX_CAST: raise ValueError(f"a cast needs 1-{CH.MAX_CAST} characters")
            have = {c["name"] for c in st.list()}; miss = [m["character"] for m in mem if m["character"] not in have]
            if miss: raise ValueError("create these characters first: " + ", ".join(miss))
            return dict(tool=tool, args=dict(name=name, members=mem, plot=str(args.get("plot") or "")[:1500]),
                        preview=f"{name}: " + ", ".join(f"{m['character']} ({m.get('role') or 'supporting'})" for m in mem), title=f"new cast {name}")
        raise ValueError(f"unknown tool {tool}")

    def execute(self, p):
        wf = self.ctx.get("wf"); config = self.ctx.get("config"); a = p["args"]
        if p["tool"] == "create_workflow":
            spec, text = validate_spec(a["yaml"], set((self.ctx.get("taken") or (lambda: []))()))
            d = Path(self.ctx.get("wf_dir") or "workflows") / spec["name"]; d.mkdir(parents=True, exist_ok=False)
            (d / "workflow.yaml").write_text(text, encoding="utf-8"); return f"saved {d.name}/workflow.yaml - open it from Home"
        if p["tool"] == "set_config":
            config.update(a["patch"])
            if wf: wf.log("chief", "CONFIG", "settings changed from CHIEF chat (confirmed): " + ", ".join(flat(a["patch"])))
            return "applied: " + ", ".join(flat(a["patch"]))
        if p["tool"] == "set_voice":
            from .video import voices as VO
            pr = VO.Library().set(a["name"], **a["changes"])
            if wf: wf.log("chief", "CONFIG", f"voice for {a['name']} changed from CHIEF chat (confirmed): {pr['voice']} {pr['rate']:+d}% {pr['pitch']:+d}Hz {pr['style']}")
            return f"{a['name']}: {pr['voice']} rate {pr['rate']:+d}% pitch {pr['pitch']:+d}Hz {pr['style']} - used for every line of {a['name']} from now on"
        if p["tool"] in ("create_character", "create_cast"):
            from .video import characters as CH
            st = CH.Store()
            if p["tool"] == "create_character":
                st.create(a["name"], a["description"], personality=a.get("personality", ""))
                if wf: wf.log("chief", "STUDIO", f"character {a['name']} created from CHIEF chat (confirmed)")
                return f"created {a['name']} - open Character Studio (/characters) to make the sheet, lock it and bind a voice"
            st.save_cast(a["name"], a["members"], a.get("plot", ""))
            if wf: wf.log("chief", "STUDIO", f"cast {a['name']} created from CHIEF chat (confirmed)")
            return f"cast {a['name']} saved - open Character Studio > Cast and press 'Shoot with this cast'"
        if p["tool"] == "run_sample":
            if a.get("data") is not None and getattr(wf, "submit_fields", None) is not None and hasattr(wf, "submit"):
                it = wf.submit(data=a["data"]); wf.wake.set(); return f"submitted item #{it['id']} and started a cycle - watch the live flow"
            wf.wake.set(); return "started a cycle - watch the live flow"
        raise ValueError("unknown tool")

    # ---- the conversation
    def system_prompt(self):
        wf = self.ctx.get("wf")
        ctx = dict(workflow=wf.definition() if wf else None, seats={k: dict(provider=v.get("provider"), model=v.get("model")) for k, v in self.cfg()["seats"].items()},
                   keys_present={k: v for k, v in llm.key_status().items()}, settings=(self.ctx.get("config").data.get("settings") if self.ctx.get("config") else None),
                   display=(self.ctx.get("config").data.get("display") if self.ctx.get("config") else None))
        return ("You are CHIEF, the friendly built-in assistant of SeatCrew, a desktop app where a team of 'seats' checks items in a chain. "
                "Explain in plain words for beginners. Reply in language code: " + self.lang + ". Facts: CHIEF assigns work each cycle; each seat judges with rules and "
                "optionally an AI (AI can only make it more cautious); any BLOCKED check stops the item; a human seat approves. Trading is paper-only, never real money. "
                "Never ask for or repeat API keys - tell users to use the setup wizard or AI Seats tab. "
                "You may call ONE tool. Reply ONLY with JSON: {\"reply\": \"...\", \"tool\": null | \"who_decides\" | \"troubleshoot\" | \"create_workflow\" | \"set_config\" | \"run_sample\", \"args\": {}}. "
                "create_workflow args: {\"yaml\": \"<SeatCrew workflow.yaml: name (snake_case), title, submit [{name,label}], seats [{name, job, rules:[{require:[f]}|{max_len:{field,max}}|{min_len:{field,min}}|{block_if_match:{field,pattern,reason}}|{require_match:{field,pattern,reason}}], ai:{labels,block,prompt}} or {name, job, human: true}], chain [seat names], sample_items [..]>\"}. "
                + ("This is a VIDEO STUDIO workflow: to make a video call run_sample with args {\"data\": {\"topic\": \"...\", \"notes\": \"optional script\", \"template\": \"emotional_story|knowledge_explainer|product_promo\", \"aspect\": \"9:16|16:9\"}}; "
                   "to adjust it use set_config on settings (template, aspect, tts_backend, visuals_backend, video_model, clips_dir, bgm_path, crf...). Quality matters: offline/draft output is labeled DRAFT PREVIEW and is not final; "
                   "To help pick providers: video best quality = kling (kling-3.0) / runway (gen4.5) / gemini (gemini-omni-1.1-flash); best value = minimax (MiniMax-H3) / luma (ray-3.2); free = draft. Voice best quality = elevenlabs / minimax; value = doubao / azure (real SSML styles) / openai; free = edge. Sora API is discontinued. Set visuals_backend / tts_backend with set_config; the Recommended models panel has links and a Test key button; prices are rough, tell the user to check the official pricing page. "
                   "final quality needs ElevenLabs/OpenAI/edge-tts voice and real clips (own folder, Replicate video model, or OpenAI/Stability images). "
                   "Character Studio (/characters): create_character args {\"name\": ..., \"description\": \"look, age, outfit\", \"personality\": ...}; create_cast args {\"name\": ..., \"members\": [{\"character\": ..., \"role\": \"lead|supporting|comic|antagonist|narrator|cameo\", \"notes\": ...}] (max 5, existing characters), \"plot\": ...}. "
                   "Each character has ONE saved voice (character voice library). To change one call set_voice with args {\"name\": \"<character>\", \"adjust\": \"older|younger|slower|faster|lower|higher|softer|louder\"} "
                   "or {\"name\": ..., \"changes\": {\"preset\": \"zh-CN/elderly_woman\", \"style\": \"gentle|sad|tender|cheerful|calm|...\", \"rate\": -10, \"pitch\": -6, \"voice\": \"zh-CN-XiaoxiaoNeural\", \"openai_voice\": \"sage\"}}. "
                   if getattr(wf, "studio", None) == "video" else "") +
                "set_config args: {\"patch\": {partial config, e.g. {\"display\":{\"theme\":\"light\"}} or {\"seats\":{\"risk\":{\"provider\":\"ollama\"}}} or {\"settings\":{...}}}}. "
                "run_sample args: {} or {\"data\": {...}}. Changing tools are only PROPOSED; the user confirms in the UI. Context: " + json.dumps(ctx, ensure_ascii=False, default=str)[:6000])

    def send(self, text):
        text = str(text or "").strip()[:4000]
        if not text: raise ValueError("empty message")
        clean, removed = scrub(text); out = []
        with self.lock:
            self._add("user", clean)
            if removed: out.append(self._add("chief", tx(self.lang, "key_removed"), kind="warn"))
            p = self.provider(); tool, args, reply = None, {}, ""
            if p:
                hist = "\n".join(f"{m['role']}: {m['text']}" for m in self.hist[-10:-1] if m["role"] in ("user", "chief"))
                try:
                    raw, _ = llm.chat(p, self.system_prompt(), (f"Earlier:\n{hist}\n\n" if hist else "") + "User: " + clean, self.cfg(), max_tokens=1200)
                    m = re.search(r"\{.*\}", raw, re.S); j = {}
                    if m:
                        try: j = json.loads(m.group(0))
                        except ValueError: j = {}
                    reply = str(j.get("reply") or (raw if not m else "")).strip(); tool = j.get("tool"); args = j.get("args") or {}
                    if not isinstance(args, dict): args = {}
                except llm.LLMError as e:
                    out.append(self._add("chief", f"AI error ({p}): {e}. " + tx(self.lang, "offline"), kind="warn")); p = None
            if not p:
                tool, args, reply = self.offline_intent(clean)
            if reply: out.append(self._add("chief", reply))
            if tool in READ_TOOLS:
                txt, extra = (self.who_decides() if tool == "who_decides" else self.troubleshoot() if tool == "troubleshoot" else (self.faq(args.get("topic", clean)), {}))
                out.append(self._add("chief", txt, kind="tool", tool=tool, **extra))
            elif tool in ACTION_TOOLS:
                try:
                    prop = self.propose(tool, args)
                    out.append(self._add("chief", tx(self.lang, "confirm_needed"), kind="proposal", status="pending", proposal=prop))
                except ValueError as e: out.append(self._add("chief", str(e), kind="warn"))
            if not out or out[-1]["role"] == "user": out.append(self._add("chief", self.faq(clean)))
            self._save()
        return dict(ok=True, messages=out, offline=self.provider() is None)

    def offline_intent(self, q):
        ql = q.lower()
        if re.search(r"who decides|who.*decid|谁.*(决|定)|誰.*(決|定)|誰が|quién decide|assign|分工|分配", ql): return "who_decides", {}, ""
        if re.search(r"error|not work|broken|fail|troubleshoot|missing|key missing|报错|错误|不工作|失败|故障|エラー|error|falla", ql) and not re.search(r"create|创建|新建", ql): return "troubleshoot", {}, ""
        if re.search(r"(recommend|which|best|cheap|free).{0,30}(model|provider|video api|tts|voice api)|(model|provider)s?.{0,20}(recommend|should i)|推荐.{0,6}模型|哪个模型|哪個模型|推薦.{0,6}模型|用什么模型|おすすめ.{0,6}モデル|どのモデル|qué modelo|recomienda.{0,10}modelo", ql):
            return None, {}, self.models_answer(ql)
        vi = self.video_intent(q, ql)
        if vi: return vi
        if re.search(r"(create|new|make|build).{0,20}(workflow|flow|pipeline)|创建|新建.*(工作流|流程)|建立.*流程|作って|crea(r)? un flujo", ql):
            return "create_workflow", dict(description=re.sub(r"^(please\s+)?(create|make|build)\s+(a|an)?\s*(new\s+)?(workflow|flow)\s*(that|to|for)?\s*", "", q, flags=re.I)), ""
        if re.search(r"run.*sample|try.*sample|运行.*(样例|示例)|試.*サンプル|ejecuta", ql): return "run_sample", {}, ""
        return None, {}, tx(self.lang, "offline") + "\n" + self.faq(q) if not self.hist[:-1] or len(self.hist) < 3 else self.faq(q)

    def models_answer(self, ql=""):
        """Recommended video + voice models in three tiers, with links (same data as the Recommended models panel)."""
        from .video import providers as PV
        H = {"en": ("Recommended models", "Best quality", "Best value", "Free / draft", "Video", "Voice / TTS", "key set", "prices are rough - check the official pricing page"),
             "zh-CN": ("推荐模型", "最佳画质", "最高性价比", "免费 / 草稿", "视频", "配音", "已设置密钥", "价格仅供参考，请以官方定价页为准"),
             "zh-TW": ("推薦模型", "最佳畫質", "最高性價比", "免費 / 草稿", "影片", "配音", "已設定金鑰", "價格僅供參考，請以官方定價頁為準"),
             "ja": ("おすすめモデル", "最高品質", "コスパ重視", "無料 / 下書き", "動画", "音声", "キー設定済み", "価格は目安です。公式料金ページを確認してください"),
             "es": ("Modelos recomendados", "Mejor calidad", "Mejor valor", "Gratis / borrador", "Vídeo", "Voz", "clave configurada", "precios aproximados: revisa la página oficial")}
        h = H.get(self.lang) or H["en"]; rec = PV.recommended(); out = [f"{h[0]} ({PV.CHECKED}) - {h[7]}"]
        kinds = ["tts"] if re.search(r"tts|voice|配音|语音|語音|声|音声|voz", ql) and not re.search(r"video|视频|影片|動画|vídeo", ql) else \
                ["video"] if re.search(r"video|视频|影片|動画|vídeo", ql) and not re.search(r"tts|voice|配音|语音|音声|voz", ql) else ["video", "tts"]
        for k in kinds:
            out.append(f"\n{h[4] if k == 'video' else h[5]}")
            for t, lab in (("best_quality", h[1]), ("best_value", h[2]), ("free_draft", h[3])):
                out.append(f"- {lab}: " + "; ".join(f"{e['provider']} {e['model']}" + (f" ({', '.join(e['env'])}{' ✓ ' + h[6] if e['configured'] and e['env'] else ''})" if e['env'] else "")
                                                   + (f" {e['docs']}" if e['docs'] else "") for e in rec[k][t]))
        return "\n".join(out)

    def video_intent(self, q, ql):
        """Video studio workflows: "make a video about X", "switch to 16:9", "use the product promo template"."""
        wf = self.ctx.get("wf")
        if getattr(wf, "studio", None) != "video": return None
        tpl = ("product_promo" if re.search(r"promo|product|广告|宣传|產品|宣傳|プロモ|商品|producto", ql) else
               "emotional_story" if re.search(r"story|emotional|故事|情感|ストーリー|物語|historia", ql) else
               "knowledge_explainer" if re.search(r"explain|knowledge|science|讲解|知识|科普|講解|知識|解説|explica", ql) else None)
        m = (re.search(r"(?:video|short|clip|reel)\s+(?:about|on|explaining|for)\s+(.+)", q, re.I) or re.search(r"(?:关于|關於)(.+?)的(?:短)?(?:视频|影片)", q)
             or re.search(r"(.+?)(?:についての|について|の)(?:動画|ショート)", q) or re.search(r"(?:vídeo|video)\s+sobre\s+(.+)", q, re.I)
             or re.search(r"(?:做|生成|制作|製作)(?:一个|一支|一條|一条)?(.+?)(?:的)?(?:短)?(?:视频|影片)", q))
        if m and re.search(r"make|create|generate|produce|做|生成|制作|製作|作って|作成|haz|crea|genera|video|vídeo|视频|影片|動画", ql):
            topic = m.group(1).strip(" .?!。？！\"'")[:200]
            if topic: return "run_sample", dict(data=dict(topic=topic, notes="", template=tpl or self.ctx["config"].data["settings"]["template"], aspect=self.ctx["config"].data["settings"]["aspect"])), ""
        cc = self.character_intent(q, ql)
        if cc: return cc
        vv = self.voice_intent(q, ql)
        if vv: return vv
        patch = {}
        if re.search(r"16:9|landscape|horizontal|横屏|橫式|横向|横長|horizontal", ql): patch["aspect"] = "16:9"
        elif re.search(r"9:16|vertical|portrait|竖屏|直式|縦|vertical", ql): patch["aspect"] = "9:16"
        if tpl and re.search(r"template|style|模板|範本|风格|テンプレ|plantilla|default|默认", ql): patch["template"] = tpl
        if patch: return "set_config", dict(patch=dict(settings=patch)), ""
        return None

    def character_intent(self, q, ql):
        """"create a character named Mia: a 30-year-old nurse..." / "创建角色 小美：..." -> create_character;
        "make a cast called Family with Mia, Leo and Ann" / "组建剧组 一家人：小美、小宇" -> create_cast."""
        m = (re.search(r"(?:create|make|new|add)\s+(?:a\s+)?character\s+(?:named\s+|called\s+)?([^\s:,，：]{1,40})\s*[:,，：-]\s*(.+)", q, re.I)
             or re.search(r"(?:创建|新建|添加|建立|新增)角色\s*[「“\"]?([^\s:,，：」”\"]{1,40})[」”\"]?\s*[:,，：]\s*(.+)", q)
             or re.search(r"キャラ(?:クター)?\s*[「]?([^\s:,，：」]{1,40})[」]?\s*(?:を作成|を作って)?\s*[:：]\s*(.+)", q)
             or re.search(r"(?:crea|nuevo)\s+(?:un\s+)?personaje\s+(?:llamado\s+)?([^\s:,]{1,40})\s*[:,]\s*(.+)", q, re.I))
        if m: return "create_character", dict(name=m.group(1).strip(), description=m.group(2).strip(" .。")), ""
        m = (re.search(r"(?:create|make|build|new)\s+(?:a\s+)?cast\s+(?:named\s+|called\s+)?([^\s:,]{1,40})\s*(?:with|:)\s*(.+)", q, re.I)
             or re.search(r"(?:组建|创建|新建|組建|建立)(?:剧组|劇組)\s*[「“\"]?([^\s:,，：」”\"]{1,40})[」”\"]?\s*[:,，：]\s*(.+)", q)
             or re.search(r"キャスト\s*[「]?([^\s:,，：」]{1,40})[」]?\s*[:：]\s*(.+)", q)
             or re.search(r"(?:crea|nuevo)\s+(?:un\s+)?elenco\s+(?:llamado\s+)?([^\s:,]{1,40})\s*(?:con|:)\s*(.+)", q, re.I))
        if m:
            names = [x.strip(" .。") for x in re.split(r",|，|、|\band\b|\by\b|和|と", m.group(2)) if x.strip(" .。")]
            return "create_cast", dict(name=m.group(1).strip(), members=[dict(character=n) for n in names[:6]]), ""
        return None

    VOICE_ADJ = [("older", r"older|老一[点些]|更老|苍老|年纪大|老けて|年上|mayor|más viej"), ("younger", r"younger|年轻一?[点些]|更年轻|嫩一[点些]|若く|más joven"),
                 ("slower", r"slower|慢一?[点些]|放慢|ゆっくり|más lent"), ("faster", r"faster|快一?[点些]|加快|速く|más rápid"),
                 ("lower", r"lower|deeper|低沉|低一?[点些]|低く|más grave"), ("higher", r"higher|高一?[点些]|尖一?[点些]|高く|más agud"),
                 ("softer", r"softer|quieter|轻一?[点些]|小声|柔一?[点些]|静かに|más suave"), ("louder", r"louder|大声|响一?[点些]|大きく|más fuerte")]
    ALIASES = {"妈妈": r"mom|mum|mother|妈|媽|母|mamá|madre", "爸爸": r"dad|father|爸|父|papá|padre", "narrator": r"narrator|旁白|ナレーター|narrador"}
    def voice_intent(self, q, ql):
        """"make mom sound older" / "让妈妈的声音老一点" -> set_voice (needs a character with that name in the voice library)."""
        if not re.search(r"voice|sound|声|聲|音|voz|suen", ql): return None
        from .video import voices as VO
        chars = list(VO.Library().all())
        name = next((n for n in sorted(chars, key=len, reverse=True) if n.lower() in ql), None)
        if not name:
            for n in chars:
                al = next((a for k, a in self.ALIASES.items() if k == n or re.search(a, n)), None)
                if al and re.search(al, ql): name = n; break
        if not name: return None
        adj = next((k for k, rx in self.VOICE_ADJ if re.search(rx, ql)), None)
        if adj: return "set_voice", dict(name=name, adjust=adj), ""
        st = next((s for s in VO.STYLES if s in ql), None)
        if st: return "set_voice", dict(name=name, changes=dict(style=st)), ""
        return None

    def confirm(self, mid, approve):
        with self.lock:
            m = next((x for x in self.hist if x["id"] == mid and x.get("kind") == "proposal"), None)
            if not m: raise ValueError("no such proposal")
            if m.get("status") != "pending": raise ValueError(f"proposal already {m.get('status')}")
            if not approve:
                m["status"] = "cancelled"; r = self._add("chief", tx(self.lang, "cancelled"))
            else:
                try: res = self.execute(m["proposal"]); m["status"] = "applied"; r = self._add("chief", tx(self.lang, "done") + " " + res)
                except (ValueError, OSError, KeyError) as e: m["status"] = "failed"; r = self._add("chief", f"failed: {e}", kind="warn")
                cb = self.ctx.get("on_change")
                if cb and m["status"] == "applied": cb(m["proposal"]["tool"])
            self._save(); return dict(ok=m["status"] != "failed", status=m["status"], message=r)

def route(asst, method, path, body=None):
    """Shared HTTP routes. Returns (obj, code) or None when the path is not a chat route."""
    if path == "/api/models" and method == "GET":
        from .video import providers as PV
        return dict(tiers=PV.recommended(), checked=PV.CHECKED, i18n=PV.i18n()), 200
    if path == "/api/models/test" and method == "POST":
        from .video import providers as PV
        i = str((body or {}).get("id", ""))
        if not any(e["id"] == i for e in PV.CATALOG): return {"error": "unknown model"}, 404
        return PV.test_key(i), 200
    if not path.startswith("/api/chat"): return None
    if method == "GET" and path == "/api/chat": return asst.status(), 200
    if method == "POST" and path == "/api/chat": return asst.send((body or {}).get("message", "")), 200
    if method == "POST" and path == "/api/chat/confirm": return asst.confirm(str((body or {}).get("id", "")), bool((body or {}).get("approve"))), 200
    if method == "POST" and path == "/api/chat/clear": return asst.clear(), 200
    return {"error": "not found"}, 404

WEB = Path(__file__).parent / "web"
def static(path):
    """chat.js / chat page shared by every server."""
    if path == "/models.js": return (WEB / "models.js").read_bytes(), "application/javascript; charset=utf-8"
    if path == "/chat.js": return (WEB / "chat.js").read_bytes(), "application/javascript; charset=utf-8"
    if path == "/chat": return (WEB / "chat.html").read_bytes(), "text/html; charset=utf-8"
    return None

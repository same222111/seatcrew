/* First-run "adapt to this PC" panel: detection, one-click recommended setup, account login via the official
   Codex / Claude CLIs (SeatCrew only relays the sign-in link/code; it never sees a token), and free local voices. */
(()=>{
const S={
en:{det:"Detected on this PC",gpu:"GPU",nogpu:"no NVIDIA GPU (CPU only)",ram:"RAM",disk:"free in data folder",rec:"Recommended",use:"Use recommended setup",
 acc:"Use your own account (no API key)",lcx:"Log in with ChatGPT / Codex",lcl:"Log in with Claude",dev:"device code",inst:"Not installed - install with:",
 in:"✓ signed in",out:"not signed in",open:"Open sign-in page",code:"one-time code",paste:"Paste the code shown after sign-in",send:"Send",wait:"Waiting for sign-in…",
 done:"Signed in ✓",fail:"Sign-in did not finish",ol:"Ollama (free local models)",olm:"models",olno:"not running",keys:"API keys found",none:"none",
 tok:"SeatCrew never reads or stores your login tokens - the official CLI keeps them.",demo:"Works right now with zero keys (demo mode); add an account any time.",
 vT:"Free voices",edge:"edge-tts (free Microsoft neural voices) - ready, default",vInst:"Install",vDone:"installed",nc:"NON-COMMERCIAL - not installed by default",
 into:"Installs into",cpu:"No NVIDIA GPU: local engines run on CPU and are slow.",clT:"Clone a character voice (your own / consented recording)",
 clN:"Voice name",clW:"Recording path (.wav, 5-15 s)",clX:"Exact words spoken in the recording",clC:"I am this speaker or have the speaker's explicit permission. I will not use it to deceive anyone.",
 clB:"Save voice",clOk:"Saved - use voice",steps:"It will run",confirm:"Start install?"},
"zh-CN":{det:"本机检测结果",gpu:"显卡",nogpu:"无 NVIDIA 显卡(仅 CPU)",ram:"内存",disk:"数据目录可用空间",rec:"推荐方案",use:"一键使用推荐设置",
 acc:"用你自己的账号(无需 API 密钥)",lcx:"用 ChatGPT / Codex 登录",lcl:"用 Claude 登录",dev:"设备码",inst:"未安装 - 安装命令:",
 in:"✓ 已登录",out:"未登录",open:"打开登录页面",code:"一次性验证码",paste:"粘贴登录后显示的代码",send:"提交",wait:"等待登录…",
 done:"已登录 ✓",fail:"登录未完成",ol:"Ollama(免费本地模型)",olm:"个模型",olno:"未运行",keys:"已找到的 API 密钥",none:"无",
 tok:"SeatCrew 从不读取或保存你的登录令牌,令牌由官方 CLI 自己保管。",demo:"零密钥也能马上用(演示模式);随时可以再登录账号。",
 vT:"免费配音",edge:"edge-tts(免费微软神经语音)- 已就绪,默认",vInst:"安装",vDone:"已安装",nc:"仅限非商业 - 默认不安装",
 into:"安装到",cpu:"没有 NVIDIA 显卡:本地引擎将用 CPU 运行,速度较慢。",clT:"克隆角色声音(本人或已获授权的录音)",
 clN:"声音名称",clW:"录音路径(.wav,5-15 秒)",clX:"录音里说的原话",clC:"我就是说话人,或已获得说话人的明确许可。我不会用它欺骗任何人。",
 clB:"保存声音",clOk:"已保存 - 使用声音",steps:"将执行",confirm:"开始安装?"},
"zh-TW":{det:"本機偵測結果",gpu:"顯示卡",nogpu:"無 NVIDIA 顯示卡(僅 CPU)",ram:"記憶體",disk:"資料夾可用空間",rec:"建議方案",use:"一鍵套用建議設定",
 acc:"用你自己的帳號(免 API 金鑰)",lcx:"用 ChatGPT / Codex 登入",lcl:"用 Claude 登入",dev:"裝置碼",inst:"未安裝 - 安裝指令:",
 in:"✓ 已登入",out:"未登入",open:"開啟登入頁面",code:"一次性驗證碼",paste:"貼上登入後顯示的代碼",send:"送出",wait:"等待登入…",
 done:"已登入 ✓",fail:"登入未完成",ol:"Ollama(免費本機模型)",olm:"個模型",olno:"未執行",keys:"已找到的 API 金鑰",none:"無",
 tok:"SeatCrew 從不讀取或儲存你的登入權杖,權杖由官方 CLI 自行保管。",demo:"零金鑰即可馬上使用(展示模式);隨時可再登入帳號。",
 vT:"免費配音",edge:"edge-tts(免費微軟神經語音)- 已就緒,預設",vInst:"安裝",vDone:"已安裝",nc:"僅限非商業 - 預設不安裝",
 into:"安裝到",cpu:"沒有 NVIDIA 顯示卡:本機引擎將以 CPU 執行,速度較慢。",clT:"複製角色聲音(本人或已獲授權的錄音)",
 clN:"聲音名稱",clW:"錄音路徑(.wav,5-15 秒)",clX:"錄音中說的原話",clC:"我就是說話者,或已取得說話者明確許可。我不會用它欺騙任何人。",
 clB:"儲存聲音",clOk:"已儲存 - 使用聲音",steps:"將執行",confirm:"開始安裝?"},
ja:{det:"この PC の検出結果",gpu:"GPU",nogpu:"NVIDIA GPU なし(CPU のみ)",ram:"メモリ",disk:"データフォルダの空き",rec:"おすすめ",use:"おすすめ設定を使う",
 acc:"自分のアカウントを使う(API キー不要)",lcx:"ChatGPT / Codex でログイン",lcl:"Claude でログイン",dev:"デバイスコード",inst:"未インストール - インストール:",
 in:"✓ ログイン済み",out:"未ログイン",open:"ログインページを開く",code:"ワンタイムコード",paste:"ログイン後に表示されるコードを貼り付け",send:"送信",wait:"ログイン待ち…",
 done:"ログイン完了 ✓",fail:"ログインが完了しませんでした",ol:"Ollama(無料ローカルモデル)",olm:"モデル",olno:"停止中",keys:"見つかった API キー",none:"なし",
 tok:"SeatCrew はログイントークンを読み取らず保存もしません(公式 CLI が管理)。",demo:"キーなしですぐ使えます(デモモード)。アカウントはいつでも追加可能。",
 vT:"無料ボイス",edge:"edge-tts(無料の Microsoft ニューラル音声)- 準備完了・既定",vInst:"インストール",vDone:"インストール済み",nc:"非商用のみ - 既定ではインストールしません",
 into:"インストール先",cpu:"NVIDIA GPU がないため、ローカルエンジンは CPU で動作し低速です。",clT:"キャラクターの声をクローン(本人または許可を得た録音)",
 clN:"声の名前",clW:"録音ファイルのパス(.wav、5〜15 秒)",clX:"録音で話している正確な文",clC:"私は話者本人であるか、話者の明確な許可を得ています。人を欺く目的には使いません。",
 clB:"声を保存",clOk:"保存しました - voice",steps:"実行内容",confirm:"インストールを開始しますか?"},
es:{det:"Detectado en este equipo",gpu:"GPU",nogpu:"sin GPU NVIDIA (solo CPU)",ram:"RAM",disk:"libre en la carpeta de datos",rec:"Recomendado",use:"Usar la configuración recomendada",
 acc:"Usa tu propia cuenta (sin clave API)",lcx:"Iniciar sesión con ChatGPT / Codex",lcl:"Iniciar sesión con Claude",dev:"código de dispositivo",inst:"No instalado - instala con:",
 in:"✓ sesión iniciada",out:"sin sesión",open:"Abrir la página de inicio de sesión",code:"código de un solo uso",paste:"Pega el código que aparece tras iniciar sesión",send:"Enviar",wait:"Esperando el inicio de sesión…",
 done:"Sesión iniciada ✓",fail:"El inicio de sesión no terminó",ol:"Ollama (modelos locales gratis)",olm:"modelos",olno:"no está en marcha",keys:"Claves API encontradas",none:"ninguna",
 tok:"SeatCrew nunca lee ni guarda tus tokens: los guarda la CLI oficial.",demo:"Funciona ya sin claves (modo demo); añade una cuenta cuando quieras.",
 vT:"Voces gratis",edge:"edge-tts (voces neuronales gratis de Microsoft) - lista, predeterminada",vInst:"Instalar",vDone:"instalado",nc:"NO COMERCIAL - no se instala por defecto",
 into:"Se instala en",cpu:"Sin GPU NVIDIA: los motores locales usan la CPU y van lentos.",clT:"Clonar la voz de un personaje (tu voz o una grabación con permiso)",
 clN:"Nombre de la voz",clW:"Ruta de la grabación (.wav, 5-15 s)",clX:"Palabras exactas de la grabación",clC:"Soy quien habla o tengo su permiso explícito. No la usaré para engañar a nadie.",
 clB:"Guardar voz",clOk:"Guardada - usa la voz",steps:"Ejecutará",confirm:"¿Empezar la instalación?"}};
const lang=()=>{try{return L}catch(e){return "en"}},t=k=>((S[lang()]||S.en)[k])||S.en[k], g=id=>document.getElementById(id), esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const J=async(p,b)=>(await fetch(p,b?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}:{})).json();
let D=null,V=null;
const css=document.createElement("style");css.textContent=`.sd{border:1px solid var(--ln);border-radius:12px;padding:12px 14px;margin:0 0 12px}.sd .k{display:inline-block;margin:2px 14px 2px 0}.sd .acc{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:8px}
.sd .box{border:1px solid var(--ln);border-radius:10px;padding:10px}.sd button{margin-top:8px}.sd code{overflow-wrap:anywhere;font:12px var(--mono);background:#05080d;padding:2px 6px;border-radius:6px;user-select:all}.sd .big{font:800 22px var(--mono);color:var(--acc);letter-spacing:.1em}.sd .warn{color:var(--warn)}`;document.head.appendChild(css);
function host(id,parent,first){let e=g(id);if(!e){e=document.createElement("div");e.id=id;e.className="sd";const p=g(parent);if(!p)return null;first?p.prepend(e):p.insertBefore(e,p.querySelector("button"))}return e}
function cliBox(tool){const c=D.cli[tool],lbl=tool=="codex"?t("lcx"):t("lcl");
 return `<div class="box"><b>${esc(c.label)}</b> <span class="${c.logged_in?"ok":"dim"}">${c.installed?(c.logged_in?t("in"):t("out")):""}</span> <span class="dim">${esc(c.version||"")}</span>
 ${c.installed?`<br><button data-login="${tool}">${lbl}</button>${tool=="codex"?` <button class="ghost" data-login="${tool}" data-dev="1">${t("dev")}</button>`:""}`:`<div class="dim">${t("inst")}<br><code>${esc(c.install)}</code><br><code>${esc(c.install_alt||"")}</code></div><button class="ghost" data-recheck>↻</button>`}
 <div id="lj-${tool}"></div></div>`}
function paintDetect(){const e=host("sdDetect","st2",true);if(!e||!D)return;const R=D.recommended,G=D.gpu;const keys=Object.entries(D.keys).filter(([k,v])=>v).map(([k])=>k);
 e.innerHTML=`<h2>${t("det")}</h2><span class="k">${esc(D.os.system)} ${esc(D.os.machine)}</span><span class="k">CPU × ${D.cpu_count}</span><span class="k">${t("ram")} ${D.ram_gb??"?"} GB</span>
 <span class="k">${t("gpu")}: ${G?esc(G.name)+(G.vram_gb?` ${G.vram_gb} GB`:""):`<span class="warn">${t("nogpu")}</span>`}</span><span class="k">${D.disk_free_gb??"?"} GB ${t("disk")}</span>
 <div style="margin-top:8px"><b>${t("rec")}:</b> ${esc(R.chat_provider||"demo")} · voice ${esc(R.voice)}${R.clone_engine?` · ${esc(R.clone_engine)} (${esc(R.clone_device)})`:""}<div class="dim">${esc(R.why.join("; "))}</div>${R.warning?`<div class="warn">${esc(R.warning)}</div>`:""}
 ${R.chat_provider?"":`<div class="dim">${t("demo")}</div>`}<button id="sdUse">${t("use")}</button> <span id="sdUseOut"></span></div>
 <h2 style="margin-top:14px">${t("acc")}</h2><div class="acc">${cliBox("codex")}${cliBox("claude")}
 <div class="box"><b>${t("ol")}</b> <span class="${D.ollama.running?"ok":"dim"}">${D.ollama.running?`✓ ${D.ollama.models.length} ${t("olm")}`:t("olno")}</span><div class="dim">${esc(D.ollama.models.slice(0,3).join(", "))}</div>
 ${D.ollama.running&&!D.ollama.models.length?`<code>${esc(D.ollama.pull)}</code>`:D.ollama.running?"":`<a href="${D.ollama.install}" target="_blank" rel="noopener">ollama.com/download</a>`}</div>
 <div class="box"><b>${t("keys")}</b><div class="dim">${keys.length?esc(keys.join(", ")):t("none")}</div></div></div><p class="dim">🔒 ${t("tok")}</p>`;
 e.querySelectorAll("[data-login]").forEach(b=>b.onclick=()=>login(b.dataset.login,!!b.dataset.dev));e.querySelectorAll("[data-recheck]").forEach(b=>b.onclick=load);
 g("sdUse").onclick=async()=>{const r=await J("/api/recommend-apply",{language:(g("lang")||{}).value});g("sdUseOut").textContent=r.ok?"✓ "+(r.provider||"demo"):r.error;
  if(r.ok&&typeof step=="function"){H=await J("/api/home");step(4)}}}
async function login(tool,dev){const o=g("lj-"+tool);o.innerHTML=`<span class="dim">${t("wait")}</span>`;let j=await J("/api/cli-login",{tool,device:dev});if(j.ok===false){o.innerHTML=`<span class="err">${esc(j.error)}</span>`;return}
 const id=j.id;let pasted=false;const tick=async()=>{j=await J("/api/cli-login/"+id);
  o.innerHTML=(j.url?`<div><a href="${esc(j.url)}" target="_blank" rel="noopener">${t("open")} ↗</a></div>`:"")+(j.code?`<div>${t("code")}: <span class="big">${esc(j.code)}</span></div>`:"")+
   (tool=="claude"&&j.url&&!j.done&&!pasted?`<label>${t("paste")}</label><input id="lc-${id}" autocomplete="off"><button class="ghost" id="lcb-${id}">${t("send")}</button>`:"")+
   `<div class="${j.done?(j.ok?"ok":"err"):"dim"}">${j.done?(j.ok?t("done"):t("fail")+": "+esc(j.lines.slice(-1)[0]||"")):t("wait")}</div>`;
  const b=g("lcb-"+id);if(b)b.onclick=async()=>{pasted=true;await J("/api/cli-login/code",{id,code:g("lc-"+id).value})};
  if(j.done){if(j.ok)setTimeout(load,800);return}setTimeout(tick,j.url&&!pasted&&tool=="claude"?4000:1500)};tick()}
function paintVoice(){const e=host("sdVoice","st3",true);if(!e||!V||!D)return;
 e.innerHTML=`<h2>${t("vT")}</h2><div class="ok">✓ ${D.edge_tts?t("edge"):"edge-tts: pip install edge-tts"}</div>${D.gpu&&D.gpu.cuda?"":`<div class="warn">${t("cpu")}</div>`}<div class="acc">`+
 Object.values(V.engines).map(x=>`<div class="box"><b>${esc(x.label)}</b> <span class="tag">${esc(x.license)}</span>${x.commercial?"":`<div class="warn">${t("nc")}</div>`}
  ${x.installed?`<div class="ok">✓ ${t("vDone")}</div>`:x.installable?`<div class="dim">${t("into")} <code>${esc(x.path)}</code></div><button class="ghost" data-inst="${x.engine}">${t("vInst")}</button>`:""}
  ${x.run?`<div class="dim">${x.running?"✓ api":""} <code>${esc(x.run)}</code></div>`:""}<div class="dim"><a href="${esc(x.docs)}" target="_blank" rel="noopener">docs</a></div><div id="vj-${x.engine}"></div></div>`).join("")+`</div>
 <h2 style="margin-top:14px">${t("clT")}</h2><div class="row"><div><label>${t("clN")}</label><input id="clN"></div><div><label>${t("clW")}</label><input id="clW" placeholder="D:\\voices\\me.wav"></div></div>
 <label>${t("clX")}</label><input id="clX"><label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="clC" style="width:auto"> <span>${t("clC")}</span></label>
 <button class="ghost" id="clB" disabled>${t("clB")}</button> <span id="clO"></span><div class="dim">${esc(V.clones.map(c=>c.name+" → clone:"+c.id).join(" · "))}</div>`;
 g("clC").onchange=()=>g("clB").disabled=!g("clC").checked;
 g("clB").onclick=async()=>{const r=await J("/api/voice-clone",{name:g("clN").value,wav_path:g("clW").value,transcript:g("clX").value,consent:g("clC").checked});
  g("clO").className=r.id?"ok":"err";g("clO").textContent=r.id?`${t("clOk")} clone:${r.id}`:r.error};
 e.querySelectorAll("[data-inst]").forEach(b=>b.onclick=()=>inst(b.dataset.inst))}
async function inst(en){const o=g("vj-"+en);const p=await J("/api/voice-engine/plan",{engine:en});if(p.ok===false){o.innerHTML=`<span class="err">${esc(p.error)}</span>`;return}
 o.innerHTML=`<div class="dim">${t("steps")}:</div>`+p.steps.map(s=>`<code style="display:block;margin:2px 0;white-space:pre-wrap">${esc(s)}</code>`).join("")+`<button id="go-${en}">${t("confirm")}</button>`;
 g("go-"+en).onclick=async()=>{let j=await J("/api/voice-engine/install",{engine:en});if(j.ok===false){o.innerHTML=`<span class="err">${esc(j.error)}</span>`;return}
  const tick=async()=>{j=await J("/api/voice-engine/job/"+j.id);o.innerHTML=`<div>${j.step}/${j.steps} ${j.done?(j.ok?"✓":"✕"):"…"}</div>${j.warning?`<div class="warn">${esc(j.warning)}</div>`:""}<code style="display:block;white-space:pre-wrap">${esc(j.log.slice(-3).join("\n"))}</code>`;
   if(!j.done)setTimeout(tick,2000);else if(j.ok)setTimeout(load,500)};tick()}}
async function load(){[D,V]=await Promise.all([J("/api/detect"),J("/api/voice-engines")]);paintDetect();paintVoice()}
window.SCSetup={load,paint:()=>{paintDetect();paintVoice()}};
addEventListener("load",()=>{load();const l=g("lang");if(l)l.addEventListener("change",()=>setTimeout(SCSetup.paint,0))});
})();

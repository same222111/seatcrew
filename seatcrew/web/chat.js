/* CHIEF chat widget - floating button + panel (or full page when window.CHAT_FULL). Shared by every SeatCrew page.
   Proposals from the AI are shown with a preview and only run when the user presses Confirm. */
(function(){
const S={en:{btn:"CHIEF chat",title:"CHIEF chat",ph:"Ask anything… e.g. who decides?",send:"Send",clear:"Clear",full:"Open full page",close:"Close",confirm:"Confirm",cancel:"Cancel",
  offline:"offline FAQ",demo:"demo mode",pending:"waiting for your confirmation",applied:"applied",cancelled:"cancelled",failed:"failed",
  guideT:"Connect an AI for full chat",guide:"Get a key from one provider (or install free Ollama), then paste it in the setup wizard or the AI Seats tab. Keys stay on this computer.",
  wizard:"Run setup wizard",q:["Who decides?","Explain the check chain","Create a workflow that reviews blog posts","Troubleshoot","Run a sample item"],cleared:"History cleared"},
 "zh-CN":{btn:"总指挥对话",title:"总指挥对话 CHIEF",ph:"随便问… 比如:谁来做决定?",send:"发送",clear:"清空",full:"全屏打开",close:"关闭",confirm:"确认",cancel:"取消",
  offline:"离线问答",demo:"演示模式",pending:"等待你确认",applied:"已应用",cancelled:"已取消",failed:"失败",
  guideT:"连接一个 AI 即可完整对话",guide:"从任一服务商获取密钥(或安装免费的 Ollama),然后在设置向导或「AI 席位」页粘贴。密钥只保存在本机。",
  wizard:"运行设置向导",q:["谁来做决定?","解释一下检查链","创建一个工作流,用来审核博客文章","故障排查","运行一个示例"],cleared:"记录已清空"},
 "zh-TW":{btn:"總指揮對話",title:"總指揮對話 CHIEF",ph:"隨便問… 例如:誰來做決定?",send:"送出",clear:"清空",full:"全頁開啟",close:"關閉",confirm:"確認",cancel:"取消",
  offline:"離線問答",demo:"展示模式",pending:"等待你確認",applied:"已套用",cancelled:"已取消",failed:"失敗",
  guideT:"連接一個 AI 即可完整對話",guide:"從任一服務商取得金鑰(或安裝免費的 Ollama),再到設定精靈或「AI 席位」頁貼上。金鑰只存在本機。",
  wizard:"執行設定精靈",q:["誰來做決定?","解釋檢查鏈","建立一個流程,用來審核部落格文章","故障排除","執行一個範例"],cleared:"紀錄已清空"},
 ja:{btn:"CHIEF チャット",title:"CHIEF チャット",ph:"何でも質問… 例: 誰が決めるの?",send:"送信",clear:"消去",full:"全画面で開く",close:"閉じる",confirm:"確認",cancel:"キャンセル",
  offline:"オフライン FAQ",demo:"デモモード",pending:"確認待ち",applied:"適用済み",cancelled:"キャンセル済み",failed:"失敗",
  guideT:"AI を接続すると会話できます",guide:"いずれかのプロバイダーでキーを取得(または無料の Ollama をインストール)し、セットアップか AI シート画面に貼り付けます。キーはこの PC にのみ保存。",
  wizard:"セットアップを開く",q:["誰が決めるの?","チェックチェーンを説明して","ブログ記事をレビューするワークフローを作って","トラブルシュート","サンプルを実行"],cleared:"履歴を消去しました"},
 es:{btn:"Chat CHIEF",title:"Chat CHIEF",ph:"Pregunta lo que sea… p. ej. ¿quién decide?",send:"Enviar",clear:"Borrar",full:"Abrir a pantalla completa",close:"Cerrar",confirm:"Confirmar",cancel:"Cancelar",
  offline:"FAQ sin conexión",demo:"modo demo",pending:"esperando tu confirmación",applied:"aplicado",cancelled:"cancelado",failed:"falló",
  guideT:"Conecta una IA para chatear",guide:"Consigue una clave de un proveedor (o instala Ollama gratis) y pégala en el asistente inicial o en la pestaña de puestos IA. Las claves se quedan en este equipo.",
  wizard:"Abrir asistente inicial",q:["¿Quién decide?","Explica la cadena de controles","Crea un flujo que revise artículos de blog","Diagnosticar","Ejecutar un ejemplo"],cleared:"Historial borrado"}};
let ST=null,L="en",open=false;const FULL=!!window.CHAT_FULL;
const t=k=>(S[L]||S.en)[k]||S.en[k];const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const HOME=(()=>{const h=new URLSearchParams(location.search).get("home");return h&&/^http:\/\/127\.0\.0\.1:\d+\/$/.test(h)?h:null})();
const css=`#ccBtn{position:fixed;right:22px;bottom:22px;z-index:900;display:flex;gap:8px;align-items:center;background:var(--acc,#3dffa0);color:#04140a;border:0;border-radius:999px;padding:12px 18px;font:800 14px var(--sans,system-ui);cursor:pointer;box-shadow:0 0 0 1px #3dffa066,0 0 26px #3dffa066}
#ccBtn .d{width:9px;height:9px;border-radius:50%;background:#04140a;animation:nxPulse 1.6s infinite}
#ccP{position:fixed;right:22px;bottom:82px;z-index:901;width:min(440px,calc(100vw - 30px));height:min(620px,calc(100vh - 110px));display:none;flex-direction:column;background:var(--pn,#0d1219);border:1px solid var(--acc,#3dffa0);border-radius:14px;box-shadow:0 0 40px #3dffa033,0 20px 60px #000a;overflow:hidden;font:13px var(--mono,monospace);color:var(--fg,#dfe7f2)}
#ccP.open{display:flex;animation:nxIn .25s ease}#ccP.full{position:static;width:auto;height:calc(100vh - 120px);display:flex;max-width:980px;margin:0 auto}
#ccP .hd{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--ln,#1f2a37);background:linear-gradient(90deg,#3dffa014,transparent)}
#ccP .hd b{font:800 14px var(--sans,system-ui);color:var(--acc,#3dffa0)}#ccP .pill{font-size:10px;border:1px solid currentColor;border-radius:6px;padding:1px 6px;color:var(--blue,#5cc8ff)}#ccP .pill.off{color:var(--warn,#ffc94d)}
#ccP .hd .sp{flex:1}#ccP .hd button,#ccP .hd a{background:none;border:1px solid var(--ln,#1f2a37);color:var(--dim,#8a97a8);border-radius:6px;padding:3px 8px;font:inherit;font-size:11px;cursor:pointer;text-decoration:none}
#ccM{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:9px}
.cm{max-width:88%;padding:8px 11px;border-radius:10px;white-space:pre-wrap;line-height:1.45;word-wrap:break-word}.cm.user{align-self:flex-end;background:#3dffa01f;border:1px solid #3dffa055}
.cm.chief{align-self:flex-start;background:var(--pn2,#111925);border:1px solid var(--ln,#1f2a37)}.cm.warn{border-color:var(--warn,#ffc94d);color:var(--warn,#ffc94d)}.cm.tool{border-color:var(--blue,#5cc8ff)}
.cm .who{font-size:10px;letter-spacing:.12em;color:var(--dim,#8a97a8);margin-bottom:3px}.cm pre{margin:6px 0;max-height:220px;overflow:auto;background:#05080d;border:1px solid var(--ln,#1f2a37);border-radius:6px;padding:7px;font-size:11px;white-space:pre}
.cm.prop{border-color:var(--acc,#3dffa0);box-shadow:0 0 14px #3dffa022}.cm .acts{display:flex;gap:8px;margin-top:4px}.cm .acts button{border:0;border-radius:7px;padding:6px 12px;font:inherit;font-weight:700;cursor:pointer;background:var(--acc,#3dffa0);color:#04140a}.cm .acts button.no{background:none;border:1px solid var(--bad,#ff4f6d);color:var(--bad,#ff4f6d)}
.cm .stt{font-size:11px;color:var(--warn,#ffc94d)}.cm .stt.applied{color:var(--acc,#3dffa0)}.cm .stt.cancelled,.cm .stt.failed{color:var(--bad,#ff4f6d)}
#ccG{margin:0 12px 6px;padding:9px 11px;border:1px dashed var(--warn,#ffc94d);border-radius:10px;font-size:12px}#ccG b{color:var(--warn,#ffc94d)}#ccG a{color:var(--blue,#5cc8ff);margin-right:10px}
#ccQ{display:flex;gap:6px;flex-wrap:wrap;padding:0 12px 6px}#ccQ button{background:none;border:1px solid var(--ln,#1f2a37);color:var(--dim,#8a97a8);border-radius:999px;padding:3px 9px;font:inherit;font-size:11px;cursor:pointer}#ccQ button:hover{border-color:var(--acc,#3dffa0);color:var(--acc,#3dffa0)}
#ccF{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--ln,#1f2a37)}#ccF textarea{flex:1;resize:none;height:40px;background:#05080d;color:var(--fg,#dfe7f2);border:1px solid var(--ln,#1f2a37);border-radius:8px;padding:8px;font:inherit}
#ccF button{background:var(--acc,#3dffa0);color:#04140a;border:0;border-radius:8px;padding:0 16px;font:inherit;font-weight:800;cursor:pointer}
body[data-theme=light] #ccP{background:#fff;color:#111}body[data-theme=light] #ccF textarea,body[data-theme=light] .cm pre{background:#f4f6f9;color:#111}body[data-theme=light] .cm.chief{background:#f7f9fb}
body[data-theme=light] #ccBtn,body[data-theme=contrast] #ccBtn{box-shadow:none}`;
function el(h){const d=document.createElement("div");d.innerHTML=h;return d.firstElementChild}
async function api(p,b){const r=await fetch(p,b?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}:{});return r.json()}
function msg(m){const who=m.role=="user"?"YOU":"CHIEF";let x=`<div class="who">${who}</div>${esc(m.text)}`;
 if(m.kind=="proposal"){const p=m.proposal||{};x+=`<div><b>▶ ${esc(p.title||p.tool)}</b></div><pre>${esc(p.preview)}</pre>`;
  x+=m.status=="pending"?`<div class="acts"><button data-ok="${m.id}">✓ ${t("confirm")}</button><button class="no" data-no="${m.id}">✕ ${t("cancel")}</button></div><div class="stt">${t("pending")}</div>`:`<div class="stt ${m.status}">● ${t(m.status)||m.status}</div>`}
 return `<div class="cm ${m.role} ${m.kind=="warn"?"warn":""} ${m.kind=="tool"?"tool":""} ${m.kind=="proposal"?"prop":""}" data-mid="${m.id}">${x}</div>`}
function render(){const p=document.getElementById("ccP");if(!p||!ST)return;L=ST.lang||L;
 p.querySelector(".hd b").textContent="◆ "+t("title");const pl=p.querySelector(".pill");pl.className="pill"+(ST.offline?" off":"");pl.textContent=ST.offline?(ST.demo?t("demo"):t("offline")):(ST.provider+"/"+ST.model);
 p.querySelector("[data-cl]").textContent=t("clear");const fl=p.querySelector("[data-full]");if(fl){fl.textContent=t("full");fl.href="/chat"+location.search}
 const G=document.getElementById("ccG");G.style.display=ST.offline?"block":"none";
 G.innerHTML=`<b>${t("guideT")}</b><div style="margin:4px 0">${esc(t("guide"))}</div>`+Object.entries(ST.links||{}).map(([k,u])=>`<a href="${u}" target="_blank" rel="noopener">${k}${ST.keys&&ST.keys[k]&&k!="ollama"&&k!="custom"?" ✓":""}</a>`).join("")+(HOME||!ST.workflow?`<div style="margin-top:6px"><a href="${HOME||"/"}?wizard=1">→ ${t("wizard")}</a></div>`:"");
 document.getElementById("ccQ").innerHTML=t("q").map(q=>`<button>${esc(q)}</button>`).join("");document.querySelectorAll("#ccQ button").forEach(b=>b.onclick=()=>send(b.textContent));
 const M=document.getElementById("ccM");const hist=ST.history.length?ST.history:[{id:"hi",role:"chief",text:ST.hi}];M.innerHTML=hist.map(msg).join("");M.scrollTop=M.scrollHeight;
 M.querySelectorAll("[data-ok]").forEach(b=>b.onclick=()=>decide(b.dataset.ok,true));M.querySelectorAll("[data-no]").forEach(b=>b.onclick=()=>decide(b.dataset.no,false));
 const ta=document.querySelector("#ccF textarea");ta.placeholder=t("ph");document.querySelector("#ccF button").textContent=t("send");const bt=document.getElementById("ccBtn");if(bt)bt.lastChild.textContent=" "+t("btn")}
async function refresh(){ST=await api("/api/chat");render()}
async function send(text){text=(text||"").trim();if(!text)return;const ta=document.querySelector("#ccF textarea");ta.value="";
 ST.history.push({id:"tmp",role:"user",text});ST.history.push({id:"tmp2",role:"chief",text:"…"});render();
 try{await api("/api/chat",{message:text})}catch(e){}await refresh()}
async function decide(id,ok){await api("/api/chat/confirm",{id,approve:ok});await refresh();if(ok&&window.onChiefChange)window.onChiefChange()}
function mount(){const st=document.createElement("style");st.textContent=css;document.head.appendChild(st);
 const p=el(`<div id="ccP" class="${FULL?"full open":""}" role="dialog" aria-label="CHIEF chat"><div class="hd"><b></b><span class="pill"></span><span class="sp"></span><button data-cl></button>${FULL?"":`<a data-full></a><button data-x>✕</button>`}</div>
  <div id="ccM"></div><div id="ccG"></div><div id="ccQ"></div><div id="ccF"><textarea></textarea><button></button></div></div>`);
 (FULL?document.getElementById("chatHost")||document.body:document.body).appendChild(p);
 if(!FULL){const b=el(`<button id="ccBtn" title="CHIEF chat"><span class="d"></span><span></span></button>`);document.body.appendChild(b);b.onclick=()=>toggle()}
 p.querySelector("[data-cl]").onclick=async()=>{await api("/api/chat/clear",{});await refresh()};const x=p.querySelector("[data-x]");if(x)x.onclick=()=>toggle(false);
 const ta=p.querySelector("textarea");ta.onkeydown=e=>{if(e.key=="Enter"&&!e.shiftKey){e.preventDefault();send(ta.value)}if(e.key=="Escape")e.stopPropagation()};p.querySelector("#ccF button").onclick=()=>send(ta.value);
 refresh()}
function toggle(v){open=v===undefined?!open:v;document.getElementById("ccP").classList.toggle("open",open);if(open){refresh();setTimeout(()=>document.querySelector("#ccF textarea").focus(),50)}}
window.ChiefChat={open:()=>toggle(true),close:()=>toggle(false),ask:q=>{toggle(true);setTimeout(()=>send(q),200)},refresh};
if(document.readyState=="loading")document.addEventListener("DOMContentLoaded",mount);else mount();
})();

// "Recommended models" panel (wizard, Video studio). Data: GET /api/models; Test key: POST /api/models/test (keys stay in env, never sent to the page).
(function(){
const T={en:{title:"Recommended models",hint:"Prices are rough - always check the official pricing page. Keys are read from environment variables only.",video:"Video",tts:"Voice / TTS",best_quality:"Best quality",best_value:"Best value",free_draft:"Free / draft",docs:"API docs",key:"Get API key",price:"Pricing",env:"Env var",test:"Test key",ok:"key works",set:"set",unset:"not set",retired:"retired",checked:"checked",free:"free"},
"zh-CN":{title:"推荐模型",hint:"价格仅供粗略参考，请以官方定价页为准。密钥只从环境变量读取。",video:"视频",tts:"配音 / TTS",best_quality:"最佳画质",best_value:"最高性价比",free_draft:"免费 / 草稿",docs:"API 文档",key:"获取 API 密钥",price:"定价",env:"环境变量",test:"测试密钥",ok:"密钥可用",set:"已设置",unset:"未设置",retired:"已停用",checked:"核对日期",free:"免费"},
"zh-TW":{title:"推薦模型",hint:"價格僅供粗略參考，請以官方定價頁為準。金鑰只從環境變數讀取。",video:"影片",tts:"配音 / TTS",best_quality:"最佳畫質",best_value:"最高性價比",free_draft:"免費 / 草稿",docs:"API 文件",key:"取得 API 金鑰",price:"定價",env:"環境變數",test:"測試金鑰",ok:"金鑰可用",set:"已設定",unset:"未設定",retired:"已停用",checked:"核對日期",free:"免費"},
ja:{title:"おすすめモデル",hint:"価格は目安です。必ず公式の料金ページを確認してください。キーは環境変数からのみ読み込みます。",video:"動画",tts:"音声 / TTS",best_quality:"最高品質",best_value:"コスパ重視",free_draft:"無料 / 下書き",docs:"API ドキュメント",key:"API キー取得",price:"料金",env:"環境変数",test:"キーをテスト",ok:"キー有効",set:"設定済み",unset:"未設定",retired:"提供終了",checked:"確認日",free:"無料"},
es:{title:"Modelos recomendados",hint:"Los precios son aproximados: revisa siempre la página oficial de precios. Las claves solo se leen de variables de entorno.",video:"Vídeo",tts:"Voz / TTS",best_quality:"Mejor calidad",best_value:"Mejor relación calidad-precio",free_draft:"Gratis / borrador",docs:"Docs de la API",key:"Obtener clave",price:"Precios",env:"Variable",test:"Probar clave",ok:"la clave funciona",set:"configurada",unset:"sin configurar",retired:"retirado",checked:"revisado",free:"gratis"}};
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const a=(u,t)=>u?`<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a>`:"";
async function render(el,lang){const t=T[lang]||T[(lang||"").split("-")[0]]||T.en;let d;
 try{d=await (await fetch("/api/models")).json()}catch(e){el.textContent="";return}
 const row=e=>`<tr><td><b>${esc(e.provider)}</b><div class="dim">${esc(e.model)}${e.status=="retired"?` · <span class="err">${t.retired}</span>`:""}</div></td><td class="dim">${esc(e.good_at)}</td>
  <td>${a(e.docs,t.docs)}<br>${a(e.key_url,t.key)}<br>${a(e.pricing,t.price)}</td>
  <td><code>${esc((e.env||[]).join(" + ")||"-")}</code><div class="dim">${e.env&&e.env.length?(e.configured?"✓ "+t.set:t.unset):t.free}</div></td>
  <td>${e.env&&e.env.length&&e.status!="retired"?`<button class="ghost" data-test="${esc(e.id)}">${t.test}</button><div class="dim" data-out="${esc(e.id)}"></div>`:""}</td></tr>`;
 el.innerHTML=`<h3>${t.title}</h3><p class="dim">${t.hint} (${t.checked} ${esc(d.checked)})</p>`+["video","tts"].map(k=>`<h4>${t[k]}</h4><table class="models">`+
  Object.entries(d.tiers[k]).map(([tier,es])=>`<tr><th colspan="5">${t[tier]||tier}</th></tr>`+es.map(row).join("")).join("")+`</table>`).join("");
 el.querySelectorAll("[data-test]").forEach(b=>b.onclick=async()=>{const o=el.querySelector(`[data-out="${b.dataset.test}"]`);o.textContent="…";
  try{const r=await (await fetch("/api/models/test",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:b.dataset.test})})).json();
   o.className=r.ok?"ok":"err";o.textContent=r.ok?"✓ "+t.ok:"✕ "+(r.message||r.error||"")}catch(e){o.textContent="✕"}})}
window.SCModels={render,T};
})();

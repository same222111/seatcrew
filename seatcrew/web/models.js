// "Recommended models" cards (wizard step 3, Home, Video studio). Data: GET /api/models. Test key: POST /api/models/test.
// Keys are never sent to the page. On the Home window (window.SC_CAN_SAVE_KEYS) a key can be pasted once; it is written to the data folder's .env.
(function(){
const T={en:{title:"Recommended models",hint:"Prices are rough - always check the official pricing page.",video:"Video",tts:"Voice / TTS",best_quality:"Best quality",best_value:"Best value",free_draft:"Free / draft",docs:"Docs",key:"Get key",price:"Pricing",test:"Test key",ok:"Key works",set:"Key set",unset:"No key",retired:"Retired",checked:"checked",free:"Free · no key",
  paste:"Paste key",save:"Save",saved:"Saved - testing…",needKey:"Get a key, paste it here, then press Test.",needEnv:"Set {env} (Home → Recommended models, or the data folder's .env), then restart.",ready:"Ready to use",about:"≈ ${p} {u}"},
"zh-CN":{title:"推荐模型",hint:"价格仅供粗略参考,请以官方定价页为准。",video:"视频",tts:"配音 / TTS",best_quality:"最佳画质",best_value:"最高性价比",free_draft:"免费 / 草稿",docs:"文档",key:"获取密钥",price:"定价",test:"测试密钥",ok:"密钥可用",set:"已设置密钥",unset:"未设置密钥",retired:"已停用",checked:"核对日期",free:"免费 · 无需密钥",
  paste:"粘贴密钥",save:"保存",saved:"已保存,正在测试…",needKey:"先获取密钥,粘贴到这里,再点「测试密钥」。",needEnv:"设置 {env}(首页 → 推荐模型粘贴,或写进数据文件夹的 .env),然后重启。",ready:"可直接使用",about:"约 ${p} {u}"},
"zh-TW":{title:"推薦模型",hint:"價格僅供粗略參考,請以官方定價頁為準。",video:"影片",tts:"配音 / TTS",best_quality:"最佳畫質",best_value:"最高性價比",free_draft:"免費 / 草稿",docs:"文件",key:"取得金鑰",price:"定價",test:"測試金鑰",ok:"金鑰可用",set:"已設定金鑰",unset:"未設定金鑰",retired:"已停用",checked:"核對日期",free:"免費 · 免金鑰",
  paste:"貼上金鑰",save:"儲存",saved:"已儲存,正在測試…",needKey:"先取得金鑰,貼到這裡,再按「測試金鑰」。",needEnv:"設定 {env}(首頁 → 推薦模型貼上,或寫入資料夾的 .env),然後重新啟動。",ready:"可直接使用",about:"約 ${p} {u}"},
ja:{title:"おすすめモデル",hint:"価格は目安です。必ず公式の料金ページを確認してください。",video:"動画",tts:"音声 / TTS",best_quality:"最高品質",best_value:"コスパ重視",free_draft:"無料 / 下書き",docs:"ドキュメント",key:"キー取得",price:"料金",test:"キーをテスト",ok:"キー有効",set:"キー設定済み",unset:"キー未設定",retired:"提供終了",checked:"確認日",free:"無料 · キー不要",
  paste:"キーを貼り付け",save:"保存",saved:"保存しました - テスト中…",needKey:"キーを取得してここに貼り付け、テストを押してください。",needEnv:"{env} を設定(ホーム → おすすめモデル、またはデータフォルダの .env)して再起動。",ready:"すぐ使えます",about:"約 ${p} {u}"},
es:{title:"Modelos recomendados",hint:"Los precios son aproximados: revisa siempre la página oficial.",video:"Vídeo",tts:"Voz / TTS",best_quality:"Mejor calidad",best_value:"Mejor precio",free_draft:"Gratis / borrador",docs:"Docs",key:"Obtener clave",price:"Precios",test:"Probar clave",ok:"La clave funciona",set:"Clave configurada",unset:"Sin clave",retired:"Retirado",checked:"revisado",free:"Gratis · sin clave",
  paste:"Pegar clave",save:"Guardar",saved:"Guardada - probando…",needKey:"Consigue una clave, pégala aquí y pulsa Probar.",needEnv:"Configura {env} (Inicio → Modelos recomendados, o el .env de la carpeta de datos) y reinicia.",ready:"Listo para usar",about:"≈ ${p} {u}"}};
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const a=(u,t)=>u?`<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)} ↗</a>`:"";
async function post(p,b){return (await fetch(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)})).json()}
async function render(el,lang){const t=T[lang]||T[(lang||"").split("-")[0]]||T.en;let d;
 try{d=await (await fetch("/api/models")).json()}catch(e){el.textContent="";return}
 const I=d.i18n||{},loc=(k,id,en)=>((I[k]||{})[id]||{})[lang]||en,unit=u=>((I.units||{})[lang]||{})[u]||u;
 const canSave=!!window.SC_CAN_SAVE_KEYS;
 const card=e=>{const needs=e.env&&e.env.length,ret=e.status=="retired";
  const st=ret?`<span class="st ret">${t.retired}</span>`:!needs?`<span class="st free">${t.free}</span>`:e.configured?`<span class="st ok">✓ ${t.set}</span>`:`<span class="st no">${t.unset}</span>`;
  const price=e.rough_usd?`<span class="price">${t.about.replace("{p}",e.rough_usd).replace("{u}",esc(unit(e.unit)))}</span>`:"";
  let act="";
  if(needs&&!ret){
   act=`<div class="act"><button data-test="${esc(e.id)}" ${e.configured?"":"disabled"} title="${esc(e.configured?t.test:t.needKey)}">${t.test}</button><span class="out" data-out="${esc(e.id)}"></span></div>`;
   if(!e.configured) act+=canSave?`<div class="keyrow"><input type="password" autocomplete="off" spellcheck="false" placeholder="${esc(t.paste)} · ${esc(e.env[0])}" data-key="${esc(e.id)}"><button data-save="${esc(e.id)}">${t.save}</button></div><div class="hint-key">${esc(t.needKey)}</div>`
     :`<div class="hint-key">${esc(t.needEnv).replace("{env}",`<code>${esc(e.env[0])}</code>`)}</div>`;
  } else if(!ret) act=`<div class="hint-key ok">✓ ${t.ready}</div>`;
  return `<div class="mcard ${e.configured&&needs?"on":""} ${ret?"retired":""}"><div class="top"><div style="min-width:0"><div class="nm">${esc(loc("names",e.id,e.provider))}</div><div class="md">${esc(e.model)}</div></div>${st}</div>
   <div class="ds">${esc(loc("good_at",e.id,e.good_at))}</div>${price}<div class="links">${a(e.docs,t.docs)}${a(e.key_url,t.key)}${a(e.pricing,t.price)}</div>${act}</div>`};
 el.innerHTML=`<div class="mdl"><h3>${t.title}</h3><p class="mhint">${t.hint} <span style="white-space:nowrap">(${t.checked} ${esc(d.checked)})</span></p>`+["video","tts"].map(k=>`<div class="kind">${t[k]}</div>`+
  Object.entries(d.tiers[k]).map(([tier,es])=>`<div class="tier ${tier}"><i>${t[tier]||tier}</i></div><div class="mgrid">${es.map(card).join("")}</div>`).join("")).join("")+`</div>`;
 const test=async id=>{const o=el.querySelector(`[data-out="${id}"]`);o.className="out dim";o.textContent="…";
  try{const r=await post("/api/models/test",{id});o.className="out "+(r.ok?"ok":"err");o.textContent=r.ok?"✓ "+t.ok:"✕ "+(r.message||r.error||"")}catch(e){o.className="out err";o.textContent="✕"}};
 el.querySelectorAll("[data-test]").forEach(b=>b.onclick=()=>test(b.dataset.test));
 el.querySelectorAll("[data-save]").forEach(b=>b.onclick=async()=>{const id=b.dataset.save,inp=el.querySelector(`[data-key="${id}"]`),v=inp.value.trim();if(!v){inp.focus();return}
  b.disabled=true;const r=await post("/api/models/key",{id,value:v});inp.value="";
  if(!r.ok){b.disabled=false;const h=b.parentElement.nextElementSibling;h.className="hint-key err";h.textContent="✕ "+(r.error||"");return}
  await render(el,lang);test(id)});
 el.querySelectorAll("[data-key]").forEach(i=>i.onkeydown=e=>{if(e.key=="Enter")el.querySelector(`[data-save="${i.dataset.key}"]`).click()})}
window.SCModels={render,T};
})();

/* Video studio panel for workflows with definition.studio == "video": item picker, preview player, storyboard,
   quality report, download. Draft output is always labeled "Draft preview - not final quality". */
(()=>{const css=`.studio{padding:14px;margin-top:0}.studio .pick{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}.studio .pick button{border:1px solid var(--ln);background:var(--pn2);color:var(--fg);border-radius:8px;padding:4px 10px;cursor:pointer;font:600 12px var(--sans)}
.studio .pick button.sel{border-color:var(--acc);box-shadow:0 0 10px #3dffa044}.studio .pick button .d{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;background:var(--dim)}
.studio .pick button.ok .d{background:var(--acc)}.studio .pick button.bad .d{background:var(--bad)}.studio .pick button.wait .d{background:var(--warn)}
.studio .sg{display:grid;grid-template-columns:minmax(240px,360px) minmax(0,1fr);gap:16px;align-items:start}@media(max-width:760px){.studio .sg{grid-template-columns:1fr}}
.studio .pl{position:relative;background:#000;border:1px solid var(--ln);border-radius:12px;overflow:hidden;display:grid;place-items:center;min-height:200px}
.studio video{width:100%;max-height:520px;display:block;background:#000}.studio .ph{color:var(--dim);padding:30px 14px;text-align:center;font-size:12px}
.studio .draft{background:#ff2d55;color:#fff;font:800 12px var(--sans);letter-spacing:.08em;text-align:center;padding:6px 8px;border-radius:8px;margin-bottom:8px}
.studio .final{border:1px solid var(--acc);color:var(--acc);font:700 11px var(--sans);letter-spacing:.08em;text-align:center;padding:4px;border-radius:8px;margin-bottom:8px}
.studio table{font-size:12px;width:100%}.studio td{vertical-align:top}.studio th{white-space:nowrap}.studio .sbt td.n{min-width:14em}.studio .sbt td.c{min-width:8em}.studio .sbt td.mono{white-space:nowrap}
.studio .bk{font-size:10px;border:1px solid var(--ln);border-radius:5px;padding:0 5px;white-space:nowrap}.studio .bk.draft{background:none;color:#ff2d55;border-color:#ff2d55;padding:0 5px;font-size:10px;margin:0}
.studio .bk.final{color:var(--acc);border-color:#3dffa077;padding:0 5px;margin:0;font-size:10px}.studio h4{margin:14px 0 6px;font:700 11px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
:lang(zh) .studio h4,:lang(ja) .studio h4,:lang(zh) .studio .draft{letter-spacing:0;text-transform:none;font-family:var(--sans);font-size:12.5px}
.studio .qc{display:grid;grid-template-columns:18px max-content max-content minmax(0,1fr);gap:4px 10px;font-size:12px;align-items:baseline}.studio .qc b,.studio .qc .s{white-space:nowrap}.studio .qc .s{font-size:10px;color:var(--blue)}
.studio .sum{font:700 12px var(--sans);margin:4px 0}.studio .sum.pass{color:var(--acc)}.studio .sum.fail{color:var(--bad)}.studio .tiers{font-size:11px;color:var(--dim);margin-top:8px;line-height:1.5}
.studio .vstats{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 10px}.studio .vstats div{flex:1 1 90px;border:1px solid var(--ln);border-radius:10px;padding:4px 10px;background:var(--pn2);display:flex;gap:8px;align-items:baseline}.studio .vstats b{font:800 17px var(--sans)}.studio .vstats span{font-size:12px;color:var(--dim);white-space:nowrap}
.studio .apbar{margin-top:10px;border:1px solid var(--warn);background:#ffc94d12;border-radius:12px;padding:10px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}.studio .apbar b{flex:1 1 100%;color:var(--warn)}
.studio .apbar input{flex:1 1 140px;min-width:0}.studio .apbar button{border:0;border-radius:9px;padding:8px 16px;font:750 14px var(--sans);cursor:pointer;background:var(--acc);color:#04140a;white-space:nowrap}.studio .apbar button.no{background:none;border:1px solid var(--bad);color:var(--bad)}
.studio .vst{font:700 13px var(--sans);margin:0 0 8px}.studio .vst.bad{color:var(--bad)}.studio .vst.wait{color:var(--warn)}.studio .vst.ok{color:var(--acc)}
.studio .steps{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}.studio .steps span{border:1px solid var(--ln);border-radius:999px;padding:2px 10px;font-size:12px;white-space:nowrap;color:var(--dim)}.studio .steps span.ok{border-color:#3dffa077;color:var(--acc)}.studio .steps span.bad{border-color:var(--bad);color:var(--bad)}
.studio .tip{border:1px solid var(--blue);background:#5cc8ff12;border-radius:10px;padding:8px 10px;font-size:13px;margin:8px 0}
body.vstudio .dgrid{grid-template-columns:minmax(270px,340px) minmax(0,1fr)}body.vstudio .dgrid>aside,body.vstudio .dgrid>.right,body.vstudio .tiles,body.vstudio #detail,body.vstudio #whoCard,body.vstudio #chips,body.vstudio .hero-stats,body.vstudio .mascot,body.vstudio .tagline,body.vstudio .hero-chip,body.vstudio #dash>.hero,body.vstudio .pn:has(>#items){display:none!important}
body.vstudio .vleft>*{margin-top:0;margin-bottom:12px}body.vstudio .hero{padding-top:8px;padding-bottom:8px;min-height:0}
body.vstudio .flowcard{padding:8px 12px}body.vstudio .flow{max-height:110px;aspect-ratio:auto;height:110px}body.vstudio .studio video{max-height:250px}body.vstudio .studio .pick{margin-bottom:6px}body.vstudio .studio .draft{padding:4px 8px;margin-bottom:6px}.studio .vstats div{flex:1 1 70px}@media(max-width:520px){body.vstudio #flowPath{display:none}body.vstudio .flow{height:96px}.studio .vstats b{font-size:16px}}
@media(max-width:900px){body.vstudio .dgrid{grid-template-columns:minmax(0,1fr)}body.vstudio .vleft{order:2}}
.tab>.studio{margin-top:0}`;
const st=document.createElement('style');st.textContent=css;document.head.appendChild(st);
const L=(k,d)=>(LOC&&LOC[k])||d;
// Layout: left = new-video form + log; right = flow, player with the approve bar under it, full-width storyboard + quality report.
document.body.classList.add('vstudio');
const dg=document.querySelector('.dgrid'),vleft=document.createElement('div');vleft.className='vleft';
['submitPn'].forEach(i=>{const e=document.getElementById(i);if(e)vleft.appendChild(e)});const term=document.querySelector('.dgrid .term');if(term)vleft.appendChild(term);
dg.insertBefore(vleft,dg.firstChild);
// Model list and voice library get their own tabs instead of stacking under the player.
const nav=document.querySelector('nav'),mainEl=document.getElementById('dash').parentNode;
[['tmodels','nav_models','Models'],['tvoices','nav_voices','Voices']].forEach(([id,k,d])=>{const sec=document.createElement('section');sec.id=id;sec.className='tab';mainEl.appendChild(sec);
 const b=document.createElement('button');b.dataset.t=id;b.dataset.vnav=k;b.textContent=L(k,d);const ref=nav.querySelector('[data-t=set]');nav.insertBefore(b,ref)});
if(window.bindNav)bindNav();else nav.querySelectorAll('[data-vnav]').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button,.tab').forEach(x=>x.classList.remove('act'));b.classList.add('act');document.getElementById(b.dataset.t).classList.add('act')});
const box=document.createElement('div');box.className='nx-card studio';box.id='studio';
const anchor=document.querySelector('.flowcard');anchor.parentNode.insertBefore(box,anchor.nextSibling);
let SEL=null,SIG='';
const cls=it=>it.status=='done'||it.status=='filled'?'ok':String(it.status||'').startsWith('blocked')?'bad':'wait';
const fmt=t=>(+t||0).toFixed(1)+'s';const SNm=k=>L('sn_'+k,String(k).toUpperCase());
const STEPS=['writer','scriptcheck','voice','visuals','lipsync','editor','qc'];
function vstatus(it){const s=String(it.status||'');const bl=(it.chain||[]).find(c=>!c.ok);
 if(it.pending!=null)return['wait',L('st_waiting','Waiting for you to approve')];
 if(bl||s.startsWith('blocked'))return['bad',L('st_blocked','Stopped at {s}').replace('{s}',SNm(bl?bl.seat:s.replace(/^blocked:?/,'')))];
 if(s=='done'||s=='filled')return['ok',L('st_done','Done')];
 if(s=='new'||!s)return['',L('st_new','Queued')];return['',L('st_working','In production…')]}
function title(){const t=L('wf_title','');if(!t)return;['title','heroTitle','crumbWf'].forEach(i=>{const e=document.getElementById(i);if(e&&e.textContent!=t)e.textContent=t});document.title=t+' · SeatCrew'}
function render(s){title();document.querySelectorAll('[data-vnav]').forEach(b=>b.textContent=L(b.dataset.vnav,b.textContent));
 const vids=(s.items||[]).filter(i=>i.data&&i.data.topic);if(!SEL||!vids.find(i=>i.id==SEL))SEL=(vids.find(i=>i.pending!=null)||vids[0]||{}).id;
 const it=vids.find(i=>i.id==SEL);const sig=JSON.stringify([LOC.app_sub,LOC.wf_title,vids.map(i=>[i.id,i.status,i.pending]),it&&[it.data.video,it.data.qc&&it.data.qc.summary,it.data.storyboard&&it.data.storyboard.shots.length,it.data.rounds,it.data.tip,it.data.steps]]);if(sig==SIG)return;
 if(box.contains(document.activeElement)&&document.activeElement.tagName=='INPUT')return;SIG=sig;
 const K=(DEF&&DEF.keys)||{};const keys=Object.entries(K).map(([k,v])=>`<span class="bk" style="color:${v?'var(--acc)':'var(--dim)'}">${k}${v?' ✓':''}</span>`).join(' ');
 let h=`<div class="nx-h"><span>▶ ${L('studio_title','Video studio')}</span><span class="qm" title="${esc(L('studio_hint','Each video walks six seats: director, writer, script check, production (voice + visuals + lip-sync), edit + quality check, then you approve.'))}">?</span><a class="b sm" href="/characters" style="margin-left:auto;text-decoration:none">◆ ${L('cs_title','Character Studio')}</a><span class="adv">${keys}</span></div>`;
 const n=c=>vids.filter(i=>cls(i)==c&&(c!='wait'||i.pending==null)).length;
 h+=`<div class="vstats" id="vtiles"><div><b>${n('wait')}</b><span>${esc(L('v_tile_making','In production'))}</span></div><div><b>${vids.filter(i=>i.pending!=null).length}</b><span>${esc(L('v_tile_wait','Waiting for you'))}</span></div><div><b>${n('ok')}</b><span>${esc(L('v_tile_done','Done'))}</span></div><div><b>${n('bad')}</b><span>${esc(L('v_tile_blocked','Stopped'))}</span></div></div>`;
 if(!vids.length){box.innerHTML=h+`<div class="ph">${esc(L('studio_empty','No videos yet. Type a topic in "New item" (left) and press Submit.'))}</div><div class="tiers">${esc(L('studio_tiers',''))}</div>`;return}
 h+=`<div class="pick">${vids.slice(0,12).map(i=>`<button data-v="${i.id}" class="${cls(i)} ${i.id==SEL?'sel':''}"><span class="d"></span>#${i.id} ${esc(String(i.data.topic).slice(0,28))}</button>`).join('')}</div>`;
 const d=it.data,v=d.video,sb=d.storyboard,qc=d.qc,draft=v?v.draft:(d.voice&&d.voice.draft)||(d.visuals&&d.visuals.draft);
 let left='';if(draft)left+=`<div class="draft">⚠ ${esc(L('draft_label','DRAFT PREVIEW - NOT FINAL QUALITY'))}</div>`;else if(v&&qc&&qc.passed)left+=`<div class="final">✓ ${esc(L('final_ok','Final backends · quality check passed'))}</div>`;
 left+=`<div class="pl">${v?`<video controls playsinline preload="metadata" src="/media/${it.id}/${v.file}?t=${encodeURIComponent(qc?qc.summary.length:0)}"></video>`:`<div class="ph">${esc(L('no_video_yet','The video appears here after the edit step.'))}</div>`}</div>`;
 if(it.pending!=null)left+=`<div class="apbar" id="apbar"><b>${esc(L('v_approve_q','Publish this video?'))}</b><input id="vnote" placeholder="${esc(T('note'))}"><button data-vok>✓ ${esc(T('approve'))}</button><button class="no" data-vno>✕ ${esc(L('v_reject','Send back'))}</button></div>`;
 if(v)left+=`<div class="row" style="margin-top:8px"><a class="b" style="text-decoration:none;padding:5px 12px;border-radius:7px;border:1px solid var(--acc);color:var(--acc)" href="/media/${it.id}/${v.file}?download=1" download>⬇ ${esc(L('download','Download'))} ${v.size?v.size.join('×'):''}</a><span class="dim">${fmt(v.total)}</span></div>
  ${draft?`<div class="dim" style="font-size:11px">${esc(L('draft_hint','Made offline with a draft voice and/or title cards. Connect a voice and visuals backend, or add your own clips, for final quality.'))}</div>`:''}`;
 const [vc,vt]=vstatus(it);let right=`<div class="vst ${vc}">${esc(vt)}</div>`;const S=d.steps||{};
 right+=`<div class="steps">${STEPS.map(k=>{const x=S[k];const c=x?(x.ok===false?'bad':'ok'):(k=='writer'&&(d.script||sb))||(k=='scriptcheck'&&sb&&(d.voice||d.visuals))?'ok':'';return `<span class="${c}">${c=='ok'?'✓ ':c=='bad'?'✕ ':''}${esc(L('step_'+k,k))}${d.rounds&&d.rounds[k]?' ×'+(d.rounds[k]+1):''}</span>`}).join('')}</div>`;
 if(d.tip)right+=`<div class="tip">💡 ${esc(d.tip)}</div>`;
 const bl=(it.chain||[]).find(c=>!c.ok);if(bl)right+=`<div class="tip" style="border-color:var(--bad)">✕ ${esc(SNm(bl.seat))}: ${esc(bl.reason_l||bl.reason)}</div>`;
 if(d.voice)right+=`<div class="dim" style="margin-top:6px">${L('voice_lbl','voice')}: <span class="bk ${d.voice.draft?'draft':'final'}">${esc(d.voice.backend.join('/'))}</span> ${esc(d.voice.voice||'')} · ${L('sync_lbl','word timing')}: ${esc(d.voice.sync)}</div>`;
 let wide='';
 if(sb){wide+=`<h4>${esc(L('storyboard','Storyboard'))} · ${sb.shots.length} · ${esc(L('opt_'+d.template,d.template||''))} · ${esc(d.aspect||'')}</h4><div style="overflow-x:auto"><table class="sbt"><tr><th>#</th><th>${L('col_time','time')}</th><th class="adv">${L('col_camera','camera')}</th><th class="adv">${L('col_trans','transition')}</th><th>${L('col_narr','narration')}</th><th>${L('col_caption','caption')}</th><th>${L('col_visual','visual')}</th></tr>`+
  sb.shots.map((x,i)=>{const tl=(d.timeline||[])[i];const vi=x.visual_info||{};return `<tr><td class="acc">${x.id}</td><td class="mono">${tl?fmt(tl.start)+' +'+fmt(tl.dur):fmt(x.duration)}</td><td class="adv">${x.camera}</td><td class="adv">${x.transition}</td><td class="n">${esc(x.narration)}</td><td class="c">${esc(x.caption)}</td>
  <td>${vi.backend?`<span class="bk ${vi.backend=='draft'?'draft':'final'}">${esc(vi.backend)}</span> `:''}<span class="dim adv" title="${esc(x.visual)}">${esc(String(x.visual).slice(0,50))}</span>${tl&&tl.src&&tl.src!='0x0'?` <span class="dim adv">${tl.src}</span>`:''}</td></tr>`}).join('')+`</table></div>`}
 if(qc){wide+=`<h4>${esc(L('qc_report','Quality report'))}${d.rounds&&Object.keys(d.rounds).length?' · '+esc(L('rounds','rework'))+': '+Object.entries(d.rounds).map(([k,n])=>L('step_'+k,k)+'×'+n).join(' '):''}</h4><div class="sum ${qc.passed?'pass':'fail'}">${esc(qc.summary_l||qc.summary)}</div><div class="qc">`+
  qc.checks.map(c=>`<span class="${c.ok?'good':c.severity=='fail'?'bad':'warn'}">${c.ok?'✓':c.severity=='fail'?'✕':'⚠'}</span><b>${esc(c.name_l||L('qc_'+c.name,c.name))}</b><span class="s">${esc(L('step_'+c.seat,c.seat))}</span><span class="dim">${esc(c.detail_l||c.detail)}</span>`).join('')+`</div>`}
 box.innerHTML=h+`<div class="sg"><div>${left}</div><div style="min-width:0">${right}</div></div>${wide}`;
 box.querySelectorAll('[data-v]').forEach(b=>b.onclick=()=>{SEL=+b.dataset.v;SIG='';render(window.__ST||s)});
 const act=async ok=>{await post('/api/decide',{id:it.id,approve:ok,pending:it.pending,note:(document.getElementById('vnote')||{}).value||''});SIG='';poll()};
 const ok=box.querySelector('[data-vok]'),no=box.querySelector('[data-vno]');if(ok)ok.onclick=()=>act(true);if(no)no.onclick=()=>act(false)}
async function poll(){try{const s=await get('/api/state');window.__ST=s;render(s)}catch(e){}}
window.addEventListener('seatcrew:lang',()=>{SIG='';setTimeout(poll,50)});
poll();setInterval(poll,2500)})();

/* Character voice library: one persistent voice per character, curated presets, audition. */
(()=>{const L=(k,d)=>(LOC&&LOC[k])||d;const vb=document.createElement('div');vb.className='nx-card studio';vb.id='voices';
document.getElementById('tvoices').appendChild(vb);let V=null,SIGV='',EDIT=null;
const plbl=p=>`${p.lang} · ${L('vk_'+p.kind,p.kind)}`;const sel=(n,opts,v,lab)=>`<select data-vf="${n}">${opts.map(o=>`<option value="${esc(o)}" ${o==v?'selected':''}>${esc(lab?lab(o):o)}</option>`).join('')}</select>`;
let AUD=null;async function play(body,btn){try{btn&&(btn.disabled=true);const r=await fetch('/api/voices/audition',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!r.ok){const j=await r.json().catch(()=>({}));alert(j.error||r.status);return}const u=URL.createObjectURL(await r.blob());if(AUD)AUD.pause();AUD=new Audio(u);AUD.play()}finally{btn&&(btn.disabled=false)}}
function form(c,name){c=c||{};const ps=V.presets.filter(p=>p.lang==V.lang).concat(V.presets.filter(p=>p.lang!=V.lang));
 return `<div class="row" style="flex-wrap:wrap;gap:6px;align-items:center"><input data-vf="name" placeholder="${esc(L('v_name','Character name'))}" value="${esc(name||'')}" ${name?'readonly':''} style="width:120px">
 <select data-vf="preset"><option value="">${esc(L('v_keep','(keep voice)'))}</option>${ps.map(p=>`<option value="${p.id}" ${p.id==c.preset?'selected':''}>${esc(plbl(p))} · ${esc(p.voice.replace(/^\w+-\w+-|Neural$/g,''))}</option>`).join('')}</select>
 <input data-vf="description" placeholder="${esc(L('v_desc','who is this? (age, mood)'))}" value="${esc(c.description||'')}" style="width:200px">
 ${sel('style',V.styles,c.style||'neutral',o=>L('st_'+o,o))} <label class="dim">${L('v_rate','rate')}</label><input data-vf="rate" type=number min=-50 max=50 value="${c.rate||0}" style="width:56px">%
 <label class="dim">${L('v_pitch','pitch')}</label><input data-vf="pitch" type=number min=-50 max=50 value="${c.pitch||0}" style="width:56px">Hz
 <label class="dim">${L('v_volume','volume')}</label><input data-vf="volume" type=number min=-50 max=50 value="${c.volume||0}" style="width:56px">%
 <input data-vf="color" type=color value="${c.color||'#FFE500'}" title="${esc(L('v_color','subtitle color'))}">
 <span class="adv">${sel('backend',V.backends,c.backend||'auto',o=>L('opt_'+o,o))} ${sel('openai_voice',['',...V.openai_voices],c.openai_voice||'')} <input data-vf="elevenlabs_voice" placeholder="ElevenLabs voice id" value="${esc(c.elevenlabs_voice||'')}" style="width:150px"></span>
 <button class="b" data-vact="tryp">▶ ${esc(L('v_play','Audition'))}</button><button class="b" data-vact="save">${esc(L('v_save','Save'))}</button>${name?`<button class="b" data-vact="cancel">✕</button>`:''}</div>`}
function render(){if(!V)return;const sig=JSON.stringify([LOC.app_sub,V.characters,EDIT]);if(sig==SIGV)return;SIGV=sig;const C=V.characters;
 let h=`<div class="nx-h"><span>🎙 ${esc(L('voices_title','Character voices'))}</span><span class="qm" title="${esc(L('voices_hint','Each character keeps one voice in every shot and every future video. Tag storyboard lines with speaker: and emotion:.'))}">?</span></div>`;
 h+=Object.keys(C).length?`<table><tr><th>${L('v_name','Character')}</th><th>${L('v_voice','voice')}</th><th>${L('v_style','style')}</th><th></th></tr>`+Object.entries(C).map(([n,c])=>EDIT==n?`<tr><td colspan=4>${form(c,n)}</td></tr>`:
  `<tr><td><span style="color:${esc(c.color||'var(--fg)')}">●</span> <b>${esc(n)}</b><div class="dim">${esc(c.description||'')}</div></td><td class="mono">${esc(c.voice)} ${c.rate>=0?'+':''}${c.rate}% ${c.pitch>=0?'+':''}${c.pitch}Hz${c.volume?` vol ${c.volume}%`:''} <span class="dim adv">[${esc(c.backend)}${c.openai_voice?' · openai '+esc(c.openai_voice):''}${c.elevenlabs_voice?' · 11labs':''}]</span></td>
  <td>${esc(L('st_'+c.style,c.style))}</td><td style="white-space:nowrap"><button class="b" data-vplay="${esc(n)}">▶</button> <button class="b" data-vedit="${esc(n)}">✎</button> <button class="b" data-vdel="${esc(n)}">🗑</button></td></tr>`).join('')+`</table>`
  :`<div class="ph">${esc(L('v_empty','No characters yet. Add one below, e.g. narrator, 林晚, 妈妈.'))}</div>`;
 h+=`<h4>${esc(L('v_add','Add character'))}</h4>${EDIT?'':form({},'')}`;vb.innerHTML=h;
 const val=root=>{const o={};root.querySelectorAll('[data-vf]').forEach(e=>o[e.dataset.vf]=e.type=='number'?+e.value:e.value);if(!o.preset)delete o.preset;return o};
 vb.querySelectorAll('[data-vact]').forEach(b=>b.onclick=async()=>{const row=b.closest('.row'),o=val(row);
  if(b.dataset.vact=='cancel'){EDIT=null;SIGV='';return render()}
  if(b.dataset.vact=='tryp'){if(o.preset&&!(EDIT&&!o.preset))return play({preset:o.preset},b);if(o.name&&C[o.name])return play({name:o.name},b);return}
  const r=await post('/api/voices/set',o);if(r.ok===false){alert(r.error);return}EDIT=null;await load()});
 vb.querySelectorAll('[data-vplay]').forEach(b=>b.onclick=()=>play({name:b.dataset.vplay},b));
 vb.querySelectorAll('[data-vedit]').forEach(b=>b.onclick=()=>{EDIT=b.dataset.vedit;render()});
 vb.querySelectorAll('[data-vdel]').forEach(b=>b.onclick=async()=>{if(!confirm(L('v_confirm_del','Delete this character voice?')))return;await post('/api/voices/delete',{name:b.dataset.vdel});await load()})}
async function load(){try{V=await get('/api/voices');SIGV='';render()}catch(e){}}
window.addEventListener('seatcrew:lang',()=>setTimeout(load,100));
load();setInterval(()=>{if(!EDIT&&!vb.contains(document.activeElement))load()},10000);setInterval(render,1500)})();
// Recommended models panel (video + voice tiers, docs / key / pricing links, Test key)
(()=>{const mb=document.createElement('div');mb.className='nx-card studio';mb.id='models';document.getElementById('tmodels').appendChild(mb);let lang='';
 const go=async()=>{if(!window.SCModels){const s=document.createElement('script');s.src='/models.js';s.onload=go;document.body.appendChild(s);return}
  const l=(await fetch('/api/voices').then(r=>r.json()).catch(()=>({}))).lang||'en';if(l!=lang){lang=l;SCModels.render(mb,l)}};
 go();setInterval(go,15000);window.addEventListener('seatcrew:lang',()=>setTimeout(go,100))})();

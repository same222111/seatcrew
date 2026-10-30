/* Video studio panel for workflows with definition.studio == "video": item picker, preview player, storyboard,
   quality report, download. Draft output is always labeled "Draft preview - not final quality". */
(()=>{const css=`.studio{padding:14px;margin-top:0}.studio .pick{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}.studio .pick button{border:1px solid var(--ln);background:var(--pn2);color:var(--fg);border-radius:8px;padding:4px 10px;cursor:pointer;font:600 12px var(--sans)}
.studio .pick button.sel{border-color:var(--acc);box-shadow:0 0 10px #3dffa044}.studio .pick button .d{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;background:var(--dim)}
.studio .pick button.ok .d{background:var(--acc)}.studio .pick button.bad .d{background:var(--bad)}.studio .pick button.wait .d{background:var(--warn)}
.studio .sg{display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);gap:14px}@media(max-width:900px){.studio .sg{grid-template-columns:1fr}}
.studio .pl{position:relative;background:#000;border:1px solid var(--ln);border-radius:12px;overflow:hidden;display:grid;place-items:center;min-height:200px}
.studio video{width:100%;max-height:540px;display:block;background:#000}.studio .ph{color:var(--dim);padding:30px 14px;text-align:center;font-size:12px}
.studio .draft{background:#ff2d55;color:#fff;font:800 12px var(--sans);letter-spacing:.08em;text-align:center;padding:6px 8px;border-radius:8px;margin-bottom:8px}
.studio .final{border:1px solid var(--acc);color:var(--acc);font:700 11px var(--sans);letter-spacing:.08em;text-align:center;padding:4px;border-radius:8px;margin-bottom:8px}
.studio table{font-size:11.5px}.studio td{vertical-align:top}.studio .bk{font-size:10px;border:1px solid var(--ln);border-radius:5px;padding:0 5px;white-space:nowrap}.studio .bk.draft{background:none;color:#ff2d55;border-color:#ff2d55;padding:0 5px;font-size:10px;margin:0}
.studio .bk.final{color:var(--acc);border-color:#3dffa077;padding:0 5px;margin:0;font-size:10px}.studio h4{margin:12px 0 6px;font:700 11px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.studio .qc{display:grid;grid-template-columns:18px 120px 70px 1fr;gap:3px 8px;font-size:11.5px;align-items:baseline}.studio .qc .s{font-size:10px;color:var(--blue);text-transform:uppercase}
.studio .sum{font:700 12px var(--sans);margin:4px 0}.studio .sum.pass{color:var(--acc)}.studio .sum.fail{color:var(--bad)}.studio .tiers{font-size:11px;color:var(--dim);margin-top:8px;line-height:1.5}`;
const st=document.createElement('style');st.textContent=css;document.head.appendChild(st);
const box=document.createElement('div');box.className='nx-card studio';box.id='studio';
const anchor=document.querySelector('.flowcard');anchor.parentNode.insertBefore(box,anchor.nextSibling);
const L=(k,d)=>(LOC&&LOC[k])||d;let SEL=null,SIG='';
const cls=it=>it.status=='done'||it.status=='filled'?'ok':String(it.status||'').startsWith('blocked')?'bad':'wait';
const fmt=t=>(+t||0).toFixed(1)+'s';
function render(s){const vids=(s.items||[]).filter(i=>i.data&&i.data.topic);if(!SEL||!vids.find(i=>i.id==SEL))SEL=vids[0]&&vids[0].id;
 const it=vids.find(i=>i.id==SEL);const sig=JSON.stringify([LOC.app_sub,vids.map(i=>[i.id,i.status]),it&&[it.data.video,it.data.qc&&it.data.qc.summary,it.data.storyboard&&it.data.storyboard.shots.length,it.data.rounds]]);if(sig==SIG)return;SIG=sig;
 const K=(DEF&&DEF.keys)||{};const keys=Object.entries(K).map(([k,v])=>`<span class="bk" style="color:${v?'var(--acc)':'var(--dim)'}">${k}${v?' ✓':''}</span>`).join(' ');
 let h=`<div class="nx-h"><span>▶ ${L('studio_title','Video studio')}</span><span class="qm" title="${esc(L('studio_hint','Each video walks the seats: script, check, voice, visuals, edit, automated quality check, then you approve.'))}">?</span><span style="margin-left:auto" class="adv">${keys}</span></div>`;
 if(!vids.length){box.innerHTML=h+`<div class="ph">${esc(L('studio_empty','No videos yet. Type a topic in "New item" (right) and press Submit.'))}</div><div class="tiers">${esc(L('studio_tiers',''))}</div>`;return}
 h+=`<div class="pick">${vids.slice(0,12).map(i=>`<button data-v="${i.id}" class="${cls(i)} ${i.id==SEL?'sel':''}"><span class="d"></span>#${i.id} ${esc(String(i.data.topic).slice(0,28))}</button>`).join('')}</div>`;
 const d=it.data,v=d.video,sb=d.storyboard,qc=d.qc,draft=v?v.draft:(d.voice&&d.voice.draft)||(d.visuals&&d.visuals.draft);
 let left='';if(draft)left+=`<div class="draft">⚠ ${esc(L('draft_label','DRAFT PREVIEW - NOT FINAL QUALITY'))}</div>`;else if(v&&qc&&qc.passed)left+=`<div class="final">✓ ${esc(L('final_ok','Final backends · quality check passed'))}</div>`;
 left+=`<div class="pl">${v?`<video controls playsinline preload="metadata" src="/media/${it.id}/${v.file}?t=${encodeURIComponent(qc?qc.summary.length:0)}"></video>`:`<div class="ph">${esc(L('no_video_yet','The video appears here after the EDITOR seat.'))}<br><br>${esc(it.status||'')}</div>`}</div>`;
 if(v)left+=`<div class="row" style="margin-top:8px"><a class="b" style="text-decoration:none;padding:5px 12px;border-radius:7px;border:1px solid var(--acc);color:var(--acc)" href="/media/${it.id}/${v.file}?download=1" download>⬇ ${esc(L('download','Download'))} ${v.size?v.size.join('×'):''}</a><span class="dim">${fmt(v.total)}</span></div>
  ${draft?`<div class="dim" style="font-size:11px">${esc(L('draft_hint','Made offline with a draft voice and/or title cards. Connect a voice and visuals backend, or add your own clips, for final quality.'))}</div>`:''}`;
 let right='';
 if(sb){right+=`<h4>${esc(L('storyboard','Storyboard'))} · ${sb.shots.length} · ${esc(L('opt_'+d.template,d.template||''))} · ${esc(d.aspect||'')}</h4><table><tr><th>#</th><th>${L('col_time','time')}</th><th class="adv">${L('col_camera','camera')}</th><th class="adv">${L('col_trans','transition')}</th><th>${L('col_narr','narration')}</th><th>${L('col_caption','caption')}</th><th>${L('col_visual','visual')}</th></tr>`+
  sb.shots.map((x,i)=>{const tl=(d.timeline||[])[i];const vi=x.visual_info||{};return `<tr><td class="acc">${x.id}</td><td class="mono">${tl?fmt(tl.start)+' +'+fmt(tl.dur):fmt(x.duration)}</td><td class="adv">${x.camera}</td><td class="adv">${x.transition}</td><td>${esc(x.narration)}</td><td>${esc(x.caption)}</td>
  <td>${vi.backend?`<span class="bk ${vi.backend=='draft'?'draft':'final'}">${esc(vi.backend)}</span> `:''}<span class="dim adv" title="${esc(x.visual)}">${esc(String(x.visual).slice(0,50))}</span>${tl&&tl.src&&tl.src!='0x0'?` <span class="dim adv">${tl.src}</span>`:''}</td></tr>`}).join('')+`</table>`}
 if(d.voice)right+=`<div class="dim" style="margin-top:6px">${L('voice_lbl','voice')}: <span class="bk ${d.voice.draft?'draft':'final'}">${esc(d.voice.backend.join('/'))}</span> ${esc(d.voice.voice||'')} · ${L('sync_lbl','word timing')}: ${esc(d.voice.sync)}</div>`;
 if(qc){right+=`<h4>${esc(L('qc_report','Quality report'))}${d.rounds&&Object.keys(d.rounds).length?' · '+esc(L('rounds','rework'))+': '+Object.entries(d.rounds).map(([k,n])=>k.toUpperCase()+'×'+n).join(' '):''}</h4><div class="sum ${qc.passed?'pass':'fail'}">${esc(qc.summary)}</div><div class="qc">`+
  qc.checks.map(c=>`<span class="${c.ok?'good':c.severity=='fail'?'bad':'warn'}">${c.ok?'✓':c.severity=='fail'?'✕':'⚠'}</span><b>${esc(L('qc_'+c.name,c.name))}</b><span class="s">${c.seat}</span><span class="dim">${esc(c.detail)}</span>`).join('')+`</div>`}
 if(!sb&&!qc)right+=`<div class="ph">${esc(it.status||'')}</div>`;
 box.innerHTML=h+`<div class="sg"><div>${left}</div><div style="min-width:0;overflow:auto">${right}</div></div>`;
 box.querySelectorAll('[data-v]').forEach(b=>b.onclick=()=>{SEL=+b.dataset.v;SIG='';render(window.__ST||s)})}
async function poll(){try{const s=await get('/api/state');window.__ST=s;render(s)}catch(e){}}
poll();setInterval(poll,2500)})();

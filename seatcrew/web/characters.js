/* Character Studio page. */
let LOC={},S=null,CUR=null,TAB='gallery',WIZ={step:1,photos:[]},CAST={name:'',members:[null,null,null,null,null],plot:'',set_sheet:''};
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const T=(k,v)=>{let s=LOC[k]??k;for(const x in v||{})s=s.replace('{'+x+'}',v[x]);return s};
const get=u=>fetch(u).then(r=>r.json());
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});const ct=r.headers.get('content-type')||'';return ct.includes('audio')?r.blob():r.json()}
function toast(m,bad){const t=$('toast');t.textContent=m;t.style.borderColor=bad?'var(--bad)':'var(--acc)';t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',3500)}
const qm=k=>`<span class="qm" title="${esc(T(k))}">?</span>`;
async function setLang(l){LOC=await get('/api/locale/'+l);document.documentElement.lang=l;document.querySelectorAll('[data-i18n]').forEach(e=>e.textContent=T(e.dataset.i18n));render()}
async function boot(){const c=await get('/api/config');const langs=c.languages||['en'];$('langSel').innerHTML=(Array.isArray(langs)?langs:Object.keys(langs)).map(l=>`<option ${l==c.language?'selected':''}>${l}</option>`).join('');
 $('langSel').onchange=e=>setLang(e.target.value);const simple=(c.display||{}).simple!==false;document.body.classList.toggle('simple',simple);
 document.querySelectorAll('.tabs .b').forEach(b=>b.onclick=()=>go(b.dataset.tab));const h=location.hash.slice(1);await reload();if(h)go(h.split('/')[0],decodeURIComponent(h.split('/')[1]||''));await setLang(c.language||'en')}
function toggleSimple(){document.body.classList.toggle('simple');$('simpleBtn').textContent=T('simple')+': '+(document.body.classList.contains('simple')?T('on'):T('off'))}
async function reload(){S=await get('/api/characters')}
function go(t,name){TAB=t;if(name)CUR=name;document.querySelectorAll('.tabs .b').forEach(b=>b.classList.toggle('on',b.dataset.tab==t||(t=='char'&&b.dataset.tab=='gallery')));render()}
const ch=n=>S.characters.find(c=>c.name==n);
function render(){if(!S)return;$('simpleBtn').textContent=T('simple')+': '+(document.body.classList.contains('simple')?T('on'):T('off'));
 $('main').innerHTML=TAB=='create'?wizard():TAB=='cast'?castView():TAB=='char'&&ch(CUR)?charView(ch(CUR)):gallery();if(TAB=='cast')wireDnD();if(TAB=='char')wireViewer()}
function thumb(c){return c.urls.front?`<img src="${c.urls.front}" alt="">`:`<div class="ph">◆</div>`}
function gallery(){if(!S.characters.length)return `<div class="nx-card pane"><p>${esc(T('cs_empty'))}</p><button class="b pri" onclick="go('create')">${esc(T('cs_create'))}</button></div>`;
 return `<div class="grid">`+S.characters.map(c=>`<div class="nx-card card nx-in" onclick="go('char','${esc(c.name)}')">${c.locked?`<span class="lk">🔒 ${esc(T('cs_locked'))}</span>`:''}${thumb(c)}<div class="nm">${esc(c.name)}</div><div class="ds">${esc(c.description||'')}</div>
 <div class="chips"><span class="chip ${Object.keys(c.sheet||{}).length?'on':''}">${esc(T('cs_sheet'))}</span><span class="chip ${c.model3d?'on':''}">3D</span><span class="chip ${c.voice?'vio':''}">♪ ${esc(c.voice_profile?(c.voice_profile.voice||'').replace(/Neural$/,'').split('-').pop():T('cs_novoice'))}</span></div></div>`).join('')+`</div>`}
function wizard(){const st=WIZ.step;return `<div class="nx-card pane" style="max-width:760px"><div class="steps">${[1,2,3].map(i=>`<span class="${i<=st?'on':''}">${i}. ${esc(T('cs_step'+i))}</span>`).join('')}</div>
 ${st==1?`<label>${esc(T('cs_name'))}</label><input id="wName" value="${esc(WIZ.name||'')}"><label>${esc(T('cs_desc'))} ${qm('cs_desc_hint')}</label><textarea id="wDesc">${esc(WIZ.desc||'')}</textarea>
 <label>${esc(T('cs_photos'))} ${qm('cs_photos_hint')}</label><input type="file" id="wPh" accept="image/png,image/jpeg,image/webp" multiple onchange="addPhotos(this.files)"><div class="angles">${WIZ.photos.map(p=>`<img src="${p}">`).join('')}</div>
 <div class="vrow adv"><div><label>${esc(T('cs_gender'))}</label><select id="wG"><option></option>${S.genders.map(g=>`<option>${g}</option>`).join('')}</select></div><div><label>${esc(T('cs_age'))}</label><select id="wA"><option></option>${S.ages.map(g=>`<option>${g}</option>`).join('')}</select></div></div>
 <label>${esc(T('cs_personality'))}</label><input id="wP" value="${esc(WIZ.pers||'')}"><p><button class="b pri" onclick="wizCreate()">${esc(T('cs_next'))} →</button></p>`:
 st==2?`<p>${esc(T('cs_sheet_hint'))}</p><p class="muted">${esc(T('cs_backends'))}: ${Object.entries(S.backends.image).map(([k,v])=>`<span class="chip ${v?'on':''}">${k}</span>`).join(' ')}</p><button class="b pri" onclick="makeSheet('${esc(WIZ.name)}',true)">${esc(T('cs_make_sheet'))}</button> <button class="b" onclick="WIZ.step=3;render()">${esc(T('cs_skip'))}</button>`:
 `<p>${esc(T('cs_done'))}</p><button class="b pri" onclick="go('char','${esc(WIZ.name)}');WIZ={step:1,photos:[]}">${esc(T('cs_open'))}</button>`}</div>`}
function addPhotos(fs){[...fs].slice(0,8).forEach(f=>{const r=new FileReader();r.onload=()=>{WIZ.photos.push(r.result);WIZ.name=$('wName').value;WIZ.desc=$('wDesc').value;render()};r.readAsDataURL(f)})}
async function wizCreate(){const b={name:$('wName').value.trim(),description:$('wDesc').value.trim(),gender:$('wG').value,age:$('wA').value,personality:$('wP').value,photos:WIZ.photos};
 const r=await post('/api/characters/create',b);if(!r.ok)return toast(r.error,1);WIZ.name=b.name;WIZ.step=2;await reload();render()}
async function makeSheet(n,wiz){toast(T('cs_working'));const r=await post('/api/characters/sheet',{name:n});if(!r.ok)return toast(r.error,1);toast(T('cs_sheet_ok',{b:r.backends.join(', ')})+(r.draft?' · DRAFT':''));await reload();if(wiz){WIZ.step=3}render()}
async function make3d(n){toast(T('cs_working'));const r=await post('/api/characters/3d',{name:n});if(!r.ok)return toast(r.error,1);toast('3D: '+r.info.backend);await reload();render()}
async function lock(n,un){const r=await post('/api/characters/lock',{name:n,unlock:!!un});if(!r.ok)return toast(r.error,1);toast(T(un?'cs_unlocked':'cs_locked_ok'));await reload();render()}
function charView(c){const u=c.urls,sh=u.sheet||{},bk=S.backends,vp=c.voice_profile||{};
 const fig=(k,src)=>`<figure>${src?`<img src="${src}">`:`<div class="ph" style="aspect-ratio:1">·</div>`}<figcaption>${esc(T('cs_v_'+k))}</figcaption></figure>`;
 return `<div class="two"><div class="nx-card pane"><div class="nx-h"><span>${esc(c.name)}</span>${c.locked?`<span class="nx-badge b-pass">🔒 ${esc(T('cs_locked'))}</span>`:''}<span class="sp"></span>
 <button class="b sm" onclick="makeSheet('${esc(c.name)}')">${esc(T(Object.keys(c.sheet||{}).length?'cs_regen':'cs_make_sheet'))}</button>
 <button class="b sm ${c.locked?'':'pri'}" onclick="lock('${esc(c.name)}',${c.locked})" title="${esc(T('cs_lock_hint'))}">${esc(T(c.locked?'cs_unlock':'cs_lock'))}</button></div>
 <p class="muted">${esc(c.description||'')}${c.personality?' · '+esc(c.personality):''}</p>
 <div class="sheet">${fig('front',sh.front)}${fig('side',sh.side)}${fig('full',sh.full)}</div><div class="expr">${S.expressions.map(e=>u.expressions[e]?`<img src="${u.expressions[e]}" title="${esc(T('cs_e_'+e))}">`:`<div class="ph" style="aspect-ratio:1;font-size:12px">${esc(T('cs_e_'+e))}</div>`).join('')}</div>
 <h4 class="nx-h" style="margin-top:14px">${esc(T('cs_refs'))} ${qm('cs_refs_hint')}</h4><div class="angles">${u.refs.map(r=>`<img src="${r}">`).join('')}${(u.locked||[]).length?` <span class="muted" style="align-self:center">→ ${esc(T('cs_locked_n',{n:u.locked.length}))}</span>`:''}</div></div>
 <div style="display:grid;gap:14px"><div class="nx-card pane"><div class="nx-h"><span>3D · 360°</span>${qm('cs_3d_hint')}<span class="sp"></span><span class="muted adv">${Object.entries(bk.model3d).map(([k,v])=>`<span class="chip ${v?'on':''}">${k}</span>`).join(' ')}</span>
 <button class="b sm" onclick="make3d('${esc(c.name)}')">${esc(T(c.model3d?'cs_regen3d':'cs_make3d'))}</button></div>
 ${u.model3d?`<model-viewer id="mv" src="${u.model3d}" camera-controls auto-rotate rotation-per-second="24deg" shadow-intensity="1" exposure="1.05" interaction-prompt="none" camera-orbit="25deg 80deg auto"></model-viewer>
 <div style="display:flex;gap:6px;margin-top:8px;align-items:center"><button class="b sm" onclick="stills('${esc(c.name)}')">${esc(T('cs_stills'))}</button><span class="muted">${esc(['standee','draft'].includes(c.model3d_backend)?T('cs_standee'):c.model3d_backend||'')}</span></div><div class="angles">${u.angles.map(a=>`<img src="${a}">`).join('')}</div>`
 :`<div class="ph" style="height:220px;aspect-ratio:auto;font-size:13px">${esc(T('cs_no3d'))}</div>`}</div>
 <div class="nx-card pane"><div class="nx-h"><span>♪ ${esc(T('cs_voice'))}</span>${qm('cs_voice_hint')}</div>
 <div class="vrow"><div><label>${esc(T('cs_voice_lib'))}</label><select id="vFrom"><option value="">—</option>${(S.voices||[]).map(v=>`<option>${esc(v)}</option>`).join('')}</select></div>
 <div><label>${esc(T('cs_preset'))}</label><select id="vPreset"><option value="">—</option>${(S.presets||[]).map(p=>`<option ${vp.preset==p.id?'selected':''} value="${esc(p.id)}">${esc(p.id)}</option>`).join('')}</select></div></div>
 <p class="muted">${vp.voice?`${esc(T('cs_bound'))}: <b style="color:var(--vio)">${esc(vp.voice)}</b> ${vp.pitch?esc(vp.pitch+'Hz'):''} ${vp.rate?esc(vp.rate+'%'):''} ${esc(vp.backend||'')}`:esc(T('cs_novoice'))}</p><div class="wave"></div>
 <label>${esc(T('cs_line'))}</label><input id="vText" value="${esc(T('cs_line_default'))}">
 <p style="display:flex;gap:6px;flex-wrap:wrap"><button class="b pri" onclick="bindVoice('${esc(c.name)}')">${esc(T('cs_bind'))}</button><button class="b" onclick="audition('${esc(c.name)}')">▶ ${esc(T('cs_audition'))}</button>
 <span class="adv" style="display:flex;gap:6px;align-items:center">${esc(T('cs_clone'))}: <select id="cB" style="width:auto">${Object.entries(bk.clone).map(([k,v])=>`<option ${v?'':'disabled'}>${k}</option>`).join('')}</select><input type="file" id="cS" accept="audio/*" style="width:150px"><button class="b sm" onclick="cloneV('${esc(c.name)}')">${esc(T('cs_clone_go'))}</button></span></p>
 <audio id="aud" controls style="width:100%;display:none"></audio></div></div></div>`}
async function bindVoice(n){const r=await post('/api/characters/voice',{name:n,voice_from:$('vFrom').value||undefined,preset:$('vPreset').value||undefined});if(!r.ok)return toast(r.error,1);toast(T('cs_bound')+': '+r.profile.voice);await reload();render()}
async function audition(n){const b=await post('/api/characters/audition',{name:n,text:$('vText').value});if(!(b instanceof Blob))return toast(b.error,1);const a=$('aud');a.src=URL.createObjectURL(b);a.style.display='block';a.play()}
function cloneV(n){const f=$('cS').files[0];if(!f)return toast(T('cs_need_sample'),1);const r=new FileReader();r.onload=async()=>{const x=await post('/api/characters/clone',{name:n,backend:$('cB').value,sample:r.result});if(!x.ok)return toast(x.error,1);toast(T('cs_bound'));await reload();render()};r.readAsDataURL(f)}
function wireViewer(){/* model-viewer is bundled (no CDN). Only Draco/KTX2-compressed GLBs would fetch a decoder from gstatic.com. */}
async function stills(n){const mv=$('mv');mv.autoRotate=false;for(const a of [0,45,90,180,270,315]){mv.cameraOrbit=`${a}deg 80deg auto`;mv.jumpCameraToGoal();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));await new Promise(r=>setTimeout(r,250));
 const r=await post('/api/characters/angle',{name:n,angle:a,image:mv.toDataURL('image/png')});if(!r.ok)return toast(r.error,1)}mv.autoRotate=true;toast(T('cs_stills_ok'));await reload();render()}
function castView(){const slots=CAST.members.map((m,i)=>{const c=m&&ch(m.character);return `<div class="slot ${c?'full':''}" data-i="${i}">${c?`${thumb(c)}<div class="n">${esc(c.name)} ${c.locked?'🔒':''}</div>
 <select onchange="CAST.members[${i}].role=this.value">${S.roles.map(r=>`<option ${m.role==r?'selected':''} value="${r}">${esc(T('cs_role_'+r))}</option>`).join('')}</select><input placeholder="${esc(T('cs_notes'))}" value="${esc(m.notes||'')}" oninput="CAST.members[${i}].notes=this.value"><button class="b sm" onclick="CAST.members[${i}]=null;render()">✕</button>`
 :`<div class="e">${esc(T('cs_drop'))}<br><b>${i+1}</b></div>`}</div>`}).join('');
 const used=new Set(CAST.members.filter(Boolean).map(m=>m.character));
 return `<div class="nx-card pane"><div class="nx-h"><span>${esc(T('cs_cast_title'))}</span>${qm('cs_cast_hint')}<span class="sp"></span><select id="cLoad" style="width:auto" onchange="loadCast(this.value)"><option value="">${esc(T('cs_load'))}…</option>${S.casts.map(c=>`<option ${c.name==CAST.name?'selected':''}>${esc(c.name)}</option>`).join('')}</select>
 <button class="b sm" onclick="exportCast()">${esc(T('cs_export'))}</button><label class="b sm" style="margin:0;text-transform:none;letter-spacing:0;color:var(--fg)">${esc(T('cs_import'))}<input type="file" accept=".json" style="display:none" onchange="importCast(this.files[0])"></label></div>
 <div class="pool">${S.characters.filter(c=>!used.has(c.name)).map(c=>`<button type="button" class="p" draggable="true" data-n="${esc(c.name)}" ${CAST.members.every(Boolean)?'disabled':''}>${c.urls.front?`<img src="${c.urls.front}">`:'◆'}${esc(c.name)}</button>`).join('')||`<span class="muted">${esc(T('cs_pool_empty'))}</span>`}</div>
 <div class="slots">${slots}</div><div class="vrow" style="margin-top:10px"><div><label>${esc(T('cs_cast_name'))}</label><input id="cName" value="${esc(CAST.name)}" oninput="CAST.name=this.value"></div>
 <div><label>${esc(T('cs_set_sheet'))} ${qm('cs_set_hint')}</label><input id="cSet" value="${esc(CAST.set_sheet||'')}" oninput="CAST.set_sheet=this.value" placeholder="/path/to/set.jpg"></div></div>
 <label>${esc(T('cs_plot'))}</label><textarea id="cPlot" oninput="CAST.plot=this.value" placeholder="${esc(T('cs_plot_ph'))}">${esc(CAST.plot)}</textarea>
 <p style="display:flex;gap:8px"><button class="b" onclick="saveCast()">${esc(T('cs_save'))}</button><button class="b pri" onclick="shoot()">🎬 ${esc(T('cs_shoot'))}</button><span class="muted" style="align-self:center">${esc(T('cs_shoot_hint'))}</span></p></div>`}
function addCastMember(n,i=CAST.members.findIndex(m=>!m)){if(i<0||!ch(n)||CAST.members.some(m=>m&&m.character==n))return;CAST.members[i]={character:n,role:i==0?'lead':'supporting',notes:''};render()}
function wireDnD(){document.querySelectorAll('.pool .p').forEach(p=>{p.ondragstart=e=>e.dataTransfer.setData('text/plain',p.dataset.n);p.onclick=()=>addCastMember(p.dataset.n)});
 document.querySelectorAll('.slot').forEach(s=>{s.ondragover=e=>{e.preventDefault();s.classList.add('over')};s.ondragleave=()=>s.classList.remove('over');
 s.ondrop=e=>{e.preventDefault();const n=e.dataTransfer.getData('text/plain');const i=+s.dataset.i;addCastMember(n,i)}})}
function loadCast(n){const c=S.casts.find(x=>x.name==n);if(!c)return;CAST={name:c.name,plot:c.plot||'',set_sheet:c.set_sheet||'',members:[...c.members.map(m=>({...m})),null,null,null,null,null].slice(0,5)};render()}
async function saveCast(){const r=await post('/api/casts/save',{name:CAST.name,members:CAST.members.filter(Boolean),plot:CAST.plot,set_sheet:CAST.set_sheet});if(!r.ok)return toast(r.error,1);toast(T('cs_saved'));await reload();render();return r}
async function shoot(){const s=await saveCast();if(!s||!s.ok)return;const r=await post('/api/casts/shoot',{name:CAST.name});if(!r.ok)return toast(r.error,1);toast(T('cs_shooting',{id:r.id}));setTimeout(()=>location.href='/',1200)}
async function exportCast(){const r=await post('/api/casts/export',{name:CAST.name});if(!r.ok)return toast(r.error,1);const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(r.file)],{type:'application/json'}));a.download=r.filename;a.click()}
async function importCast(f){const t=await f.text();const r=await post('/api/casts/import',{text:t});if(!r.ok)return toast(r.error,1);toast(T('cs_imported'));await reload();loadCast(r.cast.name)}
window.addEventListener('hashchange',()=>{const h=location.hash.slice(1);if(h)go(h.split('/')[0],decodeURIComponent(h.split('/')[1]||''))});
boot();

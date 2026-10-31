() => {
  const out = [];
  const vw = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > vw + 1) out.push({kind:'page-hscroll', w:document.documentElement.scrollWidth, vw});
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    const tag = el.tagName.toLowerCase();
    const label = (el.id ? '#'+el.id : tag + (el.className && typeof el.className==='string' ? '.'+el.className.split(' ')[0] : '')) + ' "' + (el.textContent||'').trim().slice(0,30) + '"';
    // clipped text: content wider than box with hidden overflow and no ellipsis
    if (own && el.scrollWidth > el.clientWidth + 2 && ['hidden','clip'].includes(cs.overflowX) && cs.textOverflow !== 'ellipsis') out.push({kind:'clipped', el:label});
    // one-char-per-line wrap: tall narrow text in links/buttons
    if (own && ['a','button','label','th','td','span'].includes(tag)) {
      const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize)*1.3;
      const txt = el.textContent.trim();
      if (txt.length >= 3 && r.height > lh*2.6 && r.width < parseFloat(cs.fontSize)*3.2) out.push({kind:'char-column', el:label});
      if (tag==='button' || tag==='a') { const rg=document.createRange(); rg.selectNodeContents(el); const tops=new Set([...rg.getClientRects()].filter(x=>x.width>1).map(x=>Math.round(x.top/4)));
        if (tops.size > 1 && txt.length <= 24) out.push({kind:'button-wrap', el:label}); }
    }
    // element sticking out of the viewport horizontally
    if (r.right > vw + 2 && cs.position !== 'fixed' && !el.closest('[data-hscroll]')) out.push({kind:'off-right', el:label, right:Math.round(r.right)});
  }
  const seen = new Set();
  return out.filter(o => { const k = o.kind + o.el; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 60);
}

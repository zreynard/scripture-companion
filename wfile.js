/* Chart files for Worship: a PDF or photos of a song's chords and lyrics, kept on this phone and shown exactly as they
   are (the dependable alternative to the app reading a pasted chart). Used by the app and by the leader's Present page.
   Stored in IndexedDB as plain bytes (ArrayBuffer), which every browser keeps; PDFs are drawn with pdf.js (pdf/,
   Apache-2.0), loaded only when a PDF is opened and kept offline by the app's offline helper. */
(function (G) {
  'use strict';
  const BASE = (document.currentScript && document.currentScript.src) ? new URL('.', document.currentScript.src).href : new URL('.', location.href).href;
  const PDF_V = '4.10.38', MAX = 40 * 1048576, IMG_MAX = 2400, IMG_BIG = 4 * 1048576;
  /* the look, in one place for the app and the Present page */
  const CSS = `
.wfv-pages{display:flex;flex-direction:column;gap:10px}
.wfv-page{position:relative;width:100%;aspect-ratio:8.5/11;background:#fff;border-radius:6px;box-shadow:0 2px 10px rgba(27,36,64,.12);overflow:hidden}
.wfv-page:not(.drawn)::after{content:'';position:absolute;inset:0;background:linear-gradient(100deg,#fff 30%,#f6f2ea 50%,#fff 70%);background-size:200% 100%;animation:wfvsh 1.2s linear infinite}
@keyframes wfvsh{from{background-position:100% 0}to{background-position:-100% 0}}
.wfv-page>canvas,.wfv-page>img{position:absolute;inset:0;width:100%;height:100%;display:block;object-fit:contain}
.wfv-perr{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:20px;text-align:center;color:#6b7088;font-size:14px}
.wfv-msg{color:#6b7088;font-size:15px;line-height:1.5;margin:18px 4px;text-align:center}
html.wfv-open,html.wfv-open body{overflow:hidden!important}
#wfview{position:fixed;inset:0;z-index:2147483000;background:#f4efe4;display:flex;flex-direction:column;color:#1b2440;font:16px -apple-system,BlinkMacSystemFont,system-ui,sans-serif}
#wfview .wfv-bar{flex:none;display:flex;align-items:center;gap:8px;padding:calc(8px + env(safe-area-inset-top)) calc(10px + env(safe-area-inset-right)) 8px calc(10px + env(safe-area-inset-left));border-bottom:1px solid rgba(27,36,64,.08);background:#fbf8f1}
#wfview button{font:inherit;cursor:pointer;-webkit-tap-highlight-color:transparent}
#wfview .wfv-x{flex:none;display:flex;align-items:center;gap:6px;height:40px;padding:0 14px 0 12px;border-radius:20px;border:0;background:#1b2440;color:#fff;font-weight:700;font-size:15px}
#wfview .wfv-t{flex:1;min-width:0;font:500 18px "Iowan Old Style",Palatino,Georgia,serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#wfview .wfv-n{flex:none;font-size:13px;color:#6b7088;font-variant-numeric:tabular-nums}
#wfview .wfv-zm{flex:none;display:flex;align-items:center;background:rgba(27,36,64,.06);border-radius:20px}
#wfview .wfv-zm button{border:0;background:none;color:#1b2440;height:40px;min-width:40px;font-size:20px;font-weight:600}
#wfview .wfv-zm .wfv-zv{font-size:13px;min-width:50px;font-variant-numeric:tabular-nums;font-weight:600}
#wfview .wfv-sh{flex:none;border:0;background:#f6ecd6;color:#7a5c1c;border-radius:20px;height:40px;padding:0 14px;font-weight:600;font-size:14px}
#wfview .wfv-sc{flex:1;min-height:0;overflow:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;padding:12px calc(10px + env(safe-area-inset-right)) calc(28px + env(safe-area-inset-bottom)) calc(10px + env(safe-area-inset-left));touch-action:pan-x pan-y;outline:none}
#wfview .wfv-z{--k:1;width:calc(var(--k) * min(100%, 980px));margin:0 auto;display:flex;flex-direction:column;gap:12px}
#wfview.zoomed .wfv-z{margin:0}
@media (max-width:560px){#wfview .wfv-x span{display:none}#wfview .wfv-x{padding:0 11px}#wfview .wfv-zm .wfv-zv{display:none}#wfview .wfv-sh{padding:0 12px}#wfview .wfv-t{font-size:16px}}
@media (max-width:380px){#wfview .wfv-n{display:none}}
`;
  try { if (!document.getElementById('wfv-css')) { const s = document.createElement('style'); s.id = 'wfv-css'; s.textContent = CSS; (document.head || document.documentElement).appendChild(s); } } catch (e) { }
  let dbp = null;
  function db() {
    if (dbp) return dbp;
    dbp = new Promise((ok, no) => { const r = indexedDB.open('sc-wfile', 1); r.onupgradeneeded = () => { const d = r.result; if (!d.objectStoreNames.contains('f')) d.createObjectStore('f', { keyPath: 'id' }); };
      r.onsuccess = () => ok(r.result); r.onerror = () => { dbp = null; no(r.error); }; r.onblocked = () => { dbp = null; no(new Error('blocked')); }; });
    return dbp;
  }
  function tx(mode, f) { return db().then(d => new Promise((ok, no) => { const t = d.transaction('f', mode), st = t.objectStore('f'); let res; const q = f(st); if (q) q.onsuccess = () => { res = q.result; };
    t.oncomplete = () => ok(res); t.onerror = () => no(t.error || new Error('tx')); t.onabort = () => no(t.error || new Error('abort')); })); }
  const put = rec => tx('readwrite', st => st.put(rec)), get = id => tx('readonly', st => st.get(id)), del = id => tx('readwrite', st => st.delete(id));
  const ids = () => tx('readonly', st => st.getAllKeys ? st.getAllKeys() : null).then(k => new Set(k || []));
  const newId = () => 'f' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const kind = ty => /pdf/.test(ty || '') ? 'pdf' : 'img';
  const isPdf = (f) => /pdf/i.test(f.type) || /\.pdf$/i.test(f.name || '');
  function persist() { try { if (navigator.storage && navigator.storage.persist) navigator.storage.persist(); } catch (e) { } }
  /* a big photo is made smaller once (a JPEG at most 2400 px across): it still reads sharp, and stays light to keep and back up */
  async function shrink(file) {
    if (file.size <= IMG_BIG || !G.createImageBitmap) return null;
    try { const bm = await createImageBitmap(file), k = Math.min(1, IMG_MAX / Math.max(bm.width, bm.height)); const c = document.createElement('canvas'); c.width = Math.round(bm.width * k); c.height = Math.round(bm.height * k);
      c.getContext('2d').drawImage(bm, 0, 0, c.width, c.height); const b = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.88)); return b && b.size < file.size ? b : null; } catch (e) { return null; }
  }
  /* files picked → kept on the phone → their small references for the song: [{id, ty, n, sz}] */
  async function add(files) {
    persist(); const out = [];
    for (const f of files) {
      if (!f) continue; const pdf = isPdf(f);
      if (!pdf && !/^image\//.test(f.type || '') && !/\.(jpe?g|png|gif|webp|heic|heif)$/i.test(f.name || '')) throw new Error('kind:' + (f.name || ''));
      if (f.size > MAX) throw new Error('big:' + (f.name || ''));
      const small = pdf ? null : await shrink(f), src = small || f, ty = pdf ? 'application/pdf' : (small ? 'image/jpeg' : (f.type || 'image/jpeg'));
      const buf = await src.arrayBuffer(), rec = { id: newId(), ty, n: f.name || (pdf ? 'Chart.pdf' : 'Photo.jpg'), sz: buf.byteLength, buf };
      try { await put(rec); } catch (e) { throw new Error('space'); }
      const back = await get(rec.id).catch(() => null); if (!back || !back.buf || back.buf.byteLength !== rec.sz) throw new Error('space');   // read back: it really is kept
      out.push({ id: rec.id, ty, n: rec.n, sz: rec.sz });
    }
    return out;
  }
  /* pdf.js, loaded once, from this site (works offline) */
  let pdfp = null;
  function pdfjs() {
    if (pdfp) return pdfp;
    pdfp = import(BASE + 'pdf/pdf.min.mjs?v=' + PDF_V).then(m => { m.GlobalWorkerOptions.workerSrc = BASE + 'pdf/pdf.worker.min.mjs?v=' + PDF_V; return m; }).catch(e => { pdfp = null; throw e; });
    return pdfp;
  }
  /* draw every page of a song's files into `box`, fitted to its width. Pages are laid out at once (their shape is known),
     but only those near the screen are drawn, and ones far away are let go, so a long PDF never runs a phone out of
     memory. Pages follow the box: rotate the phone or resize the window and they are drawn again, sharp, at the new size;
     zoom (full screen) draws the visible pages again at the zoomed size. */
  const LIVE = new Set();
  function release() { LIVE.forEach(c => { if (!c.box.isConnected) c.destroy(); }); }
  async function render(box, refs, o) {
    o = o || {}; release(); if (box._wfc) box._wfc.destroy(); box.innerHTML = ''; box.classList.add('wfv-pages');
    const ctl = { box, pages: [], docs: [], zoom: 1, dead: false, io: null, far: null, ro: null, w: 0, t: 0 }; box._wfc = ctl; LIVE.add(ctl);
    const msg = t => { const p = document.createElement('p'); p.className = 'wfv-msg'; p.textContent = t; box.appendChild(p); };
    const dpr = () => Math.min(3, G.devicePixelRatio || 1);
    /* draw one PDF page at its current width × zoom, within what a phone's canvas allows (16.7 million pixels, 4096 a side) */
    async function draw(pg) {
      if (ctl.dead || pg.busy || pg.kind !== 'pdf') return; const cssW = pg.el.clientWidth || box.clientWidth; if (!cssW) return;
      let k = cssW * dpr() * Math.max(1, ctl.zoom) / pg.w; const lim = Math.min(4096 / pg.w, 4096 / pg.h, Math.sqrt(16.7e6 / (pg.w * pg.h))); k = Math.min(k, lim);
      if (pg.cv && Math.abs(pg.k - k) / k < 0.08) return; pg.busy = true;
      try { const page = await pg.doc.getPage(pg.n), vp = page.getViewport({ scale: k }), c = document.createElement('canvas'); c.className = 'wfv-cv'; c.width = Math.floor(vp.width); c.height = Math.floor(vp.height);
        const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, c.width, c.height); await page.render({ canvasContext: x, viewport: vp }).promise; page.cleanup && page.cleanup();
        if (ctl.dead) return; if (pg.cv) { pg.cv.width = 0; pg.cv.remove(); } pg.el.appendChild(c); pg.cv = c; pg.k = k; pg.el.classList.add('drawn'); }
      catch (e) { if (!pg.cv) pg.el.innerHTML = '<span class="wfv-perr">This page could not be drawn.</span>'; }
      finally { pg.busy = false; if (pg.again) { pg.again = false; draw(pg); } }
    }
    function free(pg) { if (pg.kind === 'pdf' && pg.cv) { pg.cv.width = 0; pg.cv.remove(); pg.cv = null; pg.k = 0; pg.el.classList.remove('drawn'); } }
    ctl.redraw = () => ctl.pages.forEach(pg => { if (pg.near) { if (pg.busy) pg.again = true; else draw(pg); } });
    ctl.destroy = () => { ctl.dead = true; LIVE.delete(ctl); try { ctl.io && ctl.io.disconnect(); ctl.far && ctl.far.disconnect(); ctl.ro && ctl.ro.disconnect(); } catch (e) { } ctl.pages.forEach(pg => { free(pg); if (pg.url) URL.revokeObjectURL(pg.url); }); ctl.docs.forEach(d => { try { d.destroy(); } catch (e) { } }); };
    for (const r of refs || []) {
      const rec = await get(r.id).catch(() => null); if (ctl.dead) return 0;
      if (!rec || !rec.buf) { if (o.missing && !o._tried) { const ok = await o.missing(r).catch(() => false); if (ok && !ctl.dead) return render(box, refs, Object.assign({}, o, { _tried: 1 })); } msg('“' + (r.n || 'Chart file') + '” is not on this phone yet.'); continue; }
      if (kind(rec.ty) === 'pdf') {
        let doc; try { const lib = await pdfjs(); doc = await lib.getDocument({ data: new Uint8Array(rec.buf.slice(0)), isEvalSupported: false }).promise; }
        catch (e) { msg('This PDF could not be opened here' + (e && e.name === 'PasswordException' ? ' (it has a password)' : '') + '. Use Share to open it in another app.'); continue; }
        if (ctl.dead) { doc.destroy(); return 0; } ctl.docs.push(doc);
        for (let i = 1; i <= Math.min(doc.numPages, 200); i++) { const v = (await doc.getPage(i)).getViewport({ scale: 1 }), el = document.createElement('div'); el.className = 'wfv-page'; el.style.aspectRatio = v.width + ' / ' + v.height;
          el.dataset.page = String(ctl.pages.length + 1); box.appendChild(el); ctl.pages.push({ kind: 'pdf', doc, n: i, w: v.width, h: v.height, el }); }
      } else {
        const el = document.createElement('div'), img = document.createElement('img'), url = URL.createObjectURL(new Blob([rec.buf], { type: rec.ty || 'image/jpeg' })); el.className = 'wfv-page drawn'; el.dataset.page = String(ctl.pages.length + 1);
        img.alt = r.n || 'Chart'; img.decoding = 'async'; img.src = url; el.appendChild(img); box.appendChild(el); ctl.pages.push({ kind: 'img', el, url });
        await new Promise(ok => { img.onload = () => { el.style.aspectRatio = img.naturalWidth + ' / ' + img.naturalHeight; ok(); }; img.onerror = () => { el.innerHTML = '<span class="wfv-perr">This photo could not be shown.</span>'; ok(); }; });
      }
    }
    if (ctl.dead) return 0;
    /* which pages are near: watched against the box that scrolls them (a page scrolled inside a box is only "near"
       when measured against that box); a page whose box is drawn again (Present, every slide) is watched again */
    ctl.observe = root => { if (ctl.dead) return; try { ctl.io && ctl.io.disconnect(); ctl.far && ctl.far.disconnect(); } catch (e) { }
      if (!('IntersectionObserver' in G)) { ctl.pages.forEach(pg => { pg.near = true; draw(pg); }); return; }
      ctl.io = new IntersectionObserver(es => es.forEach(e => { const pg = ctl.pages.find(p => p.el === e.target); if (pg && e.isIntersecting) { pg.near = true; draw(pg); } }), { root: root || null, rootMargin: '150% 0px 150% 0px' });
      ctl.far = new IntersectionObserver(es => es.forEach(e => { const pg = ctl.pages.find(p => p.el === e.target); if (pg && !e.isIntersecting && e.target.isConnected) { pg.near = false; free(pg); } }), { root: root || null, rootMargin: '500% 0px 500% 0px' });
      ctl.pages.forEach(pg => { ctl.io.observe(pg.el); ctl.far.observe(pg.el); }); };
    ctl.observe(o.root);
    ctl.w = box.clientWidth;
    if ('ResizeObserver' in G) { ctl.ro = new ResizeObserver(() => { const w = box.clientWidth; if (!w || Math.abs(w - ctl.w) / Math.max(1, ctl.w) < 0.04) return; ctl.w = w; clearTimeout(ctl.t); ctl.t = setTimeout(ctl.redraw, 180); }); ctl.ro.observe(box); }
    box.dataset.pages = String(ctl.pages.length); return ctl.pages.length;
  }
  /* full screen: the whole screen (the browser's real full screen where it has one: iPad, computers), pinch, double-tap,
     Ctrl/⌘ + scroll or − / + to zoom, scroll to move. Done (or Esc, or the back button) collapses it back to the song. */
  let OPEN = null;
  const IC = { done: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>' };
  function open(refs, title, o) {
    close(true); o = o || {};
    const v = document.createElement('div'); v.id = 'wfview'; v.setAttribute('role', 'dialog'); v.setAttribute('aria-modal', 'true'); v.setAttribute('aria-label', (title || 'Chart') + ', chart file');
    v.innerHTML = `<div class="wfv-bar"><button class="wfv-x" aria-label="Done: close full screen">${IC.done}<span>Done</span></button><b class="wfv-t"></b><span class="wfv-n" aria-live="polite"></span>`
      + `<span class="wfv-zm"><button class="wfv-zo" aria-label="Zoom out">−</button><button class="wfv-zv" aria-label="Fit to width">100%</button><button class="wfv-zi" aria-label="Zoom in">+</button></span><button class="wfv-sh" aria-label="Share or open in another app">Share</button></div>`
      + `<div class="wfv-sc" tabindex="0"><div class="wfv-z"></div></div>`;
    v.querySelector('.wfv-t').textContent = title || 'Chart';
    const opener = document.activeElement; document.body.appendChild(v); document.documentElement.classList.add('wfv-open');
    const sc = v.querySelector('.wfv-sc'), z = v.querySelector('.wfv-z'), n = v.querySelector('.wfv-n'), zv = v.querySelector('.wfv-zv'); let zoom = 1, zt = 0, total = 0;
    const setZoom = (k, cx, cy) => { k = Math.round(Math.max(1, Math.min(4, k)) * 100) / 100; if (k === zoom) return; const r = sc.getBoundingClientRect(), ox = cx == null ? r.width / 2 : cx - r.left, oy = cy == null ? r.height / 2 : cy - r.top,
      px = (sc.scrollLeft + ox) / zoom, py = (sc.scrollTop + oy) / zoom; zoom = k; z.style.setProperty('--k', k); sc.scrollLeft = px * k - ox; sc.scrollTop = py * k - oy; v.dataset.zoom = k.toFixed(2); zv.textContent = Math.round(k * 100) + '%';
      v.classList.toggle('zoomed', k > 1); const c = z._wfc; if (c) { c.zoom = k; clearTimeout(zt); zt = setTimeout(c.redraw, 260); } };
    const pageNow = () => { if (total < 2) { n.textContent = ''; return; } const pg = [...z.querySelectorAll('.wfv-page')], mid = sc.getBoundingClientRect().top + sc.clientHeight / 3; let k = 1; pg.forEach((e, i) => { if (e.getBoundingClientRect().top <= mid) k = i + 1; }); n.textContent = k + ' / ' + total; };
    OPEN = { v, opener, back: o.back, pushed: false, fs: false, setZoom };
    v.querySelector('.wfv-x').onclick = () => close();
    v.querySelector('.wfv-sh').onclick = () => share(refs, title);
    v.querySelector('.wfv-zo').onclick = () => setZoom(zoom - 0.5); v.querySelector('.wfv-zi').onclick = () => setZoom(zoom + 0.5); zv.onclick = () => setZoom(1);
    render(z, refs, { root: sc, missing: o.missing }).then(p => { total = p; pageNow(); v.dataset.ready = '1'; });
    sc.addEventListener('scroll', pageNow, { passive: true });
    let pinch = null, lastTap = 0;
    sc.addEventListener('touchstart', e => { if (e.touches.length === 2) { const [a, b] = e.touches; pinch = { d: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) || 1, z: zoom, cx: (a.clientX + b.clientX) / 2, cy: (a.clientY + b.clientY) / 2 }; }
      else if (e.touches.length === 1) { const t = Date.now(); if (t - lastTap < 300) { setZoom(zoom > 1.2 ? 1 : 2.2, e.touches[0].clientX, e.touches[0].clientY); lastTap = 0; } else lastTap = t; } }, { passive: true });
    sc.addEventListener('touchmove', e => { if (pinch && e.touches.length === 2) { e.preventDefault(); const [a, b] = e.touches; setZoom(pinch.z * Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) / pinch.d, pinch.cx, pinch.cy); } }, { passive: false });
    sc.addEventListener('touchend', e => { if (e.touches.length < 2) pinch = null; });
    ['gesturestart', 'gesturechange'].forEach(ev => v.addEventListener(ev, e => e.preventDefault(), { passive: false }));   // Safari: the pinch zooms the chart, not the page
    sc.addEventListener('wheel', e => { if (!e.ctrlKey && !e.metaKey) return; e.preventDefault(); setZoom(zoom * Math.exp(-e.deltaY / 300), e.clientX, e.clientY); }, { passive: false });
    sc.addEventListener('dblclick', e => setZoom(zoom > 1.2 ? 1 : 2.2, e.clientX, e.clientY));
    G.addEventListener('keydown', key);
    /* the back button (or a swipe back) collapses it, not the song */
    try { history.pushState(Object.assign({}, history.state || {}, { wfv: 1 }), ''); OPEN.pushed = true; } catch (e) { }
    G.addEventListener('popstate', pop);
    /* the browser's real full screen where it has one; leaving it (Esc on a computer) collapses the view too */
    if (document.fullscreenEnabled && v.requestFullscreen && o.fullscreen !== false && G.WFile.fs !== false) { v.requestFullscreen({ navigationUI: 'hide' }).then(() => { if (OPEN && OPEN.v === v) OPEN.fs = true; }).catch(() => { }); }
    document.addEventListener('fullscreenchange', fsc);
    setTimeout(() => { try { sc.focus({ preventScroll: true }); } catch (e) { } }, 30);
    return v;
  }
  function key(e) { if (!OPEN) return; if (e.key === 'Escape') { e.preventDefault(); close(); } else if ((e.key === '+' || e.key === '=') && !e.altKey) { e.preventDefault(); OPEN.setZoom(+(OPEN.v.dataset.zoom || 1) + 0.5); } else if (e.key === '-' && !e.altKey) { e.preventDefault(); OPEN.setZoom(+(OPEN.v.dataset.zoom || 1) - 0.5); } else if (e.key === '0') { OPEN.setZoom(1); } }
  function pop() { if (OPEN) { OPEN.pushed = false; close(); } }
  function fsc() { if (OPEN && OPEN.fs && !document.fullscreenElement) { OPEN.fs = false; close(); } }
  /* collapse: back to the song exactly as it was (focus where it was) */
  function close(quiet) {
    const o = OPEN; OPEN = null; G.removeEventListener('keydown', key); G.removeEventListener('popstate', pop); document.removeEventListener('fullscreenchange', fsc);
    const v = document.getElementById('wfview'); if (v) { const z = v.querySelector('.wfv-z'); if (z && z._wfc) z._wfc.destroy(); v.remove(); }
    document.documentElement.classList.remove('wfv-open');
    if (o) { if (o.fs && document.fullscreenElement) { try { document.exitFullscreen().catch(() => { }); } catch (e) { } } if (o.pushed && !quiet && history.state && history.state.wfv) { try { history.back(); } catch (e) { } }
      const f = o.opener && o.opener.isConnected ? o.opener : o.back ? document.querySelector(o.back) : null;   /* the page may have been drawn again (the screen turned): its button now */
      if (f && f.focus) { try { f.focus({ preventScroll: true }); } catch (e) { } } }
  }
  /* the phone's own share sheet (Files, Books, Mail…); without one, the file opens in a new tab */
  async function share(refs, title) {
    const files = []; for (const r of refs || []) { const rec = await get(r.id).catch(() => null); if (rec && rec.buf) files.push(new File([rec.buf], rec.n || r.n || 'Chart', { type: rec.ty })); }
    if (!files.length) return false;
    try { if (navigator.canShare && navigator.canShare({ files })) { await navigator.share({ files, title: title || 'Chart' }); return true; } } catch (e) { if (e && e.name === 'AbortError') return true; }
    const u = URL.createObjectURL(files[0]); const a = document.createElement('a'); a.href = u; a.target = '_blank'; a.rel = 'noopener'; a.download = files[0].name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 60000); return true;
  }
  const label = refs => !refs || !refs.length ? '' : refs.length > 1 ? refs.length + ' photos' : kind(refs[0].ty) === 'pdf' ? 'PDF' : 'Photo';
  const size = b => b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
  G.WFile = { put, get, del, ids, add, render, open, close, share, label, size, kind, pdfjs, newId, release, isOpen: () => !!OPEN };
})(window);

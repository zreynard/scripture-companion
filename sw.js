// Scripture Companion service worker. Caches only the app itself so it opens offline;
// sermon audio always streams from the publisher (never cached, never proxied).
const CACHE = 'sc-v1794602742';
const SHELL = ['./', 'index.html', 'worship.js', 'manifest.webmanifest', 'icon.svg', 'icon-180.png', 'icon-192.png', 'icon-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k.startsWith('sc-') && k !== CACHE && k !== 'sc-bible-1').map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return; // audio + links: straight to network
  if (u.pathname.endsWith('version.txt')) return;                          // version checks never come from cache
  if (e.request.mode === 'navigate' && /\/(tv|live|s)\//.test(u.pathname)) {  // the Worship screen, remote and shared-sermon pages: never stored as the app
    e.respondWith(fetch(e.request, { cache: 'no-store' }).catch(() => caches.match(e.request)));
    return;
  }
  if (e.request.mode === 'navigate') { // the phone's copy at once, no waiting on the network (fetched when there is none yet)
    const fresh = () => fetch(e.request, { cache: 'no-store' }).then(r => { if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put('index.html', copy)); } return r; });
    // (a newer build is fetched by the app itself when version.txt says there is one, so nothing competes with the audio)
    e.respondWith(caches.match('index.html').then(hit => hit || fresh()).catch(() => fresh()));
    return;
  }
  if (u.pathname.endsWith('index.html') && u.searchParams.has('sw-refresh')) {  // the app asking for the newest build, to open next
    e.respondWith(fetch('index.html', { cache: 'no-store' }).then(r => { if (r.ok) { const copy = r.clone(); return caches.open(CACHE).then(c => c.put('index.html', copy)).then(() => r); } return r; }));
    return;
  }
  if (u.pathname.includes('/narration/')) {  // chapter timings grow as narration is published: newest when online
    e.respondWith(fetch(e.request, { cache: 'no-cache' }).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); } return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  if (u.pathname.includes('/bible/')) {  // Bible books: kept once downloaded, across app versions
    e.respondWith(caches.open('sc-bible-1').then(c => c.match(e.request).then(r => r || fetch(e.request).then(res => { if (res.ok) c.put(e.request, res.clone()); return res; }))).catch(gone));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)).catch(gone));
});
/* a download that fails or is cut off is answered as plainly unavailable (the app shows its own message), never as a
   broken reply — Safari reports a broken one as an access-control error on the page */
function gone() { return new Response('', { status: 504, statusText: 'Unavailable' }); }

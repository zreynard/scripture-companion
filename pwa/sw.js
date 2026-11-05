// Scripture Companion service worker. Caches only the app itself so it opens offline;
// sermon audio always streams from the publisher (never cached, never proxied).
const CACHE = 'sc-v__VERSION__';
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
  if (e.request.mode === 'navigate' && /\/(tv|live)\//.test(u.pathname)) {  // the Worship screen and remote pages: never stored as the app
    e.respondWith(fetch(e.request, { cache: 'no-store' }).catch(() => caches.match(e.request)));
    return;
  }
  if (e.request.mode === 'navigate') { // network first so new builds show up; cache when offline
    e.respondWith(fetch(e.request, { cache: 'no-store' }).then(r => {  // always the newest page when online
      const copy = r.clone(); caches.open(CACHE).then(c => c.put('index.html', copy)); return r;
    }).catch(() => caches.match('index.html')));
    return;
  }
  if (u.pathname.includes('/narration/')) {  // chapter timings grow as narration is published: newest when online
    e.respondWith(fetch(e.request, { cache: 'no-cache' }).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); } return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  if (u.pathname.includes('/bible/')) {  // Bible books: kept once downloaded, across app versions
    e.respondWith(caches.open('sc-bible-1').then(c => c.match(e.request).then(r => r || fetch(e.request).then(res => { if (res.ok) c.put(e.request, res.clone()); return res; }))));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});

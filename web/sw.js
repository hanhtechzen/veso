// LuckyVision service worker: dùng được khi mạng chập chờn, mở lại trang đã xem khi mất mạng.
const VERSION = 'lv-1';
const CORE = ['/offline.html', '/assets/site.css', '/assets/lv-date.css', '/assets/lv-date.js', '/icons/icon-192.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(VERSION).then(c => c.addAll(CORE)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/v1/') || url.pathname.startsWith('/admin')) return;  // dữ liệu trực tiếp và quản trị: luôn lấy mới
  if (req.mode === 'navigate') {
    // Trang: ưu tiên mạng để luôn có kết quả mới; mất mạng thì dùng bản đã lưu hoặc trang ngoại tuyến
    e.respondWith(fetch(req).then(res => { const copy = res.clone(); caches.open(VERSION).then(c => c.put(req, copy)); return res; })
      .catch(() => caches.match(req).then(r => r || caches.match('/offline.html'))));
    return;
  }
  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/')) {
    e.respondWith(caches.match(req).then(hit => {
      const net = fetch(req).then(res => { const copy = res.clone(); caches.open(VERSION).then(c => c.put(req, copy)); return res; });
      return hit || net;
    }));
  }
});

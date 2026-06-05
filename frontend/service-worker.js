const CACHE = 'gnm-v2516';
const STATIC = ['/css/bootstrap.css', '/css/style.css', '/css/mechanic.css', '/css/admin.css', '/js/config.js', '/js/components.js'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) return;

  // HTML navigation requests: network-first (fresh page hamesha chahiye mobile pe)
  const isNavigation = e.request.mode === 'navigate' || url.pathname.endsWith('.html') || url.pathname.endsWith('/');
  if (isNavigation) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }

  // CSS/JS: cache-first with network fallback
  e.respondWith(caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
    if (res.ok && (url.pathname.startsWith('/css/') || url.pathname.startsWith('/js/'))) {
      const cloneToCache = res.clone();
      caches.open(CACHE).then(c => c.put(e.request, cloneToCache));
    }
    return res;
  }).catch(() => cached)));
});

// ── Firebase FCM v9 compat ─────────────────────────────────────────────────
try {
  importScripts('https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js');
  importScripts('https://www.gstatic.com/firebasejs/9.23.0/firebase-messaging-compat.js');
} catch(e) {
  console.warn('Firebase scripts load nahi hue — notifications unavailable', e);
}

let messaging = null;
if (typeof firebase !== 'undefined') {
  firebase.initializeApp({
    apiKey:            "AIzaSyAcTO4mDIopzinhQKrxOuDGp3-NclWYrJw",
    authDomain:        "garagenearme-b5e36.firebaseapp.com",
    projectId:         "garagenearme-b5e36",
    storageBucket:     "garagenearme-b5e36.firebasestorage.app",
    messagingSenderId: "139028585448",
    appId:             "1:139028585448:web:5225c22c98a9054b33e25d"
  });
  messaging = firebase.messaging();
}

let activeSOSLoops = new Set();

self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'STOP_SOS_LOOP') {
        activeSOSLoops.delete(String(event.data.sosId));
    } else if (event.data && event.data.type === 'STOP_ALL_SOS_LOOPS') {
        activeSOSLoops.clear();
    }
});

// Background notification handler
if (messaging) messaging.onBackgroundMessage(payload => {
    const title = payload.notification?.title || 'GarageNearMe';
    const body  = payload.notification?.body  || '';
    const data  = payload.data || {};
    const isSOS = data.type === 'sos';

    if (!isSOS) {
        return self.registration.showNotification(title, {
            body,
            icon:    '/assets/icon-192.png',
            badge:   '/assets/icon-192.png',
            vibrate: [200,100,200],
            requireInteraction: true,
            tag:     'gnm-alert',
            renotify: true,
            data,
            actions: [{ action: 'open', title: '👁 Dekho' }]
        });
    }

    // SOS Repeated Loop logic
    const sosId = String(data.id || data.sosId || 'unknown');
    activeSOSLoops.add(sosId);

    return new Promise(async (resolve) => {
        let iteration = 0;
        
        const notify = async () => {
            try {
                await self.registration.showNotification(title, {
                    body,
                    icon:    '/assets/icon-192.png',
                    badge:   '/assets/icon-192.png',
                    vibrate: [500,200,500,200,500],
                    requireInteraction: true,
                    tag:     'sos-alert-' + sosId,
                    renotify: true, // Forces sound to play again!
                    data,
                    actions: [
                        { action: 'accept', title: '✅ Accept SOS' },
                        { action: 'decline', title: '❌ Decline'   },
                    ]
                });
            } catch(e) { console.error('Loop notify error', e); }
        };

        // Fire first notification immediately
        await notify();
        iteration++;

        const interval = setInterval(async () => {
            if (!activeSOSLoops.has(sosId) || iteration >= 10) {
                clearInterval(interval);
                activeSOSLoops.delete(sosId);
                resolve();
                return;
            }
            await notify();
            iteration++;
        }, 7000); // Keep ringing every 7 seconds for ~70 seconds
    });
});

// Notification click handler
self.addEventListener('notificationclick', e => {
    e.notification.close();
    
    // Stop the background ringing loop for this SOS
    const data  = e.notification.data || {};
    const sosId = String(data.id || data.sosId || 'unknown');
    activeSOSLoops.delete(sosId);

    if (e.action === 'decline') {
        // Here you might want to call an API to decline, but for now just close
        return;
    }

    const screen = data.screen || 'sos-alerts';
    const m      = ['bookings','sos-alerts','dashboard','services','earnings','payout-history','profile'];
    const url    = (m.includes(screen) || screen.startsWith('sos')) ? `/mechanic/${screen}` : `/${screen}`;

    e.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
            for (const c of list) { if (c.url.includes(url) && 'focus' in c) return c.focus(); }
            if (clients.openWindow) return clients.openWindow(url);
        })
    );
});
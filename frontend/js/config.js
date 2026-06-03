function getApiBase() {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") return "http://localhost:8000/api";
    if (/^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host)) {
        return `http://${host}:8000/api`;
    }
    return window.location.origin + "/api";
}

function getWsBase() {
    const host = window.location.hostname;
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    if (host === "localhost" || host === "127.0.0.1") return `ws://localhost:8000`;
    if (/^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host)) return `ws://${host}:8000`;
    return `${proto}://${window.location.host}`;
}

// ── Firebase Config ────────────────────────────────────────────────────────
const firebaseConfig = {
    apiKey:            "AIzaSyAcTO4mDIopzinhQKrxOuDGp3-NclWYrJw",
    authDomain:        "garagenearme-b5e36.firebaseapp.com",
    projectId:         "garagenearme-b5e36",
    storageBucket:     "garagenearme-b5e36.firebasestorage.app",
    messagingSenderId: "139028585448",
    appId:             "1:139028585448:web:5225c22c98a9054b33e25d",
    measurementId:     "G-BFR17F1KL3"
};

const VAPID_KEY = "BHU4b9XF3oH9piDcWFj6EfITIaPfth_uEAme59GKvaolsgki-4ygl68tlhde3FxqQtnmnEfau5StJ6CuwK-jzDU";

let _fcmInitialized = false;

// ── Ringtone (Web Audio API) ───────────────────────────────────────────────
let _audioCtx     = null;
let _ringInterval = null;

function _getCtx() {
    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return _audioCtx;
}

function _beep(freq, startOffset, dur, vol = 0.5) {
    try {
        const ctx  = _getCtx();
        const osc  = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0, ctx.currentTime + startOffset);
        gain.gain.linearRampToValueAtTime(vol, ctx.currentTime + startOffset + 0.02);
        gain.gain.setValueAtTime(vol, ctx.currentTime + startOffset + dur - 0.05);
        gain.gain.linearRampToValueAtTime(0, ctx.currentTime + startOffset + dur);
        osc.start(ctx.currentTime + startOffset);
        osc.stop(ctx.currentTime + startOffset + dur);
    } catch(e) {}
}

// Phone double-ring pattern
function _playRing() {
    _beep(480, 0.0, 0.4, 0.6);
    _beep(440, 0.0, 0.4, 0.3);
    _beep(480, 0.5, 0.4, 0.6);
    _beep(440, 0.5, 0.4, 0.3);
}

function startRingtone() {
    stopRingtone();
    _playRing();
    _ringInterval = setInterval(_playRing, 1800);
}

function stopRingtone() {
    if (_ringInterval) { clearInterval(_ringInterval); _ringInterval = null; }
}

function playNotificationBeep() {
    _beep(660, 0, 0.15, 0.4);
    _beep(880, 0.18, 0.15, 0.3);
}

// ── WebSocket Client (Mechanic only) ──────────────────────────────────────
let _ws               = null;
let _wsGarageId       = null;
let _wsReconnectTimer = null;
let _wsPingInterval   = null;

function initWebSocket(garageId) {
    if (!garageId) return;
    _wsGarageId = garageId;
    _connectWS();
}

function _connectWS() {
    if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;

    const url = `${getWsBase()}/ws/mechanic/${_wsGarageId}`;
    _ws = new WebSocket(url);

    _ws.onopen = () => {
        console.log('WS connected ✅');
        // Ping every 30s to keep connection alive
        _wsPingInterval = setInterval(() => {
            if (_ws && _ws.readyState === WebSocket.OPEN) _ws.send('ping');
        }, 30000);
    };

    _ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'sos') {
                showIncomingCall(data.title, data.body, data);
            } else if (['webrtc_offer','webrtc_ice','webrtc_answer','webrtc_end'].includes(data.type)) {
                // WebRTC signaling — page-specific handler ko forward karo
                window.dispatchEvent(new CustomEvent('gnm_webrtc', { detail: data }));
            } else {
                playNotificationBeep();
                showFCMToast(data.title, data.body, data);
            }
        } catch(e) { /* pong ya kuch aur — ignore */ }
    };

    _ws.onclose = () => {
        console.log('WS disconnected — reconnecting in 5s...');
        clearInterval(_wsPingInterval);
        _wsReconnectTimer = setTimeout(_connectWS, 5000);
    };

    _ws.onerror = () => {
        _ws.close();
    };
}

// ── FCM Init ──────────────────────────────────────────────────────────────
async function initFCM(role = 'customer') {
    if (_fcmInitialized) return;
    if (!('serviceWorker' in navigator) || !('Notification' in window)) return;

    try {
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') { console.warn('Notification permission denied'); return; }

        const { initializeApp, getApps }           = await import('https://www.gstatic.com/firebasejs/9.23.0/firebase-app.js');
        const { getMessaging, getToken, onMessage } = await import('https://www.gstatic.com/firebasejs/9.23.0/firebase-messaging.js');

        const app       = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);
        const messaging = getMessaging(app);

        let swReg = await navigator.serviceWorker.register('/service-worker.js');
        await navigator.serviceWorker.ready;
        await swReg.update();

        let token;
        try {
            token = await getToken(messaging, { vapidKey: VAPID_KEY, serviceWorkerRegistration: swReg });
        } catch (tokenErr) {
            console.warn('FCM token retry...', tokenErr);
            await swReg.unregister();
            swReg = await navigator.serviceWorker.register('/service-worker.js');
            await navigator.serviceWorker.ready;
            token = await getToken(messaging, { vapidKey: VAPID_KEY, serviceWorkerRegistration: swReg });
        }

        if (!token) { console.warn('FCM token nahi mila'); return; }

        await saveFCMToken(token, role);
        _fcmInitialized = true;
        console.log('FCM initialized ✅');

        // Foreground message handler
        onMessage(messaging, payload => {
            console.log('FCM foreground payload:', payload);
            const title = payload.notification?.title || 'GarageNearMe';
            const body  = payload.notification?.body  || '';
            const data  = payload.data || {};

            if (data.type === 'sos') {
                showIncomingCall(title, body, data);
            } else {
                playNotificationBeep();
                showFCMToast(title, body, data);
            }
        });

    } catch (err) {
        console.error('FCM init error:', err);
    }
}

// ── FCM Token Save ─────────────────────────────────────────────────────────
async function saveFCMToken(fcmToken, role) {
    try {
        const authToken = localStorage.getItem('gnm_token') || localStorage.getItem('garage_token');
        if (!authToken) return;
        const endpoint = role === 'garage'
            ? `${getApiBase()}/garage-auth/fcm-token`
            : `${getApiBase()}/auth/fcm-token`;
        await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
            body: JSON.stringify({ fcm_token: fcmToken })
        });
        console.log('FCM token saved ✅');
    } catch (e) { console.error('FCM token save error:', e); }
}

// ── Incoming Call UI (SOS — foreground) ───────────────────────────────────
function showIncomingCall(title, body, data = {}) {
    const existing = document.getElementById('gnm-incoming-call');
    if (existing) existing.remove();
    startRingtone();

    const overlay = document.createElement('div');
    overlay.id = 'gnm-incoming-call';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:999999;background:#0a0a0a;display:flex;flex-direction:column;align-items:center;justify-content:space-between;padding:64px 24px 80px;';

    overlay.innerHTML = `
        <style>
            @keyframes gnmRingPulse {
                0%   { transform:scale(1);   opacity:0.7; }
                100% { transform:scale(1.7); opacity:0;   }
            }
            @keyframes gnmFadeIn {
                from { opacity:0; transform:translateY(20px); }
                to   { opacity:1; transform:translateY(0);    }
            }
            #gnm-incoming-call .ring-wrap {
                position:relative; width:130px; height:130px;
                display:flex; align-items:center; justify-content:center;
            }
            #gnm-incoming-call .ring-pulse {
                position:absolute; inset:0; border-radius:50%;
                border:2px solid #FF6B35;
                animation:gnmRingPulse 1.6s ease-out infinite;
            }
            #gnm-incoming-call .ring-pulse:nth-child(2){ animation-delay:0.5s; }
            #gnm-incoming-call .ring-pulse:nth-child(3){ animation-delay:1.0s; }
            #gnm-incoming-call .avatar {
                width:110px; height:110px; border-radius:50%;
                background:linear-gradient(135deg,#FF6B35,#e85d2a);
                display:flex; align-items:center; justify-content:center;
                font-size:46px; position:relative; z-index:1;
                box-shadow:0 0 40px rgba(255,107,53,0.4);
            }
            #gnm-incoming-call .call-info {
                text-align:center;
                animation:gnmFadeIn 0.4s ease;
            }
            #gnm-incoming-call .call-tag {
                display:inline-block;
                background:rgba(255,107,53,0.15); color:#FF6B35;
                border:1px solid rgba(255,107,53,0.3);
                border-radius:20px; padding:4px 14px;
                font-size:12px; letter-spacing:2px;
                font-family:'DM Sans',sans-serif;
                text-transform:uppercase; margin-bottom:16px;
            }
            #gnm-incoming-call .call-title {
                color:#fff; font-size:24px; font-weight:700;
                font-family:Syne,sans-serif; margin-bottom:10px;
                line-height:1.2;
            }
            #gnm-incoming-call .call-body {
                color:#9CA3AF; font-size:14px;
                font-family:'DM Sans',sans-serif; line-height:1.6;
                max-width:280px; margin:0 auto;
            }
            #gnm-incoming-call .actions {
                display:flex; gap:56px; align-items:flex-start; justify-content:center;
            }
            #gnm-incoming-call .action-wrap { text-align:center; }
            #gnm-incoming-call .btn-circle {
                width:72px; height:72px; border-radius:50%;
                border:none; cursor:pointer;
                display:flex; align-items:center; justify-content:center;
                transition:transform 0.15s;
            }
            #gnm-incoming-call .btn-circle:active { transform:scale(0.93); }
            #gnm-incoming-call .btn-decline {
                background:#E53E3E;
                box-shadow:0 0 0 10px rgba(229,62,62,0.15);
            }
            #gnm-incoming-call .btn-accept {
                background:#22C55E;
                box-shadow:0 0 0 10px rgba(34,197,94,0.15);
            }
            #gnm-incoming-call .btn-label {
                display:block; color:#6B7280; font-size:12px;
                font-family:'DM Sans',sans-serif; margin-top:10px;
            }
        </style>

        <div class="call-info">
            <div class="call-tag">🚨 SOS Emergency</div>
            <div class="call-title">${title || 'Nayi SOS Alert'}</div>
            <div class="call-body">${body || 'Koi mechanic ki madad maang raha hai!'}</div>
        </div>

        <div class="ring-wrap">
            <div class="ring-pulse"></div>
            <div class="ring-pulse"></div>
            <div class="ring-pulse"></div>
            <div class="avatar">🔧</div>
        </div>

        <div class="actions">
            <div class="action-wrap">
                <button class="btn-circle btn-decline" id="gnm-decline-btn">
                    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
                <span class="btn-label">Decline</span>
            </div>
            <div class="action-wrap">
                <button class="btn-circle btn-accept" id="gnm-accept-btn">
                    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.81 19.79 19.79 0 01.15 1.18 2 2 0 012.12 0h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 14.92z"/>
                    </svg>
                </button>
                <span class="btn-label">Accept</span>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    document.getElementById('gnm-accept-btn').onclick = () => {
        stopRingtone();
        overlay.remove();
        const screen = data.screen || 'sos-alerts';
        const m = ['bookings','sos-alerts','dashboard','services','earnings','payout-history','profile'];
        window.location.href = (m.includes(screen) || screen.startsWith('sos'))
            ? `/mechanic/${screen}` : `/${screen}`;
    };

    document.getElementById('gnm-decline-btn').onclick = () => {
        stopRingtone();
        overlay.remove();
    };
}

// ── Normal Toast (non-SOS foreground) ─────────────────────────────────────
function showFCMToast(title, body, data = {}) {
    let c = document.getElementById('fcm-toast-container');
    if (!c) {
        c = document.createElement('div');
        c.id = 'fcm-toast-container';
        c.style.cssText = 'position:fixed;top:80px;right:16px;z-index:99999;display:flex;flex-direction:column;gap:10px;';
        document.body.appendChild(c);
    }
    const t = document.createElement('div');
    t.style.cssText = 'background:#1B1F2E;color:#fff;border-radius:16px;padding:14px 18px;max-width:320px;box-shadow:0 8px 32px rgba(0,0,0,0.3);cursor:pointer;border-left:4px solid #FF6B35;animation:slideIn 0.3s ease;';
    t.innerHTML = `
        <div style="font-weight:700;font-size:14px;margin-bottom:4px;">🔔 ${title || 'GarageNearMe'}</div>
        <div style="font-size:13px;opacity:0.85;">${body || ''}</div>
    `;
    t.onclick = () => {
        const s = data.screen || '';
        if (s) {
            const m = ['bookings','sos-alerts','dashboard','services','earnings'];
            window.location.href = (m.includes(s) || s.startsWith('sos')) ? `/mechanic/${s}` : `/${s}`;
        }
        t.remove();
    };
    c.appendChild(t);
    setTimeout(() => { if (t.parentNode) t.remove(); }, 8000);
}

// ── Animations ─────────────────────────────────────────────────────────────
const _s = document.createElement('style');
_s.textContent = '@keyframes slideIn{from{transform:translateX(120%);opacity:0}to{transform:translateX(0);opacity:1}}';
document.head?.appendChild(_s);
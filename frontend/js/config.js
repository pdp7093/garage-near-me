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

// ── Incoming SOS Alert Toast (foreground) ─────────────────────────────────
function showIncomingCall(title, body, data = {}) {
    const existing = document.getElementById('gnm-sos-toast');
    if (existing) existing.remove();

    startRingtone();

    const toast = document.createElement('div');
    toast.id = 'gnm-sos-toast';
    toast.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:999999;width:calc(100% - 32px);max-width:480px;background:#DC2626;color:#fff;border-radius:16px;padding:16px 20px;box-shadow:0 8px 32px rgba(220,38,38,0.4);display:flex;align-items:center;gap:14px;cursor:pointer;';

    toast.innerHTML = `
        <style>
            @keyframes sosSlideIn{from{opacity:0;transform:translateX(-50%) translateY(-20px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
            @keyframes sosPulse{0%,100%{opacity:1}50%{opacity:0.6}}
            #gnm-sos-toast{animation:sosSlideIn 0.3s ease;}
            #gnm-sos-toast .si{font-size:28px;flex-shrink:0;animation:sosPulse 1s infinite;}
            #gnm-sos-toast .st{flex:1;}
            #gnm-sos-toast .stitle{font-weight:700;font-size:14px;margin-bottom:2px;}
            #gnm-sos-toast .sbody{font-size:12px;opacity:0.9;}
            #gnm-sos-toast .sbtn{background:rgba(255,255,255,0.2);border:none;color:#fff;border-radius:8px;padding:6px 12px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;}
            #gnm-sos-toast .sclose{background:none;border:none;color:rgba(255,255,255,0.7);font-size:18px;cursor:pointer;padding:0 4px;}
        </style>
        <div class="si">🚨</div>
        <div class="st">
            <div class="stitle">${title || 'New SOS Alert!'}</div>
            <div class="sbody">${body || 'Koi breakdown mein hai!'}</div>
        </div>
        <button class="sbtn" id="gnm-sos-view">View SOS</button>
        <button class="sclose" id="gnm-sos-dismiss">✕</button>
    `;

    document.body.appendChild(toast);

    document.getElementById('gnm-sos-view').onclick = (e) => {
        e.stopPropagation();
        stopRingtone();
        toast.remove();
        window.location.href = '/mechanic/sos-alerts';
    };
    document.getElementById('gnm-sos-dismiss').onclick = (e) => {
        e.stopPropagation();
        stopRingtone();
        toast.remove();
    };
    toast.onclick = () => {
        stopRingtone();
        toast.remove();
        window.location.href = '/mechanic/sos-alerts';
    };
    setTimeout(() => { if (toast.parentNode) { stopRingtone(); toast.remove(); } }, 30000);
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
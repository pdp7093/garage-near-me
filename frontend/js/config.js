// One-time cleanup: purana PWA Service Worker unregister karo
// (Web-FCM/PWA se native Capacitor push par migrate ho chuke hain, isliye
// purane devices par pehle se registered service worker hata rahe hain)
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(function(registrations) {
    for (let registration of registrations) {
      registration.unregister();
      console.log('[Cleanup] Old service worker unregistered:', registration.scope);
    }
  }).catch(function(err) {
    console.warn('[Cleanup] Service worker cleanup failed:', err);
  });
}

function getApiBase() {
    // Capacitor native app check
    if (window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()) {
        return "https://garagenearme.net/api";
    }
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") return "http://localhost:8000/api";
    if (/^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host)) {
        return `http://${host}:8000/api`;
    }
    return window.location.origin + "/api";
}

function getWsBase() {
    // Capacitor native app check
    if (window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()) {
        return "wss://garagenearme.net";
    }
    const host = window.location.hostname;
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    if (host === "localhost" || host === "127.0.0.1") return `ws://localhost:8000`;
    if (/^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host)) return `ws://${host}:8000`;
    return `${proto}://${window.location.host}`;
}

// ── Ringtone (Web Audio API) ───────────────────────────────────────────────
let _audioCtx = null;
let _ringInterval = null;

function _getCtx() {
    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return _audioCtx;
}

function _beep(freq, startOffset, dur, vol = 0.5) {
    try {
        const ctx = _getCtx();
        const osc = ctx.createOscillator();
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
    } catch (e) { }
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
let _ws = null;
let _wsGarageId = null;
let _wsReconnectTimer = null;
let _wsPingInterval = null;

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
            } else if (['webrtc_offer', 'webrtc_ice', 'webrtc_answer', 'webrtc_end'].includes(data.type)) {
                // WebRTC signaling — page-specific handler ko forward karo
                window.dispatchEvent(new CustomEvent('gnm_webrtc', { detail: data }));
            } else {
                playNotificationBeep();
                showFCMToast(data.title, data.body, data);
            }
        } catch (e) { /* pong ya kuch aur — ignore */ }
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

// ── Incoming SOS Alert Toast (foreground) ─────────────────────────────────
function showIncomingCall(title, body, data = {}) {
    const sosId = data.sos_id;

    // Check if dismissed recently (within 30 seconds)
    if (sosId) {
        const dismissed = JSON.parse(localStorage.getItem('dismissed_sos_toast') || '{}');
        if (dismissed[sosId] && (Date.now() - dismissed[sosId] < 30 * 1000)) {
            return; // Skip showing toast if dismissed within last 30 seconds
        }
    }

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
        window.location.href = '/mechanic/sos-alerts.html';
    };
    document.getElementById('gnm-sos-dismiss').onclick = (e) => {
        e.stopPropagation();
        stopRingtone();
        toast.remove();
        if (sosId) {
            const dismissed = JSON.parse(localStorage.getItem('dismissed_sos_toast') || '{}');
            dismissed[sosId] = Date.now();
            localStorage.setItem('dismissed_sos_toast', JSON.stringify(dismissed));
        }
    };
    toast.onclick = () => {
        stopRingtone();
        toast.remove();
        window.location.href = '/mechanic/sos-alerts.html';
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
            const m = ['bookings', 'sos-alerts', 'dashboard', 'services', 'earnings'];
            window.location.href = (m.includes(s) || s.startsWith('sos')) ? `/mechanic/${s}.html` : `/${s}.html`;
        }
        t.remove();
    };
    c.appendChild(t);
    setTimeout(() => { if (t.parentElement) t.remove(); }, 5000);
}

// ── Global SOS Polling (Fallback if FCM is not active) ────────────────────
function startGlobalSOSPolling() {
    const token = localStorage.getItem('garage_token');
    if (!token) return;

    setInterval(async () => {
        try {
            const res = await fetch(`${getApiBase()}/sos/active`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!res.ok) return;
            const alerts = await res.json();
            const activeAlerts = alerts.filter(a => a.status === 'broadcasting');

            if (activeAlerts.length > 0) {
                const latest = activeAlerts[0];
                const declined = JSON.parse(localStorage.getItem('declined_sos') || '[]');
                if (!declined.includes(latest.id)) {
                    // Only show if we haven't dismissed it
                    const dismissed = JSON.parse(localStorage.getItem('dismissed_sos_toast') || '{}');
                    if (!dismissed[latest.id] || (Date.now() - dismissed[latest.id] > 30 * 1000)) {
                        const vt = latest.vehicle_type === 'two_wheeler' ? '🏍️ 2 Wheeler' : latest.vehicle_type === 'four_wheeler' ? '🚗 4 Wheeler' : latest.vehicle_type;
                        showIncomingCall(`SOS #${latest.id}`, `${vt} breakdown near you!`, { sos_id: latest.id });
                    }
                }
            }
        } catch (e) {
            // Ignore polling errors
        }
    }, 10000); // Check every 10 seconds globally
}

// Start global polling automatically if logged in as mechanic
if (localStorage.getItem('garage_token') && window.location.pathname.startsWith('/mechanic')) {
    setTimeout(startGlobalSOSPolling, 3000);
}

// ── Animations ─────────────────────────────────────────────────────────────
const _s = document.createElement('style');
_s.textContent = '@keyframes slideIn{from{transform:translateX(120%);opacity:0}to{transform:translateX(0);opacity:1}}';
document.head?.appendChild(_s);
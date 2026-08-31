/**
 * mechanic-auth.js
 * Session and authentication management for mechanic portal
 */



const MECHANIC_AUTH = {
  isLoggedIn() {
    return !!localStorage.getItem('garage_token');
  },

  getToken() {
    return localStorage.getItem('garage_token');
  },

  getMechanicInfo() {
    const info = localStorage.getItem('mechanic_info');
    return info ? JSON.parse(info) : null;
  },

  setSession(token, mechnicInfo) {
    localStorage.setItem('garage_token', token);
    if (mechnicInfo) {
      localStorage.setItem('mechanic_info', JSON.stringify(mechnicInfo));
    }
  },

  logout() {
    localStorage.removeItem('garage_token');
    localStorage.removeItem('mechanic_info');
    window.location.href = '/mechanic/';
  },

  checkSession() {
    if (!this.isLoggedIn()) {
      window.location.href = '/mechanic/';
      return false;
    }
    return true;
  },

  async verifyToken() {
    const token = this.getToken();
    if (!token) {
      this.clearSession();
      return false;
    }

    try {
      const response = await fetch(getApiBase() + '/garage-auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        this.clearSession();
        return false;
      }

      return true;
    } catch (error) {
      console.error('Token verification failed:', error);
      this.clearSession();
      return false;
    }
  },

  clearSession() {
    localStorage.removeItem('garage_token');
    localStorage.removeItem('mechanic_info');
  }
};

// ── WebSocket — real-time SOS notifications (app open hone par) ───────────
let _mechanicWs = null;
let _mechanicWsReconnectTimer = null;
let _mechanicWsPingTimer = null;

function _getGarageIdFromToken() {
  const token = localStorage.getItem('garage_token');
  if (!token) return null;
  try { return JSON.parse(atob(token.split('.')[1])).user_id || null; } catch (e) { return null; }
}

function connectMechanicSosWS() {
  const garageId = _getGarageIdFromToken();
  if (!garageId) { console.warn('[SOS-WS] garageId nahi mila token se'); return; }

  const base = (typeof getWsBase === 'function') ? getWsBase() : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
  const url = `${base}/ws/mechanic/${garageId}`;

  console.log(`[SOS-WS] Connecting → ${url}`);
  _mechanicWs = new WebSocket(url);

  _mechanicWs.onopen = () => {
    console.log(`[SOS-WS] Connected ✅ garage_id=${garageId}`);
    if (_mechanicWsReconnectTimer) { clearTimeout(_mechanicWsReconnectTimer); _mechanicWsReconnectTimer = null; }
    if (_mechanicWsPingTimer) clearInterval(_mechanicWsPingTimer);
    _mechanicWsPingTimer = setInterval(() => {
      if (_mechanicWs && _mechanicWs.readyState === WebSocket.OPEN) _mechanicWs.send('ping');
    }, 25000);
  };

  _mechanicWs.onmessage = (e) => {
    if (e.data === 'pong') return;
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'sos_alert') {
        console.log('[SOS-WS] sos_alert mila:', data);
        if (typeof showIncomingCall === 'function') {
          showIncomingCall(data.title || 'SOS Emergency!', data.body || 'Koi breakdown mein hai!', data);
        }
        if (typeof loadSOSAlerts === 'function') {
          loadSOSAlerts(true);
        }
      } else if (data.type === 'sos_cancelled') {
        console.log('[SOS-WS] sos_cancelled mila:', data);
        if (typeof loadSOSAlerts === 'function') {
          loadSOSAlerts(true);
        }
      }
    } catch (err) { console.error('[SOS-WS] parse error:', err); }
  };

  _mechanicWs.onclose = (e) => {
    console.log(`[SOS-WS] Disconnected (code=${e.code}) — 7s mein reconnect`);
    if (_mechanicWsPingTimer) { clearInterval(_mechanicWsPingTimer); _mechanicWsPingTimer = null; }
    _mechanicWsReconnectTimer = setTimeout(connectMechanicSosWS, 7000);
  };
  _mechanicWs.onerror = (e) => { console.error('[SOS-WS] Error:', e); _mechanicWs.close(); };
}

// Automatically check session on page load for protected pages
window.addEventListener('DOMContentLoaded', async function () {
  const currentPage = window.location.pathname.split('/').pop() || '';

  if (currentPage === 'index' || currentPage === '') {
    return;
  }

  if (!MECHANIC_AUTH.isLoggedIn()) {
    window.location.href = '/mechanic/';
    return;
  }

  const isValid = await MECHANIC_AUTH.verifyToken();
  if (!isValid) {
    MECHANIC_AUTH.logout();
    return;
  }

  connectMechanicSosWS();
  initCapacitorPushNotifications();
});

// ── Capacitor Push Notifications (native — app kill state mein bhi kaam karta hai) ──
async function initCapacitorPushNotifications() {
  if (typeof window.Capacitor === 'undefined' || !window.Capacitor.isNativePlatform || !window.Capacitor.isNativePlatform()) {
    console.log('[Push] Not running on a native Capacitor platform, skipping push setup.');
    return;
  }

  try {
    const { PushNotifications } = window.Capacitor.Plugins;
    if (!PushNotifications) {
      console.warn('[Push] PushNotifications plugin not found on Capacitor.Plugins');
      return;
    }

    let permStatus = await PushNotifications.checkPermissions();
    if (permStatus.receive === 'prompt') {
      permStatus = await PushNotifications.requestPermissions();
    }

    if (permStatus.receive !== 'granted') {
      console.warn('[Push] Permission denied');
      return;
    }

    // High-priority Android notification channel — background/kill state mein
    // sound + heads-up popup guarantee karne ke liye.
    try {
      await PushNotifications.createChannel({
        id: 'sos_alerts',
        name: 'SOS Emergency Alerts',
        description: 'High priority emergency breakdown alerts',
        importance: 5,       // IMPORTANCE_HIGH
        visibility: 1,       // VISIBILITY_PUBLIC
        sound: 'default',
        vibration: true,
        lights: true
      });
      console.log('[Push] SOS notification channel created ✅');
    } catch (chErr) {
      console.warn('[Push] Channel creation skipped/failed:', chErr);
    }

    await PushNotifications.register();

    PushNotifications.addListener('registration', async (token) => {
      console.log('[Push] FCM Token: ' + token.value);
      const authToken = MECHANIC_AUTH.getToken();
      if (authToken) {
        try {
          await fetch(getApiBase() + '/garage-auth/fcm-token', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({ fcm_token: token.value })
          });
          console.log('[Push] Token saved in backend!');
        } catch (e) {
          console.error('[Push] Failed to send token', e);
        }
      }
    });

    PushNotifications.addListener('registrationError', (error) => {
      console.error('[Push] Registration error: ', error);
    });

    PushNotifications.addListener('pushNotificationReceived', (notification) => {
      console.log('[Push] Received: ', notification);
      if (typeof loadSOSAlerts === 'function') {
        loadSOSAlerts(true);
      }
    });

    PushNotifications.addListener('pushNotificationActionPerformed', (notification) => {
      console.log('[Push] Action performed: ', notification);
      window.location.href = '/mechanic/dashboard.html';
    });

  } catch (error) {
    console.error('[Push] setup error:', error);
  }
}
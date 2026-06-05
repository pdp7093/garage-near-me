/**
 * mechanic-auth.js
 * Session and authentication management for mechanic portal
 */



const MECHANIC_AUTH = {
  // Check if user is logged in
  isLoggedIn() {
    return !!localStorage.getItem('garage_token');
  },

  // Get stored token
  getToken() {
    return localStorage.getItem('garage_token');
  },

  // Get mechanic info from session
  getMechanicInfo() {
    const info = localStorage.getItem('mechanic_info');
    return info ? JSON.parse(info) : null;
  },

  // Store login session
  setSession(token, mechnicInfo) {
    localStorage.setItem('garage_token', token);
    if (mechnicInfo) {
      localStorage.setItem('mechanic_info', JSON.stringify(mechnicInfo));
    }
  },

  // Clear session on logout
  logout() {
    localStorage.removeItem('garage_token');
    localStorage.removeItem('mechanic_info');
    window.location.href = 'index';
  },

  // Check if session is valid, redirect to login if not
  checkSession() {
    if (!this.isLoggedIn()) {
      window.location.href = 'index';
      return false;
    }
    return true;
  },

  // Verify token with backend
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

  // Clear session data
  clearSession() {
    localStorage.removeItem('garage_token');
    localStorage.removeItem('mechanic_info');
  }
};

// ── WebSocket — real-time SOS notifications ───────────────────────────────
let _mechanicWs                  = null;
let _mechanicWsReconnectTimer    = null;
let _mechanicWsPingTimer         = null;

function _getGarageIdFromToken() {
  const token = localStorage.getItem('garage_token');
  if (!token) return null;
  try { return JSON.parse(atob(token.split('.')[1])).user_id || null; } catch(e) { return null; }
}

function connectMechanicSosWS() {
  const garageId = _getGarageIdFromToken();
  if (!garageId) { console.warn('[SOS-WS] garageId nahi mila token se'); return; }

  // getWsBase() config.js mein hai — localhost/LAN/ngrok sab handle karta hai
  const base = (typeof getWsBase === 'function') ? getWsBase() : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
  const url  = `${base}/ws/mechanic/${garageId}`;

  console.log(`[SOS-WS] Connecting → ${url}`);
  _mechanicWs = new WebSocket(url);

  _mechanicWs.onopen = () => {
    console.log(`[SOS-WS] Connected ✅ garage_id=${garageId}`);
    if (_mechanicWsReconnectTimer) { clearTimeout(_mechanicWsReconnectTimer); _mechanicWsReconnectTimer = null; }
    // Keepalive — connection zinda rakho
    if (_mechanicWsPingTimer) clearInterval(_mechanicWsPingTimer);
    _mechanicWsPingTimer = setInterval(() => {
      if (_mechanicWs && _mechanicWs.readyState === WebSocket.OPEN) _mechanicWs.send('ping');
    }, 25000);
  };

  _mechanicWs.onmessage = (e) => {
    if (e.data === 'pong') return;
    try {
      const data = JSON.parse(e.data);
      if (data.type !== 'sos_alert') return;
      console.log('[SOS-WS] sos_alert mila:', data);

      // Hamesha overlay dikhao — chahe koi bhi page ho
      if (typeof showIncomingCall === 'function') {
        showIncomingCall(data.title || 'SOS Emergency!', data.body || 'Koi breakdown mein hai!', data);
      }
      // Sos-alerts page pe hain — list bhi refresh karo
      if (typeof loadSOSAlerts === 'function') {
        loadSOSAlerts(true);
      }
    } catch(err) { console.error('[SOS-WS] parse error:', err); }
  };

  _mechanicWs.onclose  = (e) => {
    console.log(`[SOS-WS] Disconnected (code=${e.code}) — 7s mein reconnect`);
    if (_mechanicWsPingTimer) { clearInterval(_mechanicWsPingTimer); _mechanicWsPingTimer = null; }
    _mechanicWsReconnectTimer = setTimeout(connectMechanicSosWS, 7000);
  };
  _mechanicWs.onerror  = (e) => { console.error('[SOS-WS] Error:', e); _mechanicWs.close(); };
}

// Automatically check session on page load for protected pages
window.addEventListener('DOMContentLoaded', function() {
  // Only check on protected mechanic pages (not on index.html)
  const currentPage = window.location.pathname.split('/').pop() || '';

  // Skip session check on login/index pages
  if (currentPage === 'index' || currentPage === '') {
    return;
  }

  // For all other mechanic pages, enforce session check
  if (!MECHANIC_AUTH.isLoggedIn()) {
    window.location.href = 'index';
    return;
  }

  // Real-time SOS notification ke liye WebSocket connect karo
  connectMechanicSosWS();
});

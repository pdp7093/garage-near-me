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
    window.location.href = '/mechanic/index.html';
  },

  checkSession() {
    if (!this.isLoggedIn()) {
      window.location.href = '/mechanic/index.html';
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
        headers: {
          'ngrok-skip-browser-warning': '69420',
          'Authorization': `Bearer ${token}`
        }
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

  // Sequential order zaroori hai — ek dialog complete hone ke baad hi
  // agla dialog trigger karna hai, warna Android kuch dialogs silently
  // skip kar deta hai jab multiple permission requests overlap hoti hain.
  await requestCapacitorLocationPermission();
  await requestCapacitorPushPermission();
  await requestBatteryOptimizationExemption();
  connectMechanicWS();
  checkForAppUpdate();
});

// ── Capacitor Location Permission Request ──
async function requestCapacitorLocationPermission() {
  if (typeof window.Capacitor === 'undefined' || !window.Capacitor.isNativePlatform || !window.Capacitor.isNativePlatform()) {
    return;
  }
  try {
    const { Geolocation } = window.Capacitor.Plugins;
    if (Geolocation) {
      let geoPerm = await Geolocation.checkPermissions();
      if (geoPerm.location === 'prompt' || geoPerm.location === 'prompt-with-rationale') {
        await Geolocation.requestPermissions();
      }
    }
  } catch (err) {
    console.warn('[Location] Failed to request location permission', err);
  }
}

// ── Battery Optimization Exemption (WhatsApp jaisa background reliability) ──
async function requestBatteryOptimizationExemption() {
  if (typeof window.Capacitor === 'undefined' || !window.Capacitor.isNativePlatform || !window.Capacitor.isNativePlatform()) {
    return;
  }
  try {
    const { BatteryOptimization } = window.Capacitor.Plugins;
    if (!BatteryOptimization) {
      console.warn('[Battery] BatteryOptimization plugin not found');
      return;
    }

    const { enabled } = await BatteryOptimization.isBatteryOptimizationEnabled();
    if (enabled) {
      console.log('[Battery] Optimization is ON — requesting exemption...');
      await BatteryOptimization.requestIgnoreBatteryOptimization();
    } else {
      console.log('[Battery] Already exempted ✅');
    }
  } catch (err) {
    console.warn('[Battery] Exemption request failed:', err);
  }
}

// ── Helper: Notification data se sahi page pe navigate karo ──
function navigateFromNotificationData(data) {
  if (!data) {
    window.location.href = '/mechanic/dashboard.html';
    return;
  }
  if ((data.type === 'sos_alert' || data.type === 'call-request') && data.sos_id) {
    const targetUrl = `/mechanic/sos-detail.html?id=${data.sos_id}`;
    // Agar same page pe hain, to reload mat karo taaki ringing call UI gayab na ho
    if (window.location.pathname.includes('sos-detail') && window.location.search.includes(`id=${data.sos_id}`)) {
      return;
    }
    window.location.href = targetUrl;
  } else if (data.screen) {
    window.location.href = `/mechanic/${data.screen}.html`;
  } else {
    window.location.href = '/mechanic/dashboard.html';
  }
}

// ── Capacitor Push Notification Permission Request ──
async function requestCapacitorPushPermission() {
  if (typeof window.Capacitor === 'undefined' || !window.Capacitor.isNativePlatform || !window.Capacitor.isNativePlatform()) {
    return;
  }
  try {
    const { PushNotifications, LocalNotifications } = window.Capacitor.Plugins;
    if (!PushNotifications) return;

    let pushPerm = await PushNotifications.checkPermissions();
    if (pushPerm.receive === 'prompt' || pushPerm.receive === 'prompt-with-rationale') {
      pushPerm = await PushNotifications.requestPermissions();
    }

    if (pushPerm.receive !== 'granted') {
      console.warn('[Push] Permission not granted:', pushPerm.receive);
      return;
    }

    // ── PHASE 2: High-priority notification channel (native FCM push ke liye — background/kill) ──
    // SOS wala channel — ISKO TOUCH NAHI KARNA, already tested aur working hai
    try {
      await PushNotifications.createChannel({
        id: 'sos_alerts_loud',
        name: 'SOS Emergency Alerts LOUD',
        description: 'High priority emergency breakdown alerts',
        importance: 5,       // IMPORTANCE_HIGH (heads-up + sound)
        visibility: 1,       // VISIBILITY_PUBLIC (lock screen pe bhi dikhe)
        sound: 'notification.mp3',
        vibration: true,
        lights: true
      });
      console.log('[Push] Notification channel "sos_alerts" created ✅');
    } catch (chErr) {
      console.warn('[Push] Channel creation failed:', chErr);
    }

    // ── NAYA: Booking alerts channel — SOS se alag, normal booking updates ke liye ──
    try {
      await PushNotifications.createChannel({
        id: 'booking_alerts',
        name: 'Booking Updates',
        description: 'New booking, accept, estimate, and status alerts',
        importance: 4,       // IMPORTANCE_HIGH (heads-up milega, SOS se thoda kam)
        visibility: 1,
        sound: 'default',
        vibration: true,
        lights: true
      });
      console.log('[Push] Notification channel "booking_alerts" created ✅');
    } catch (chErr) {
      console.warn('[Push] Booking channel creation failed:', chErr);
    }

    // ── PHASE 4: Local Notifications — ALAG channel ID, taaki PushNotifications
    // wale channel se conflict na ho ──
    if (LocalNotifications) {
      try {
        let localPerm = await LocalNotifications.checkPermissions();
        if (localPerm.display === 'prompt' || localPerm.display === 'prompt-with-rationale') {
          localPerm = await LocalNotifications.requestPermissions();
        }
        await LocalNotifications.createChannel({
          id: 'sos_alerts_local',
          name: 'SOS Emergency Alerts (Foreground)',
          description: 'High priority emergency breakdown alerts',
          importance: 5,
          visibility: 1,
          sound: 'default',
          vibration: true,
          lights: true
        });
        console.log('[LocalNotif] Channel "sos_alerts_local" created ✅');
      } catch (lnErr) {
        console.warn('[LocalNotif] Setup failed:', lnErr);
      }
    }

    await PushNotifications.register();

    PushNotifications.addListener('registration', async (token) => {
      console.log('[Push] Token received: ' + token.value);
      const authToken = MECHANIC_AUTH.getToken();
      if (!authToken) return;
      try {
        await fetch(getApiBase() + '/garage-auth/fcm-token', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${authToken}`
          },
          body: JSON.stringify({ fcm_token: token.value })
        });
        console.log('[Push] Token saved in backend');
      } catch (e) {
        console.error('[Push] Failed to save token:', e);
      }
    });

    PushNotifications.addListener('registrationError', (error) => {
      console.error('[Push] Registration error:', error);
    });

    // ── PHASE 4: Foreground push aane par manually notification dikhao ──
    PushNotifications.addListener('pushNotificationReceived', async (notification) => {
      console.log('[Push] Foreground notification received:', notification);
      if (LocalNotifications) {
        try {
          await LocalNotifications.schedule({
            notifications: [
              {
                id: Math.floor(Math.random() * 100000),
                title: notification.title || 'GarageNearMe',
                body: notification.body || '',
                channelId: 'sos_alerts_local',
                extra: notification.data || {}
              }
            ]
          });
        } catch (lnErr) {
          console.error('[LocalNotif] Failed to show foreground notification:', lnErr);
        }
      }
    });

    // ── Native push notification TAP hone par (background/killed state se app khulne par) ──
    // SOS alert ho to seedha sos-alerts page pe le jao, us specific SOS ID ke saath
    PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
      console.log('[Push] Action performed: ', action);
      const data = action.notification?.data;
      navigateFromNotificationData(data);
    });

    // ── Foreground wali LocalNotification TAP hone par ──
    if (LocalNotifications) {
      LocalNotifications.addListener('localNotificationActionPerformed', (action) => {
        console.log('[LocalNotif] Action performed: ', action);
        const data = action.notification?.extra;
        navigateFromNotificationData(data);
      });
    }

  } catch (err) {
    console.warn('[Push] Failed to request push permission', err);
  }
}

// ── WebSocket connection — WebRTC call signaling ke liye zaroori ──
let _ws = null;
let _wsReconnectTimer = null;

function _getGarageIdFromToken() {
  const token = localStorage.getItem('garage_token');
  if (!token) return null;
  try { return JSON.parse(atob(token.split('.')[1])).user_id || null; } catch (e) { return null; }
}

function connectMechanicWS() {
  const garageId = _getGarageIdFromToken();
  if (!garageId) return;

  const base = (typeof getWsBase === 'function') ? getWsBase() : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
  const url = `${base}/ws/mechanic/${garageId}`;

  _ws = new WebSocket(url);

  _ws.onopen = () => {
    console.log('[WS] Connected ✅');
  };

  _ws.onmessage = (e) => {
    if (e.data === 'pong') return;
    try {
      const data = JSON.parse(e.data);
      if (['webrtc_offer', 'webrtc_ice', 'webrtc_answer', 'webrtc_end'].includes(data.type)) {
        window.dispatchEvent(new CustomEvent('gnm_webrtc', { detail: data }));
      }
    } catch (err) { console.error('[WS] parse error:', err); }
  };

  _ws.onclose = () => {
    console.log('[WS] Disconnected — 5s mein reconnect');
    _wsReconnectTimer = setTimeout(connectMechanicWS, 5000);
  };
  _ws.onerror = () => { _ws.close(); };
}

// ── App Version Check (sideload distribution ke liye — Play Store nahi hai) ──
async function checkForAppUpdate() {
  if (typeof window.Capacitor === 'undefined' || !window.Capacitor.isNativePlatform || !window.Capacitor.isNativePlatform()) {
    return;
  }
  try {
    const { App } = window.Capacitor.Plugins;
    if (!App) return;

    const info = await App.getInfo();
    const currentVersion = info.version;

    const res = await fetch(getApiBase() + '/app-version/mechanic-latest', {
      headers: { 'ngrok-skip-browser-warning': '69420' }
    });
    if (!res.ok) return;
    const data = await res.json();

    if (data.latest_version && data.latest_version !== currentVersion) {
      showUpdateBanner(data.download_url, data.latest_version);
    }
  } catch (err) {
    console.warn('[Update Check] Failed:', err);
  }
}

function showUpdateBanner(downloadUrl, latestVersion) {
  if (document.getElementById('gnm-update-banner')) return; // already shown

  const banner = document.createElement('div');
  banner.id = 'gnm-update-banner';
  banner.style.cssText = 'position:fixed; bottom:0; left:0; width:100%; background:#0B1220; color:white; z-index:999999; padding:14px 20px; display:flex; align-items:center; justify-content:space-between; gap:12px; box-shadow:0 -4px 12px rgba(0,0,0,0.2); font-family:sans-serif;';
  banner.innerHTML = `
    <span style="font-size:14px;">🔔 Naya update (v${latestVersion}) available hai!</span>
    <button id="gnm-update-btn" style="background:#FF6B35; color:white; border:none; padding:8px 16px; border-radius:20px; font-weight:bold; font-size:13px;">Update Karo</button>
  `;
  document.body.appendChild(banner);

  document.getElementById('gnm-update-btn').addEventListener('click', () => {
    window.open(downloadUrl, '_system');
  });
}
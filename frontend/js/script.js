// GarageNearMe — script.js

// ── GPS location detect ─────────────────
const gpsBtn = document.getElementById('gpsBtn');
const locationInput = document.getElementById('locationInput');
if (gpsBtn && locationInput) {
  const LOCATION_STORAGE_KEY = 'gnm_customer_location';
  const LOCATION_PROMPT_SESSION_KEY = 'gnm_location_prompted';

  function isGeolocationAllowedHere() {
    return window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname);
  }

  function rememberLocation(pos) {
    const payload = {
      lat: pos.coords.latitude,
      lng: pos.coords.longitude,
      accuracy: pos.coords.accuracy,
      saved_at: Date.now()
    };
    localStorage.setItem(LOCATION_STORAGE_KEY, JSON.stringify(payload));
    locationInput.value = 'Current location detected';
  }

  function requestLocation(showAlert) {
    if (!navigator.geolocation) {
      if (showAlert) alert('Geolocation is not supported by your browser.');
      return;
    }

    if (!isGeolocationAllowedHere()) {
      if (showAlert) alert('Location permission only works on HTTPS or localhost.');
      return;
    }

    gpsBtn.style.opacity = '0.4';
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        rememberLocation(pos);
        gpsBtn.style.opacity = '1';
      },
      function () {
        if (showAlert) alert('Could not detect location. Please type your area.');
        gpsBtn.style.opacity = '1';
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
    );
  }

  try {
    const cached = JSON.parse(localStorage.getItem(LOCATION_STORAGE_KEY) || 'null');
    if (cached && Number.isFinite(cached.lat) && Number.isFinite(cached.lng)) {
      locationInput.value = 'Current location detected';
    }
  } catch { }

  gpsBtn.addEventListener('click', function () {
    requestLocation(true);
  });

  if (
    !locationInput.value &&
    !sessionStorage.getItem(LOCATION_PROMPT_SESSION_KEY) &&
    isGeolocationAllowedHere()
  ) {
    sessionStorage.setItem(LOCATION_PROMPT_SESSION_KEY, '1');
    setTimeout(() => requestLocation(false), 600);
  }
}

// ── SOS button ──────────────────────────
const sosBtn = document.getElementById('sosBtn');
if (sosBtn) {
  sosBtn.addEventListener('click', function () {
    window.location.href = '/customer/sos.html';
  });
}

// ── Customer Capacitor Setup (sequential permissions + FCM) ─────
document.addEventListener('DOMContentLoaded', async () => {
  if (!window?.Capacitor?.isNativePlatform?.()) return;

  const { Geolocation, PushNotifications, LocalNotifications } = window.Capacitor.Plugins;

  // ── STEP 1: Location permission (pehle) ──
  if (Geolocation) {
    try {
      let locPerm = await Geolocation.checkPermissions();
      if (locPerm.location === 'prompt' || locPerm.location === 'prompt-with-rationale') {
        await Geolocation.requestPermissions({ permissions: ['location'] });
      }
    } catch (e) {
      console.warn('[GNM] Geolocation permission error:', e);
    }
  }

  // ── STEP 2: Push Notifications permission (baad me, sequential) ──
  if (!PushNotifications) return;

  try {
    let pushPerm = await PushNotifications.checkPermissions();
    if (pushPerm.receive === 'prompt' || pushPerm.receive === 'prompt-with-rationale') {
      pushPerm = await PushNotifications.requestPermissions();
    }
    if (pushPerm.receive !== 'granted') {
      console.warn('[GNM] Push permission not granted');
      return;
    }
  } catch (e) {
    console.warn('[GNM] Push permission error:', e);
    return;
  }

  // ── STEP 3: customer_updates notification channel ──
  try {
    await PushNotifications.createChannel({
      id: 'customer_updates',
      name: 'Customer Updates',
      description: 'Booking accepted, mechanic on the way, SOS accepted alerts',
      importance: 4,
      visibility: 1,
      sound: 'default',
      vibration: true,
      lights: true
    });
    console.log('[GNM] Notification channel "customer_updates" created ✅');
  } catch (chErr) {
    console.warn('[GNM] Channel creation failed:', chErr);
  }

  // ── STEP 4: Local Notifications channel ──
  if (LocalNotifications) {
    try {
      let localPerm = await LocalNotifications.checkPermissions();
      if (localPerm.display === 'prompt' || localPerm.display === 'prompt-with-rationale') {
        await LocalNotifications.requestPermissions();
      }
    } catch (lnErr) {
      console.warn('[GNM] LocalNotifications setup failed:', lnErr);
    }
  }

  // ── STEP 5: Register FCM token ──
  await PushNotifications.register();

  PushNotifications.addListener('registration', async (token) => {
    console.log('[GNM] FCM Token received:', token.value);
    const authToken = localStorage.getItem('gnm_token');
    if (!authToken) return;
    try {
      const apiBase = typeof getApiBase === 'function' ? getApiBase() : 'https://garagenearme.net/api';
      await fetch(`${apiBase}/auth/fcm-token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({ fcm_token: token.value })
      });
      console.log('[GNM] FCM token saved to backend ✅');
    } catch (err) {
      console.warn('[GNM] FCM token save failed:', err);
    }
  });

  PushNotifications.addListener('registrationError', (error) => {
    console.warn('[GNM] FCM registration error:', error);
  });

  // ── STEP 6: Handle incoming push (foreground) ──
  PushNotifications.addListener('pushNotificationReceived', (notification) => {
    console.log('[GNM] Push received in foreground:', notification);
    // LocalNotification se foreground mein bhi dikhaao
    if (LocalNotifications) {
      LocalNotifications.schedule({
        notifications: [{
          title: notification.title || 'GarageNearMe',
          body: notification.body || '',
          id: Date.now(),
          schedule: { at: new Date(Date.now() + 300) },
          channelId: 'customer_updates'
        }]
      }).catch(() => {});
    }
  });

  // ── STEP 7: Push tap → navigate ──
  PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
    const data = action?.notification?.data || {};
    const screen = data.screen;
    const bookingId = data.booking_id;
    const sosId = data.sos_id;
    if (screen === 'booking-detail' && bookingId) {
      window.location.href = `/customer/booking-detail.html?id=${bookingId}`;
    } else if (screen === 'sos-tracking' && sosId) {
      window.location.href = `/customer/sos-tracking.html?id=${sosId}`;
    }
  });
});

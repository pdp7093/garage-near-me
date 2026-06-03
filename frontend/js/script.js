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
  } catch {}

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
    alert('SOS Alert Sent!\n\nNearby mechanics are being notified.\nPlease stay at your location.');
  });
}

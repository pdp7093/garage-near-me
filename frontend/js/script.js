// GarageNearMe — script.js

// ── Mobile menu toggle ──────────────────
const menuBtn = document.getElementById('menuBtn');
const mobileMenu = document.getElementById('mobileMenu');
if (menuBtn && mobileMenu) {
  menuBtn.addEventListener('click', function () {
    mobileMenu.classList.toggle('open');
  });
}

// ── GPS location detect ─────────────────
const gpsBtn = document.getElementById('gpsBtn');
const locationInput = document.getElementById('locationInput');
if (gpsBtn && locationInput) {
  gpsBtn.addEventListener('click', function () {
    if (!navigator.geolocation) {
      alert('Geolocation is not supported by your browser.');
      return;
    }
    gpsBtn.style.opacity = '0.4';
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        locationInput.value = 'Ahmedabad, Gujarat (GPS Detected)';
        gpsBtn.style.opacity = '1';
      },
      function () {
        alert('Could not detect location. Please type your area.');
        gpsBtn.style.opacity = '1';
      }
    );
  });
}

// ── SOS button ──────────────────────────
const sosBtn = document.getElementById('sosBtn');
if (sosBtn) {
  sosBtn.addEventListener('click', function () {
    alert('SOS Alert Sent!\n\nNearby mechanics are being notified.\nPlease stay at your location.');
  });
}

/**
 * SOS Notification Handler
 * Simplified — service worker dependency removed.
 * Ab hum native Capacitor Push Notifications use kar rahe hain, jo
 * background/kill state mein bhi Android OS level pe reliably kaam karta hai.
 * Isliye service-worker-based looping notification logic ki zaroorat nahi rahi.
 */

// ── Integration point: Call this when mechanic accepts SOS ──────────────────
function handleSOSAccepted(sosId) {
    console.log(`✅ SOS ${sosId} accepted`);
}

// ── Integration point: Call this when mechanic declines SOS ─────────────────
function handleSOSDeclined(sosId) {
    console.log(`❌ SOS ${sosId} declined`);
}

// Exposed as globals for regular script usage (no module needed)
window.handleSOSAccepted = handleSOSAccepted;
window.handleSOSDeclined = handleSOSDeclined;
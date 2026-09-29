const OTP_PROVIDER = "firebase"; // or "messagecentral"

const FIREBASE_WEB_CONFIG = {
    // The user will paste the real values here
    apiKey: "AIzaSyAf_TRBMQ1213PahyEsP5GiJlPMFyV_YrU",
    authDomain: "nice-limiter-308209.firebaseapp.com",
    projectId: "nice-limiter-308209",
    storageBucket: "nice-limiter-308209.firebasestorage.app",
    messagingSenderId: "154328863578",
    appId: "1:154328863578:web:16dd06513aee5398f79963",
    measurementId: "G-QLFVHQWZXT"
};

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

// ── NGROK Bypass Interceptor ───────────────────────────────────────────────
const originalFetch = window.fetch;
window.fetch = async function () {
    let [resource, config] = arguments;
    if (typeof resource === 'string' && resource.includes('ngrok')) {
        config = config || {};
        config.headers = config.headers || {};
        if (config.headers instanceof Headers) {
            config.headers.set('ngrok-skip-browser-warning', '69420');
        } else {
            config.headers['ngrok-skip-browser-warning'] = '69420';
        }
    } else if (resource instanceof Request && resource.url.includes('ngrok')) {
        resource.headers.set('ngrok-skip-browser-warning', '69420');
    }
    return originalFetch(resource, config);
};
/**
 * phone-auth.js
 * Firebase Phone OTP — native (Capacitor plugin) + web (Firebase JS SDK)
 * Depends on config.js: FIREBASE_WEB_CONFIG
 *
 * Public API (global GNM_PHONE_AUTH):
 *   await GNM_PHONE_AUTH.sendOtp('9876543210')
 *   const idToken = await GNM_PHONE_AUTH.verifyOtp('123456')
 *   GNM_PHONE_AUTH.reset()
 *
 * Android auto-read OTP hone par window pe 'gnm_otp_autoverified' event fire hota hai
 * (detail.code optional) — index.html usko sun ke seedha verify karta hai.
 */
const GNM_PHONE_AUTH = (function () {
  const FIREBASE_JS_VERSION = '10.13.1';
  const SEND_TIMEOUT_MS = 60000;

  // ── Shared state ──
  let verificationId = null;      // native
  let autoSignedIn = false;       // native (Android auto-retrieval)
  let pendingSend = null;         // native: { resolve, reject, timer }
  let nativeListenersReady = false;

  let fb = null;                  // web: { appMod, authMod, auth }
  let recaptchaVerifier = null;   // web
  let confirmationResult = null;  // web

  function isNative() {
    return !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  }

  function nativePlugin() {
    const p = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.FirebaseAuthentication;
    if (!p) throw makeError('plugin-missing', 'FirebaseAuthentication plugin not found. Run npx cap sync.');
    return p;
  }

  function makeError(code, message) {
    const err = new Error(message || code);
    err.code = code;
    return err;
  }

  function settlePending(fn, value) {
    if (!pendingSend) return;
    clearTimeout(pendingSend.timer);
    const p = pendingSend;
    pendingSend = null;
    p[fn](value);
  }

  // ══════════════════ NATIVE ══════════════════

  async function ensureNativeListeners() {
    if (nativeListenersReady) return;
    const FA = nativePlugin();

    await FA.addListener('phoneCodeSent', (event) => {
      verificationId = event && event.verificationId;
      settlePending('resolve');
    });

    await FA.addListener('phoneVerificationCompleted', (event) => {
      // Android ne SMS khud padh liya aur sign-in ho gaya
      autoSignedIn = true;
      settlePending('resolve');
      const code = event && event.verificationCode;
      // UI OTP screen pe aa jaye, uske baad event bhejo
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent('gnm_otp_autoverified', { detail: { code: code || null } }));
      }, 300);
    });

    await FA.addListener('phoneVerificationFailed', (event) => {
      const msg = (event && event.message) || 'Phone verification failed';
      console.error('[PhoneAuth] Verification failed:', msg);
      const lower = msg.toLowerCase();
      let code = 'verification-failed';
      if (lower.includes('unusual activity') || lower.includes('too many') || lower.includes('blocked')) code = 'auth/too-many-requests';
      else if (lower.includes('invalid') && lower.includes('phone')) code = 'auth/invalid-phone-number';
      else if (lower.includes('network')) code = 'auth/network-request-failed';
      settlePending('reject', makeError(code, msg));
    });

    nativeListenersReady = true;
  }

  async function sendOtpNative(phoneNumber) {
    await ensureNativeListeners();
    verificationId = null;
    autoSignedIn = false;

    // Pehle waiter set karo, phir request bhejo — taaki event miss na ho
    const waiter = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (pendingSend) {
          pendingSend = null;
          reject(makeError('auth/network-request-failed', 'OTP send timed out'));
        }
      }, SEND_TIMEOUT_MS);
      pendingSend = { resolve, reject, timer };
    });

    try {
      // Is plugin mein ye kuch return nahi karta — result listeners se aata hai
      await nativePlugin().signInWithPhoneNumber({ phoneNumber });
    } catch (err) {
      settlePending('reject', err);
    }

    await waiter;
  }

  async function verifyOtpNative(code) {
    const FA = nativePlugin();

    if (!autoSignedIn) {
      if (!verificationId) throw makeError('auth/code-expired', 'No verificationId — request OTP again');
      await FA.confirmVerificationCode({ verificationId, verificationCode: code });
    }

    const result = await FA.getIdToken();
    const idToken = result && result.token;
    if (!idToken) throw makeError('no-id-token', 'Firebase ID token not received');

    // Humara apna JWT session hai — Firebase session ki zaroorat nahi
    try { await FA.signOut(); } catch (e) { console.warn('[PhoneAuth] signOut failed', e); }

    verificationId = null;
    autoSignedIn = false;
    return idToken;
  }

  // ══════════════════ WEB ══════════════════

  async function loadWebFirebase() {
    if (fb) return fb;
    const base = `https://www.gstatic.com/firebasejs/${FIREBASE_JS_VERSION}`;
    const [appMod, authMod] = await Promise.all([
      import(`${base}/firebase-app.js`),
      import(`${base}/firebase-auth.js`)
    ]);
    const app = appMod.getApps().length ? appMod.getApp() : appMod.initializeApp(FIREBASE_WEB_CONFIG);
    const auth = authMod.getAuth(app);
    auth.useDeviceLanguage();
    fb = { appMod, authMod, auth };
    return fb;
  }

  function clearRecaptcha() {
    if (recaptchaVerifier) {
      try { recaptchaVerifier.clear(); } catch (e) { /* ignore */ }
      recaptchaVerifier = null;
    }
  }

  async function sendOtpWeb(phoneNumber) {
    const { authMod, auth } = await loadWebFirebase();
    clearRecaptcha();
    confirmationResult = null;

    recaptchaVerifier = new authMod.RecaptchaVerifier(auth, 'recaptcha-container', { size: 'invisible' });

    try {
      confirmationResult = await authMod.signInWithPhoneNumber(auth, phoneNumber, recaptchaVerifier);
    } catch (err) {
      clearRecaptcha();
      throw err;
    }
  }

  async function verifyOtpWeb(code) {
    const { authMod, auth } = await loadWebFirebase();
    if (!confirmationResult) throw makeError('auth/code-expired', 'No confirmation result — request OTP again');

    const result = await confirmationResult.confirm(code);
    const idToken = await result.user.getIdToken();

    try { await authMod.signOut(auth); } catch (e) { console.warn('[PhoneAuth] signOut failed', e); }

    confirmationResult = null;
    clearRecaptcha();
    return idToken;
  }

  // ══════════════════ PUBLIC ══════════════════

  return {
    async sendOtp(phone10) {
      const phoneNumber = `+91${phone10}`;
      if (isNative()) return sendOtpNative(phoneNumber);
      return sendOtpWeb(phoneNumber);
    },

    async verifyOtp(code) {
      if (isNative()) return verifyOtpNative(code);
      return verifyOtpWeb(code);
    },

    // Firebase error → user-friendly Hinglish message (customer pages use karte hain)
    friendlyError(error) {
      const c = String((error && (error.code || error.message)) || '').toLowerCase();
      if (c.includes('invalid-phone-number')) return 'Phone number sahi nahi hai.';
      if (c.includes('too-many-requests') || c.includes('quota')) return 'Bahut zyada attempts! Thodi der baad try karein.';
      if (c.includes('invalid-verification-code')) return 'OTP galat hai. Sahi OTP dalein.';
      if (c.includes('code-expired') || c.includes('session-expired')) return 'OTP expire ho gaya hai. Naya OTP mangwayein.';
      if (c.includes('network')) return 'Internet connection check karein.';
      if (c.includes('captcha')) return 'Verification fail hua. Page refresh karke dobara try karein.';
      return 'Kuch galat ho gaya. Kripaya dobara try karein.';
    },

    reset() {
      verificationId = null;
      autoSignedIn = false;
      confirmationResult = null;
      settlePending('reject', makeError('cancelled', 'Cancelled'));
      clearRecaptcha();
    }
  };
})();
/**
 * app-update.js — Mechanic App In-App Update System
 * Checks for updates against /app/version?app=mechanic on native Capacitor platforms.
 */
(function () {
  'use strict';

  // Sirf native platform pe chale (website pe nahi)
  if (typeof window === 'undefined' || !window.Capacitor || !window.Capacitor.isNativePlatform || !window.Capacitor.isNativePlatform()) {
    return;
  }

  async function openApkUrl(url) {
    if (!url) return;
    try {
      const BrowserPlugin = window.Capacitor?.Plugins?.Browser;
      if (BrowserPlugin && typeof BrowserPlugin.open === 'function') {
        await BrowserPlugin.open({ url: url });
        return;
      }
    } catch (e) {
      console.warn('[AppUpdate] Browser plugin error, fallback to window.open:', e);
    }
    try {
      window.open(url, '_system');
    } catch (e) {
      console.warn('[AppUpdate] window.open failed:', e);
    }
  }

  async function getCurrentVersionCode() {
    try {
      const AppPlugin = window.Capacitor?.Plugins?.App;
      if (AppPlugin && typeof AppPlugin.getInfo === 'function') {
        const info = await AppPlugin.getInfo();
        const code = Number(info.build);
        if (!isNaN(code) && code > 0) {
          return code;
        }
      }
    } catch (e) {
      console.warn('[AppUpdate] Failed to get app info, defaulting currentCode=0:', e);
    }
    // Agar App plugin nahi mila ya error aaye -> currentCode = 0 (purani app maano)
    return 0;
  }

  function showForceUpdateOverlay(apkUrl, message) {
    if (document.getElementById('gnm-force-update-overlay')) return;

    // Remove soft banner if open
    const existingSoft = document.getElementById('gnm-soft-update-banner');
    if (existingSoft) existingSoft.remove();

    const overlay = document.createElement('div');
    overlay.id = 'gnm-force-update-overlay';
    overlay.style.cssText = [
      'position: fixed',
      'top: 0',
      'left: 0',
      'width: 100vw',
      'height: 100vh',
      'background-color: #062B63',
      'z-index: 99999999',
      'display: flex',
      'flex-direction: column',
      'align-items: center',
      'justify-content: center',
      'padding: 24px',
      'box-sizing: border-box',
      'color: #ffffff',
      'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      'text-align: center'
    ].join(';');

    overlay.innerHTML = `
      <div style="max-width: 360px; width: 100%; display: flex; flex-direction: column; align-items: center;">
        <div style="width: 88px; height: 88px; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.4); margin-bottom: 24px; background: rgba(255,255,255,0.08); display: flex; align-items: center; justify-content: center;">
          <img src="/assets/gnm-icon-mechanic.png" alt="GarageNearMe Mechanic" width="88" height="88" style="display:block; object-fit:cover;" onerror="this.style.display='none';">
        </div>
        <h2 style="font-size: 22px; font-weight: 700; margin: 0 0 12px; color: #ffffff; letter-spacing: -0.3px;">App Update Zaroori Hai</h2>
        <p style="font-size: 15px; line-height: 1.5; color: rgba(255,255,255,0.85); margin: 0 0 28px;">${message}</p>
        <button id="gnm-force-update-btn" style="width: 100%; background: #FF6B35; color: #ffffff; border: none; padding: 14px 20px; border-radius: 12px; font-weight: 700; font-size: 16px; cursor: pointer; box-shadow: 0 4px 15px rgba(255,107,53,0.45); transition: opacity 0.2s;">
          Update Karein
        </button>
      </div>
    `;

    document.body.appendChild(overlay);

    const btn = document.getElementById('gnm-force-update-btn');
    if (btn) {
      btn.addEventListener('click', () => {
        openApkUrl(apkUrl);
      });
    }
  }

  function showSoftUpdateBanner(apkUrl, message) {
    if (document.getElementById('gnm-soft-update-banner') || document.getElementById('gnm-force-update-overlay')) return;

    const banner = document.createElement('div');
    banner.id = 'gnm-soft-update-banner';
    banner.style.cssText = [
      'position: fixed',
      'top: 0',
      'left: 0',
      'width: 100%',
      'background: #062B63',
      'color: #ffffff',
      'z-index: 9999999',
      'padding: 12px 16px',
      'display: flex',
      'align-items: center',
      'justify-content: space-between',
      'gap: 12px',
      'box-shadow: 0 4px 14px rgba(0,0,0,0.25)',
      'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      'box-sizing: border-box',
      'border-bottom: 1px solid rgba(255,255,255,0.1)'
    ].join(';');

    banner.innerHTML = `
      <div style="display: flex; align-items: center; gap: 10px; flex: 1 1 auto; min-width: 0;">
        <span style="font-size: 20px; flex-shrink: 0;">🚀</span>
        <div style="min-width: 0;">
          <div style="font-size: 14px; font-weight: 700; line-height: 1.2;">Naya update available</div>
          <div style="font-size: 12px; color: rgba(255,255,255,0.85); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${message}</div>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
        <button id="gnm-soft-update-btn" style="background: #FF6B35; color: #ffffff; border: none; padding: 7px 14px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer;">
          Update
        </button>
        <button id="gnm-soft-dismiss-btn" style="background: transparent; color: rgba(255,255,255,0.75); border: 1px solid rgba(255,255,255,0.3); padding: 6px 10px; border-radius: 8px; font-size: 12px; cursor: pointer;">
          Baad mein
        </button>
      </div>
    `;

    document.body.prepend(banner);

    const updateBtn = document.getElementById('gnm-soft-update-btn');
    if (updateBtn) {
      updateBtn.addEventListener('click', () => {
        openApkUrl(apkUrl);
      });
    }

    const dismissBtn = document.getElementById('gnm-soft-dismiss-btn');
    if (dismissBtn) {
      dismissBtn.addEventListener('click', () => {
        try {
          sessionStorage.setItem('gnm_update_dismissed', 'true');
        } catch (e) {}
        banner.remove();
      });
    }
  }

  async function checkAppUpdate() {
    try {
      const apiBase = typeof getApiBase === 'function' ? getApiBase() : 'https://garagenearme.net/api';
      const res = await fetch(`${apiBase}/app/version?app=mechanic`, {
        headers: { 'ngrok-skip-browser-warning': '69420' }
      });
      if (!res.ok) {
        console.warn('[AppUpdate] Failed to fetch version info, status:', res.status);
        return;
      }

      const data = await res.json();
      const apkUrl = (data.apk_url || '').trim();
      if (!apkUrl) {
        // apk_url khaali ho -> kuch mat dikhao
        return;
      }

      const latestCode = Number(data.latest_version_code) || 1;
      const minCode = Number(data.min_version_code) || 1;
      const message = data.message || 'Naya update aaya hai, kripya app update karein.';

      const currentCode = await getCurrentVersionCode();

      if (currentCode < minCode) {
        showForceUpdateOverlay(apkUrl, message);
      } else if (currentCode < latestCode) {
        let isDismissed = false;
        try {
          isDismissed = sessionStorage.getItem('gnm_update_dismissed') === 'true';
        } catch (e) {}

        if (!isDismissed) {
          showSoftUpdateBanner(apkUrl, message);
        }
      }
    } catch (err) {
      // Fetch fail ho to chupchap ignore (console.warn only)
      console.warn('[AppUpdate] Check failed silently:', err);
    }
  }

  // Expose function globally for manual calls
  window.checkAppUpdate = checkAppUpdate;

  // Page load check
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', checkAppUpdate);
  } else {
    checkAppUpdate();
  }

  // App 'resume' event
  try {
    const AppPlugin = window.Capacitor?.Plugins?.App;
    if (AppPlugin && typeof AppPlugin.addListener === 'function') {
      AppPlugin.addListener('appStateChange', (state) => {
        if (state && state.isActive) {
          checkAppUpdate();
        }
      });
    }
  } catch (e) {
    console.warn('[AppUpdate] Could not attach appStateChange listener:', e);
  }
})();

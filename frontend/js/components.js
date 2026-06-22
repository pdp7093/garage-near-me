function _resolveApiBase() {
  const h = window.location.hostname;
  if (h === 'localhost' || h === '127.0.0.1') return 'http://localhost:8000';
  if (/^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(h)) return `http://${h}:8000`;
  return window.location.origin;
}
const API_BASE = window.API_BASE || _resolveApiBase();

async function loadComponent(elementId, componentPath, callback = null) {
  const container = document.getElementById(elementId);
  if (!container) return;

  try {
    const response = await fetch(componentPath);
    if (!response.ok) {
      throw new Error(`Failed to load ${componentPath}: ${response.statusText}`);
    }
    
    const html = await response.text();
    container.innerHTML = html;

    // Normalize internal relative links inside admin/mechanic components
    try {
      let prefix = null;
      if (componentPath.startsWith('/admin/')) prefix = '/admin/';
      else if (componentPath.startsWith('/mechanic/')) prefix = '/mechanic/';
      if (prefix) {
        container.querySelectorAll('a[href]').forEach(a => {
          const h = a.getAttribute('href');
          if (!h) return;
          if (h.startsWith('/') || h.startsWith('http') || h.startsWith('mailto:') || h.startsWith('#')) return;
          if (h.includes('${')) return; // template variable
          if (h.startsWith('./') || h.startsWith('../')) return;
          a.setAttribute('href', prefix + h);
        });
      }
    } catch (e) {
      console.error('Error normalizing component links', e);
    }

    // Execute callback if provided (e.g., to bind events after load)
    if (callback && typeof callback === 'function') {
      callback();
    }

  } catch (error) {
    console.error('Error loading component:', error);
    container.innerHTML = `<div class="text-danger p-2 border border-danger">Failed to load component</div>`;
  }
}

/**
 * Highlights the active link in the sidebar based on current URL
 */
function setActiveSidebarLink() {
  const currentPath = window.location.pathname.split('/').pop() || 'index';
  const links = document.querySelectorAll('.admin-nav-link, .sidebar-link, .gnm-nav-link');
  
  links.forEach(link => {
    // Remove active class from all
    link.classList.remove('active');
    
    // Add active class if href matches current path
    const href = link.getAttribute('href');
    if (href && currentPath.includes(href)) {
      link.classList.add('active');
    }
  });
}

function bindAdminSidebarToggle() {
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', () => {
      sidebar.classList.toggle('show');
    });
  }
}

async function initAdminChrome(pageTitle, callback = null) {
  // Enforce secure administrator session lock
  const adminKey = localStorage.getItem("gnm_admin_key");
  if (!adminKey) {
    window.location.href = "index";
    return;
  }

  const v = '2506b';

  await Promise.all([
    loadComponent('sidebar-container', '/admin/components/sidebar.html?v=' + v, setActiveSidebarLink),
    loadComponent('topbar-container', '/admin/components/topbar.html?v=' + v, () => {
      const titleEl = document.getElementById('topbar-title');
      if (titleEl) titleEl.textContent = pageTitle;
    })
  ]);

  bindAdminSidebarToggle();

  updateAdminChrome();

  if (callback && typeof callback === 'function') {
    callback();
  }
}

async function updateAdminChrome() {
  const token = localStorage.getItem('gnm_admin_key');
  if (!token) return;

  try {
    const res = await fetch(`${API_BASE}/api/admin-auth/chrome-stats`, {
      headers: { 'Authorization': `Bearer ${token}`, 'X-Admin-Key': token }
    });
    if (res.ok) {
      const data = await res.json();
      
      // Update Topbar Avatar Initials
      const topbarAvatar = document.querySelector('.admin-topbar .rounded-circle');
      if (topbarAvatar && data.admin_email) {
        topbarAvatar.textContent = data.admin_email.substring(0, 2).toUpperCase();
      }

      // Update Sidebar Badges
      const sidebar = document.getElementById('sidebar');
      if (sidebar) {
        // Pending Garages
        const garagesLink = sidebar.querySelector('a[href="garages"]');
        if (garagesLink && data.pending_garages > 0) {
          let badge = garagesLink.querySelector('.gnm-badge');
          if (!badge) {
            badge = document.createElement('span');
            badge.className = 'gnm-badge badge bg-warning text-dark ms-auto rounded-pill';
            garagesLink.appendChild(badge);
          }
          badge.textContent = data.pending_garages;
        }

        // Active SOS Red Dot
        const sosLink = sidebar.querySelector('a[href="sos-monitor"]');
        if (sosLink) {
          let dot = sosLink.querySelector('.gnm-dot');
          if (data.active_sos > 0) {
            if (!dot) {
              dot = document.createElement('span');
              dot.className = 'gnm-dot position-absolute top-50 end-0 translate-middle-y me-3 bg-danger rounded-circle';
              dot.style.width = '10px';
              dot.style.height = '10px';
              dot.style.boxShadow = '0 0 10px rgba(220, 38, 38, 0.8)';
              sosLink.style.position = 'relative';
              sosLink.appendChild(dot);
            }
          } else if (dot) {
            dot.remove();
          }
        }

        // Pending Payouts
        const payoutsLink = sidebar.querySelector('a[href="payouts"]');
        if (payoutsLink && data.pending_payouts > 0) {
          let badge = payoutsLink.querySelector('.gnm-badge');
          if (!badge) {
            badge = document.createElement('span');
            badge.className = 'gnm-badge badge bg-danger text-white ms-auto rounded-pill';
            payoutsLink.appendChild(badge);
          }
          badge.textContent = data.pending_payouts;
        }
      }
    }
  } catch (err) {
    console.error('Failed to update admin chrome', err);
  }
}

function bindMechanicSidebarToggle() {
  const sidebarContainer = document.getElementById('sidebar-container');
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarOverlay = document.getElementById('sidebarOverlay');

  function toggleSidebar() {
    if (sidebarContainer) {
      sidebarContainer.classList.toggle('show');
    }
    if (sidebarOverlay) {
      if (sidebarOverlay.classList.contains('d-none')) {
        sidebarOverlay.classList.remove('d-none');
      } else {
        sidebarOverlay.classList.add('d-none');
      }
    }
  }

  if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);
  if (sidebarOverlay) sidebarOverlay.addEventListener('click', toggleSidebar);
}

async function initMechanicChrome(pageTitle, callback = null, activeHref = null) {
  const v = '2506b';

  await Promise.all([
    loadComponent('sidebar-container', '/mechanic/components/sidebar.html?v=' + v, () => {
      setActiveSidebarLink();
      if (activeHref) {
        const activeLink = document.querySelector(`.sidebar-link[href="${activeHref}"]`);
        if (activeLink) activeLink.classList.add('active');
      }
    }),
    loadComponent('topbar-container', '/mechanic/components/topbar.html?v=' + v, () => {
      const titleEl = document.getElementById('topbar-title');
      if (titleEl) titleEl.textContent = pageTitle;
    })
  ]);

  bindMechanicSidebarToggle();

  // Dynamic data — name, badges, sos dot
  updateMechanicChrome();

  // FCM — garage notifications (SDK load hone ke baad)
  loadFirebaseSDKAndInit('garage');

  if (callback && typeof callback === 'function') {
    callback();
  }
}

/**
 * Mechanic topbar + sidebar dynamic update
 * - Garage name + initials from API
 * - Active SOS count → bell dot + sidebar badge
 * - Pending bookings count → sidebar badge
 */
async function updateMechanicChrome() {
  const token = localStorage.getItem('garage_token');
  if (!token) return;

  // ── 1. Garage info (name + initials) ──────────────────
  try {
    const res = await fetch(`${API_BASE}/api/garage-auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      const garage = await res.json();
      const name = garage.name || 'Partner';
      const initials = getInitials(name);

      const nameEl   = document.getElementById('topbar-name');
      const avatarEl = document.getElementById('topbar-avatar');
      if (nameEl)   nameEl.textContent   = name;
      if (avatarEl) avatarEl.textContent = initials;

      // Credit Lock Enforcement Overlay
      if (garage.is_credit_locked && !window.location.pathname.includes('payout-history.html')) {
        if (!document.getElementById('credit-lock-overlay')) {
          const overlay = document.createElement('div');
          overlay.id = 'credit-lock-overlay';
          overlay.style.position = 'fixed';
          overlay.style.top = '0';
          overlay.style.left = '0';
          overlay.style.width = '100vw';
          overlay.style.height = '100vh';
          overlay.style.backgroundColor = 'rgba(255,255,255,0.75)';
          overlay.style.backdropFilter = 'blur(12px)';
          overlay.style.zIndex = '999999';
          overlay.style.display = 'flex';
          overlay.style.flexDirection = 'column';
          overlay.style.alignItems = 'center';
          overlay.style.justifyContent = 'center';
          
          overlay.innerHTML = `
            <div class="text-center p-5 bg-white rounded shadow-lg border border-danger" style="max-width: 500px; transform: translateY(-10%);">
              <i class="bi bi-lock-fill text-danger mb-2 d-block" style="font-size: 3.5rem;"></i>
              <h2 class="mt-3 text-danger fw-bold tracking-tight">Account Locked</h2>
              <p class="text-muted mt-3 mb-4" style="font-size: 1.1rem;">
                ${garage.has_completed_trial 
                  ? 'Your previous billing cycle payment is due. To resume receiving new SOS and Normal bookings, please clear your outstanding dues.' 
                  : 'Your pending platform dues have reached or exceeded the ₹500.00 threshold. To resume receiving new SOS and Normal bookings, please clear your outstanding dues.'}
              </p>
              <div class="bg-light p-3 rounded mb-4 border">
                <div class="text-uppercase text-muted small fw-bold mb-1">Total Outstanding</div>
                <h3 class="fw-bold text-dark mb-0">₹${parseFloat(garage.pending_platform_dues || 0).toFixed(2)}</h3>
              </div>
              <a href="payout-history.html" class="btn btn-danger btn-lg w-100 fw-bold shadow-sm py-3" style="font-size: 1.1rem;">Pay Dues via UPI Now</a>
            </div>
          `;
          document.body.appendChild(overlay);
          
          // Disable scroll
          document.body.style.overflow = 'hidden';
        }
      }
    }
  } catch (e) {}

  // ── 2. Active SOS count ────────────────────────────────
  try {
    const res = await fetch(`${API_BASE}/api/sos/active`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      const list = await res.json();
      const declined = JSON.parse(localStorage.getItem('declined_sos') || '[]').map(Number);
      const activeSOS = list.filter(s =>
        s.status === 'broadcasting' && !declined.includes(Number(s.id))
      );
      const count = activeSOS.length;

      // Topbar bell dot
      const dot = document.getElementById('topbar-sos-dot');
      if (dot) dot.classList.toggle('d-none', count === 0);

      // Sidebar SOS badge
      const sosBadge = document.getElementById('sidebar-sos-badge');
      if (sosBadge) {
        if (count > 0) {
          sosBadge.textContent = count;
          sosBadge.classList.remove('d-none');
        } else {
          sosBadge.classList.add('d-none');
        }
      }
    }
  } catch (e) {}

  // ── 3. Pending bookings count ──────────────────────────
  try {
    const res = await fetch(`${API_BASE}/api/bookings/garage/incoming`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      const data = await res.json();
      const count = Array.isArray(data) ? data.length : (data.total || 0);

      const bkBadge = document.getElementById('sidebar-bookings-badge');
      if (bkBadge) {
        if (count > 0) {
          bkBadge.textContent = count;
          bkBadge.classList.remove('d-none');
        } else {
          bkBadge.classList.add('d-none');
        }
      }
    }
  } catch (e) {}
}

async function mechanicCheckLocationSet() {
  const token = localStorage.getItem('garage_token');
  if (!token) {
    window.location.href = 'index';
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/garage-auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) {
      window.location.href = 'index';
      return;
    }

    const garage = await res.json();
    
    // Check for Credit Lock
    if (garage.is_credit_locked) {
      const currentPath = window.location.pathname.split('/').pop() || 'dashboard';
      if (currentPath !== 'payout-history') {
        showCreditLockOverlay(garage.pending_platform_dues, garage.has_completed_trial);
        return; // Don't check location if locked
      }
    }

    // Check for Grace Period Warning Banner
    if (!garage.is_credit_locked && garage.grace_period_ends_at) {
      showGracePeriodBanner(garage.pending_platform_dues, garage.grace_period_ends_at);
    }

    const loc = garage.location;
    if (!loc || !loc.latitude || !loc.longitude) {
      window.location.href = 'set-location';
    }
  } catch (err) {
    console.error('Error in mechanic check:', err);
  }
}

function showGracePeriodBanner(duesAmount, graceEndsAt) {
  // Prevent duplicate rendering
  if (document.getElementById('gracePeriodBanner')) return;

  const contentContainer = document.querySelector('.mechanic-content');
  if (!contentContainer) return;

  const deadline = new Date(graceEndsAt);
  const options = { weekday: 'long', hour: '2-digit', minute: '2-digit', hour12: true };
  const formattedDeadline = deadline.toLocaleDateString('en-IN', options);

  const banner = document.createElement('div');
  banner.id = 'gracePeriodBanner';
  banner.className = 'mb-4';
  banner.style.cssText = `
    background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%);
    border: 1px solid rgba(245, 158, 11, 0.25);
    border-radius: 16px;
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    box-shadow: 0 10px 30px rgba(245, 158, 11, 0.08);
    font-family: 'DM Sans', sans-serif;
    color: #F8FAFC;
    flex-wrap: wrap;
    animation: fadeInDown 0.5s ease-out;
  `;

  // Inject dynamic CSS keyframe animation if not exists
  if (!document.getElementById('bannerAnimationStyles')) {
    const style = document.createElement('style');
    style.id = 'bannerAnimationStyles';
    style.textContent = `
      @keyframes fadeInDown {
        from { opacity: 0; transform: translateY(-15px); }
        to { opacity: 1; transform: translateY(0); }
      }
    `;
    document.head.appendChild(style);
  }

  banner.innerHTML = `
    <div style="display: flex; align-items: center; gap: 16px;">
      <!-- Warning Icon -->
      <div style="width: 44px; height: 44px; background: rgba(245, 158, 11, 0.15); border: 1.5px solid #F59E0B; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-shadow: 0 0 15px rgba(245, 158, 11, 0.15);">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="#F59E0B">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/>
        </svg>
      </div>
      <div>
        <h5 style="margin: 0; font-weight: 700; font-size: 15px; color: #F59E0B; font-family: 'Syne', sans-serif; letter-spacing: 0.2px;">Weekly Statement Generated (Dues: ₹${Number(duesAmount).toFixed(2)})</h5>
        <p style="margin: 4px 0 0; font-size: 13px; color: #94A3B8; line-height: 1.4;">
          Please clear outstanding dues before <strong style="color: #F1F5F9;">${formattedDeadline}</strong> to avoid automatic service lockout.
        </p>
      </div>
    </div>
    <a href="payout-history" style="
      background: linear-gradient(135deg, #F59E0B, #D97706);
      color: #0F172A;
      text-decoration: none;
      font-weight: 700;
      font-size: 13px;
      padding: 10px 20px;
      border-radius: 10px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.3s ease;
      box-shadow: 0 4px 12px rgba(245, 158, 11, 0.25);
    " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 16px rgba(245, 158, 11, 0.35)';" onmouseout="this.style.transform='none'; this.style.boxShadow='0 4px 12px rgba(245, 158, 11, 0.25)';">
      Pay Now
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
        <path d="M12 4l-1.41 1.41L15.17 10H3v2h12.17l-4.58 4.59L12 18l8-8z"/>
      </svg>
    </a>
  `;

  contentContainer.prepend(banner);
}

function showCreditLockOverlay(duesAmount, hasCompletedTrial) {
  // Prevent double rendering
  if (document.getElementById('creditLockOverlay')) return;

  // Prevent body scrolling
  document.body.style.overflow = 'hidden';

  // Create overlay element
  const overlay = document.createElement('div');
  overlay.id = 'creditLockOverlay';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    z-index: 999999;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow-y: auto;
    font-family: 'DM Sans', sans-serif;
    color: #F8FAFC;
    padding: 20px;
  `;

  // Dynamic UPI URL (using admin VPA and duesAmount)
  const upiId = 'adminupi@okaxis';
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=upi://pay?pa=${upiId}%26pn=GarageNearMeAdmin%26am=${duesAmount}%26cu=INR%26tn=PlatformDues`;

  overlay.innerHTML = `
    <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 24px; max-width: 500px; width: 100%; padding: 40px 30px; box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4); text-align: center;">
      <!-- Lock Icon -->
      <div style="width: 80px; height: 80px; background: rgba(239, 68, 68, 0.15); border: 2px solid #EF4444; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 24px; box-shadow: 0 0 20px rgba(239, 68, 68, 0.2);">
        <svg viewBox="0 0 24 24" width="36" height="36" fill="#EF4444">
          <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
        </svg>
      </div>

      <h3 style="font-family: 'Syne', sans-serif; font-weight: 700; margin-bottom: 12px; font-size: 24px; color: #EF4444; text-transform: uppercase; letter-spacing: 0.5px;">Credit Limit Exceeded!</h3>
      <p style="color: #94A3B8; font-size: 14px; line-height: 1.6; margin-bottom: 24px;">
        ${hasCompletedTrial 
          ? 'Aapke previous billing cycle ka payment due hai. Aapka account block kar diya gaya hai aur nayi bookings / SOS alerts temporarily suspended hain.' 
          : 'Aapka platform commission outstanding ₹500 cross ho gaya hai. Aapka account block kar diya gaya hai aur nayi bookings / SOS alerts temporarily suspended hain.'}
      </p>

      <!-- Amount Box -->
      <div style="background: rgba(15, 23, 42, 0.4); border: 1px dashed rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 15px; margin-bottom: 30px;">
        <span style="color: #94A3B8; font-size: 13px; font-weight: 500; text-transform: uppercase;">Total Outstanding Dues</span>
        <h2 style="font-family: 'Syne', sans-serif; font-weight: 800; font-size: 32px; color: #EF4444; margin-top: 5px; margin-bottom: 0;">₹${Number(duesAmount).toFixed(2)}</h2>
      </div>

      <!-- Payment Section -->
      <div id="lockFormContainer">
        <h5 style="font-weight: 600; font-size: 15px; margin-bottom: 15px; color: #F1F5F9;">Scan QR to Pay Dues Instantly</h5>
        <div style="width: 170px; height: 170px; background: white; border-radius: 16px; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; padding: 10px; box-shadow: 0 10px 20px rgba(0,0,0,0.2);">
          <img src="${qrUrl}" alt="UPI QR Code" style="width: 100%; height: 100%; object-fit: contain;">
        </div>

        <p style="font-size: 12px; color: #64748B; margin-bottom: 20px;">Or pay directly to UPI ID: <strong style="color: #38BDF8;">${upiId}</strong></p>

        <!-- Form -->
        <form id="duesPaymentForm" style="text-align: left;">
          <div style="margin-bottom: 20px;">
            <label style="display: block; font-size: 12px; text-transform: uppercase; font-weight: 600; color: #94A3B8; margin-bottom: 8px;">Enter 12-Digit UPI Transaction ID (UTR)</label>
            <input type="text" id="lockUtrInput" required placeholder="e.g. 123456789012" maxlength="12" style="width: 100%; padding: 12px 16px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 12px; color: white; font-size: 14px; font-weight: 600; letter-spacing: 0.5px; transition: 0.3s;">
            <div id="utrErrorMsg" style="color: #EF4444; font-size: 11px; margin-top: 5px; display: none; font-weight: 500;">Please enter a valid 12-digit numeric UTR code.</div>
          </div>

          <button type="submit" style="width: 100%; padding: 14px; background: linear-gradient(135deg, #EF4444, #C2410C); border: none; border-radius: 12px; color: white; font-weight: 700; font-size: 15px; cursor: pointer; transition: 0.3s; box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);">Submit Payment Proof</button>
        </form>
      </div>

      <div style="margin-top: 30px; border-top: 1px solid rgba(255, 255, 255, 0.08); padding-top: 20px;">
        <a href="payout-history" style="color: #38BDF8; text-decoration: none; font-size: 13px; font-weight: 600; transition: 0.2s;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">View Past Payouts Ledger</a>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // Bind submit event
  const form = document.getElementById('duesPaymentForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const utr = document.getElementById('lockUtrInput').value.trim();
    const utrError = document.getElementById('utrErrorMsg');

    // UTR regex validation
    if (!/^\d{12}$/.test(utr)) {
      utrError.textContent = 'Please enter a valid 12-digit numeric UTR code.';
      utrError.style.display = 'block';
      return;
    }
    utrError.style.display = 'none';

    const submitBtn = form.querySelector('button[type="submit"]');
    const originalBtnText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting...';

    try {
      const token = localStorage.getItem('garage_token');
      const formData = new FormData();
      formData.append('amount', duesAmount);
      formData.append('utr_number', utr);

      const response = await fetch(`${API_BASE}/api/payouts/request`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to submit proof');
      }

      // Show success message
      const container = document.getElementById('lockFormContainer');
      container.innerHTML = `
        <div style="padding: 20px 0; text-align: center;">
          <div style="width: 60px; height: 60px; background: rgba(16, 185, 129, 0.15); border: 2px solid #10B981; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="#10B981">
              <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
            </svg>
          </div>
          <h5 style="color: #10B981; font-weight: 700; margin-bottom: 10px;">Verification Submitted!</h5>
          <p style="font-size: 13px; color: #94A3B8; line-height: 1.6; margin-bottom: 25px;">Aapka UTR submit ho gaya hai. Admin bank account check karke instantly isey approve kar dega. Status check karne ke liye niche reload button dabayein.</p>
          
          <button onclick="window.location.reload();" style="width: 100%; padding: 12px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); border-radius: 10px; color: white; font-weight: 700; font-size: 14px; cursor: pointer; transition: 0.3s;">Check Status &amp; Reload</button>
        </div>
      `;
    } catch (err) {
      console.error(err);
      submitBtn.disabled = false;
      submitBtn.textContent = originalBtnText;
      utrError.textContent = err.message || 'Payment submission failed. Please try again.';
      utrError.style.display = 'block';
    }
  });
}

function getInitials(name) {
  if (!name) return 'U';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0) return 'U';
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function getStoredCustomer() {
  const gnmUserStr = localStorage.getItem('gnm_user');
  if (!gnmUserStr) return null;

  try {
    return JSON.parse(gnmUserStr);
  } catch (e) {
    console.error('Error parsing gnm_user from localStorage:', e);
    return null;
  }
}

function _customerForceLogout() {
  localStorage.removeItem('gnm_token');
  localStorage.removeItem('gnm_user');
  localStorage.removeItem('gnm_role');
  window.location.href = '/customer/login';
}

async function fetchCustomerFromApi() {
  const token = localStorage.getItem('gnm_token');
  if (!token) return null;

  try {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (response.status === 401) {
      _customerForceLogout();
      return null;
    }

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    const currentUser = {
      name: data.name,
      email: data.email,
      phone: data.phone,
      profile_image: data.profile_image ? `${API_BASE}${data.profile_image}` : null
    };

    localStorage.setItem('gnm_user', JSON.stringify(currentUser));
    return currentUser;
  } catch (error) {
    console.warn('Could not refresh customer profile:', error);
    return null;
  }
}

async function updateCustomerNav() {
  const profileBtn = document.getElementById('navProfileButton');
  const loginBtn = document.getElementById('navLoginButton');
  const mobileLoginLink = document.getElementById('mobileLoginLink');
  const mobileProfileLink = document.getElementById('mobileProfileLink');
  const avatarInitials = document.getElementById('navAvatarInitials');
  
  const token = localStorage.getItem('gnm_token');

  // Token nahi hai toh stored user bhi ignore karo
  let gnmUser = null;
  if (token) {
    // Har baar API se fresh verify karo — stale localStorage se blindly show mat karo
    gnmUser = await fetchCustomerFromApi();
    // 401 pe fetchCustomerFromApi redirect kar dega, yahan null milega
  }

  if (gnmUser && gnmUser.name) {
    if (avatarInitials) {
      if (gnmUser.profile_image) {
        avatarInitials.innerHTML = `<img src="${gnmUser.profile_image}" alt="Profile" style="width:100%; height:100%; border-radius:50%; object-fit:cover;">`;
      } else {
        avatarInitials.textContent = getInitials(gnmUser.name);
      }
    }
    if (profileBtn) profileBtn.classList.remove('d-none');
    if (loginBtn) loginBtn.classList.add('d-none');
    if (mobileLoginLink) mobileLoginLink.classList.add('d-none');
    if (mobileProfileLink) mobileProfileLink.classList.remove('d-none');
  } else {
    if (profileBtn) profileBtn.classList.add('d-none');
    if (loginBtn) loginBtn.classList.remove('d-none');
    if (mobileLoginLink) mobileLoginLink.classList.remove('d-none');
    if (mobileProfileLink) mobileProfileLink.classList.add('d-none');
    if (avatarInitials) avatarInitials.textContent = 'JD';
  }
}

async function initCustomerMenu() {
  const menuBtn = document.getElementById('menuBtn');
  const mobileMenu = document.getElementById('mobileMenu');
  if (menuBtn && mobileMenu) {
    // Remove old listeners to avoid duplicates if called multiple times
    const newMenuBtn = menuBtn.cloneNode(true);
    menuBtn.parentNode.replaceChild(newMenuBtn, menuBtn);
    
    // Get fresh reference to mobileMenu after DOM update
    const freshMobileMenu = document.getElementById('mobileMenu');
    
    newMenuBtn.addEventListener('click', function() {
      if (freshMobileMenu) {
        freshMobileMenu.classList.toggle('open');
        const isExpanded = freshMobileMenu.classList.contains('open');
        this.setAttribute('aria-expanded', isExpanded);
      }
    });
    
    // Close menu when a link is clicked
    if (freshMobileMenu) {
      const links = freshMobileMenu.querySelectorAll('a');
      links.forEach(link => {
        link.addEventListener('click', function() {
          freshMobileMenu.classList.remove('open');
          newMenuBtn.setAttribute('aria-expanded', 'false');
        });
      });
    }
  }

  await updateCustomerNav();

  // FCM — customer notifications (SDK load hone ke baad)
  if (localStorage.getItem('gnm_token')) {
    loadFirebaseSDKAndInit('customer');
  }
}


// App — Firebase SDK + Service Worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker
            .register('/service-worker.js')
            .then(() => console.log('PWA ready'))
            .catch(err => console.log(err));
    });
}

// Firebase SDK load karo — chain loading (app pehle, phir messaging)
function loadFirebaseSDKAndInit(role) {
    if (typeof firebase !== 'undefined' && firebase.apps !== undefined) {
        // Already loaded
        if (typeof initFCM === 'function') initFCM(role).catch(() => {});
        return;
    }

    function loadScript(src, onload) {
        const s = document.createElement('script');
        s.src = src;
        s.onload = onload;
        s.onerror = (e) => console.error('Firebase script load failed:', src, e);
        document.head.appendChild(s);
    }

    // Chain: app-compat → messaging-compat → initFCM (no auth needed for FCM)
    loadScript(
        'https://www.gstatic.com/firebasejs/10.8.1/firebase-app-compat.js',
        () => {
            loadScript(
                'https://www.gstatic.com/firebasejs/10.8.1/firebase-messaging-compat.js',
                () => {
                    setTimeout(() => {
                        if (typeof initFCM === 'function') {
                            initFCM(role).catch(e => console.error('FCM init error:', e));
                        }
                    }, 300);
                }
            );
        }
    );
}
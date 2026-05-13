/**
 * components.js
 * Utility to load HTML components dynamically
 */

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
  const currentPath = window.location.pathname.split('/').pop() || 'index.html';
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
  const v = new Date().getTime();

  await Promise.all([
    loadComponent('sidebar-container', 'components/sidebar.html?v=' + v, setActiveSidebarLink),
    loadComponent('topbar-container', 'components/topbar.html?v=' + v, () => {
      const titleEl = document.getElementById('topbar-title');
      if (titleEl) titleEl.textContent = pageTitle;
    })
  ]);

  bindAdminSidebarToggle();

  if (callback && typeof callback === 'function') {
    callback();
  }
}

function bindMechanicSidebarToggle() {
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarOverlay = document.getElementById('sidebarOverlay');

  function toggleSidebar() {
    if (sidebar) sidebar.classList.toggle('show');
    if (sidebarOverlay) sidebarOverlay.classList.toggle('d-none');
  }

  if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);
  if (sidebarOverlay) sidebarOverlay.addEventListener('click', toggleSidebar);
}

async function initMechanicChrome(pageTitle, callback = null, activeHref = null) {
  const v = new Date().getTime();

  await Promise.all([
    loadComponent('sidebar-container', 'components/sidebar.html?v=' + v, () => {
      setActiveSidebarLink();
      if (activeHref) {
        const activeLink = document.querySelector(`.sidebar-link[href="${activeHref}"]`);
        if (activeLink) activeLink.classList.add('active');
      }
    }),
    loadComponent('topbar-container', 'components/topbar.html?v=' + v, () => {
      const titleEl = document.getElementById('topbar-title');
      if (titleEl) titleEl.textContent = pageTitle;
    })
  ]);

  bindMechanicSidebarToggle();

  if (callback && typeof callback === 'function') {
    callback();
  }
}

async function mechanicCheckLocationSet() {
  const token = localStorage.getItem('garage_token');
  if (!token) {
    window.location.href = 'index.html';
    return;
  }

  try {
    const res = await fetch('http://localhost:8000/api/garage-auth/me', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) {
      window.location.href = 'index.html';
      return;
    }

    const garage = await res.json();
    const loc = garage.location;
    if (!loc || !loc.latitude || !loc.longitude) {
      window.location.href = 'set-location.html';
    }
  } catch {
    /* silent */
  }
}

const API_BASE = window.API_BASE || ((window.location.protocol === 'http:' || window.location.protocol === 'https:') ? `${window.location.protocol}//${window.location.hostname}:8000` : 'http://localhost:8000');

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

async function fetchCustomerFromApi() {
  const token = localStorage.getItem('gnm_token');
  if (!token) return null;

  try {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

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
  
  let gnmUser = getStoredCustomer();
  const token = localStorage.getItem('gnm_token');

  if ((!gnmUser || !gnmUser.name) && token) {
    gnmUser = await fetchCustomerFromApi();
  } else if (token && gnmUser && !gnmUser.profile_image) {
    const freshUser = await fetchCustomerFromApi();
    if (freshUser) gnmUser = freshUser;
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
    
    newMenuBtn.addEventListener('click', function() {
      this.classList.toggle('active');
      mobileMenu.classList.toggle('active');
      const isExpanded = this.classList.contains('active');
      this.setAttribute('aria-expanded', isExpanded);
    });
  }

  await updateCustomerNav();
}
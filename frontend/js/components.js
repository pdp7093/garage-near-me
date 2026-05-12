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

function initCustomerMenu() {
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
}

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


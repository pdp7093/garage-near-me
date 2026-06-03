/**
 * mechanic-auth.js
 * Session and authentication management for mechanic portal
 */



const MECHANIC_AUTH = {
  // Check if user is logged in
  isLoggedIn() {
    return !!localStorage.getItem('garage_token');
  },

  // Get stored token
  getToken() {
    return localStorage.getItem('garage_token');
  },

  // Get mechanic info from session
  getMechanicInfo() {
    const info = localStorage.getItem('mechanic_info');
    return info ? JSON.parse(info) : null;
  },

  // Store login session
  setSession(token, mechnicInfo) {
    localStorage.setItem('garage_token', token);
    if (mechnicInfo) {
      localStorage.setItem('mechanic_info', JSON.stringify(mechnicInfo));
    }
  },

  // Clear session on logout
  logout() {
    localStorage.removeItem('garage_token');
    localStorage.removeItem('mechanic_info');
    window.location.href = 'index';
  },

  // Check if session is valid, redirect to login if not
  checkSession() {
    if (!this.isLoggedIn()) {
      window.location.href = 'index';
      return false;
    }
    return true;
  },

  // Verify token with backend
  async verifyToken() {
    const token = this.getToken();
    if (!token) {
      this.clearSession();
      return false;
    }

    try {
      const response = await fetch(getApiBase() + '/garage-auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        this.clearSession();
        return false;
      }

      return true;
    } catch (error) {
      console.error('Token verification failed:', error);
      this.clearSession();
      return false;
    }
  },

  // Clear session data
  clearSession() {
    localStorage.removeItem('garage_token');
    localStorage.removeItem('mechanic_info');
  }
};

// Automatically check session on page load for protected pages
window.addEventListener('DOMContentLoaded', function() {
  // Only check on protected mechanic pages (not on index.html)
  const currentPage = window.location.pathname.split('/').pop() || '';
  
  // Skip session check on login/index pages
  if (currentPage === 'index' || currentPage === '') {
    return;
  }

  // For all other mechanic pages, enforce session check
  if (!MECHANIC_AUTH.isLoggedIn()) {
    window.location.href = 'index';
  }
});

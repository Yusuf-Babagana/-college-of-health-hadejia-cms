(function () {
  const root = document.documentElement;
  const STORAGE_KEY = 'cohst-theme';

  function applyTheme(theme) {
    root.setAttribute('data-bs-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    document.querySelectorAll('[data-theme-icon]').forEach((el) => {
      el.className = theme === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
    });
  }

  const saved = localStorage.getItem(STORAGE_KEY)
    || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  applyTheme(saved);

  document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('themeToggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const current = root.getAttribute('data-bs-theme');
        applyTheme(current === 'dark' ? 'light' : 'dark');
      });
    }

    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('appSidebar');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');

    function closeSidebar() {
      sidebar.classList.remove('show');
      sidebarBackdrop?.classList.remove('show');
    }

    if (sidebarToggle && sidebar) {
      sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('show');
        sidebarBackdrop?.classList.toggle('show');
      });
    }

    if (sidebarBackdrop) {
      sidebarBackdrop.addEventListener('click', closeSidebar);
    }

    if (sidebar) {
      sidebar.querySelectorAll('.nav-link').forEach((link) => {
        link.addEventListener('click', () => {
          if (window.matchMedia('(max-width: 991.98px)').matches) {
            closeSidebar();
          }
        });
      });
    }
  });
})();

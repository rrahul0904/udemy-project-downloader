const THEME_KEY = 'course-intelligence-theme';

function preferredTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
  document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
    button.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`);
    button.title = `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`;
    button.textContent = theme === 'dark' ? '☀' : '◐';
  });
}

export function initCourseIntelligenceOS() {
  applyTheme(preferredTheme());
  document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
    button.addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
  });

  const pathname = window.location.pathname;
  document.querySelectorAll('[data-mode-link]').forEach((link) => {
    const mode = link.dataset.modeLink;
    const active = mode === 'home'
      ? pathname === '/home' || pathname === '/library'
      : mode === 'acquire'
        ? pathname === '/' || pathname === '/acquire'
        : mode === 'learn'
          ? pathname === '/learn' || pathname === '/viewer'
          : mode === 'work'
            ? pathname === '/lab'
            : mode === 'files'
              ? pathname === '/files-ui'
              : mode === 'settings' && pathname === '/settings';
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCourseIntelligenceOS, { once: true });
} else {
  initCourseIntelligenceOS();
}

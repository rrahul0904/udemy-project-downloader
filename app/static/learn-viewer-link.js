const viewerLink = document.querySelector('#open-media');

function refreshViewerLink() {
  const active = document.querySelector('.lesson-button.active');
  if (!viewerLink || !active?.dataset.lessonId) return;
  const expected = `/viewer?lesson=${encodeURIComponent(active.dataset.lessonId)}`;
  if (viewerLink.getAttribute('href') !== expected) viewerLink.setAttribute('href', expected);
  if (viewerLink.hidden) viewerLink.hidden = false;
  viewerLink.textContent = 'Open synced viewer';
}

const observer = new MutationObserver(refreshViewerLink);
observer.observe(document.querySelector('#lesson-workspace'), {
  attributes: true,
  subtree: true,
  attributeFilter: ['hidden', 'href', 'class'],
});
observer.observe(document.querySelector('#library'), {
  childList: true,
  subtree: true,
  attributes: true,
  attributeFilter: ['class'],
});

document.addEventListener('click', (event) => {
  if (event.target.closest('.lesson-button, #library-search-results button')) {
    queueMicrotask(refreshViewerLink);
  }
});

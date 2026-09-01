const params = new URLSearchParams(window.location.search);
const lessonId = params.get('lesson');

const state = {
  lesson: null,
  transcript: null,
  activeIndex: -1,
  progress: null,
  lastProgressSave: 0,
};

const titleEl = document.querySelector('#lesson-title');
const metaEl = document.querySelector('#lesson-meta');
const errorEl = document.querySelector('#viewer-error');
const videoEl = document.querySelector('#media-player');
const audioEl = document.querySelector('#audio-player');
const noMediaEl = document.querySelector('#no-media');
const sourceEl = document.querySelector('#transcript-source');
const searchEl = document.querySelector('#transcript-search');
const countEl = document.querySelector('#search-count');
const transcriptEl = document.querySelector('#transcript');
const autoScrollEl = document.querySelector('#auto-scroll');
const showTimestampsEl = document.querySelector('#show-timestamps');
const progressStatusEl = document.querySelector('#progress-status');
const completeEl = document.querySelector('#mark-complete');

function encodedFilePath(path) {
  return String(path).split('/').map(encodeURIComponent).join('/');
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  })[char]);
}

function formatTime(ms) {
  if (ms == null) return '—';
  const total = Math.max(0, Math.floor(Number(ms) / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    : `${minutes}:${String(seconds).padStart(2, '0')}`;
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      if (payload?.detail) message = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
    } catch (_) {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function currentPlayer() {
  if (!videoEl.hidden) return videoEl;
  if (!audioEl.hidden) return audioEl;
  return null;
}

function configureMedia() {
  const path = state.lesson?.media_path;
  videoEl.hidden = true;
  audioEl.hidden = true;
  noMediaEl.hidden = true;
  if (!path) {
    noMediaEl.hidden = false;
    return;
  }
  const src = `/files/${encodedFilePath(path)}`;
  const audio = /\.(mp3|m4a|wav|ogg|flac)$/i.test(path);
  const player = audio ? audioEl : videoEl;
  player.src = src;
  player.hidden = false;
  player.addEventListener('loadedmetadata', restorePosition, { once: true });
  player.addEventListener('timeupdate', onTimeUpdate);
  player.addEventListener('pause', () => saveProgress(false).catch(showError));
  player.addEventListener('ended', () => saveProgress(true).catch(showError));
}

function restorePosition() {
  const player = currentPlayer();
  const position = Number(state.progress?.last_position_ms || 0) / 1000;
  if (player && Number.isFinite(position) && position > 0 && position < player.duration) {
    player.currentTime = position;
  }
}

function sourceLabel(item) {
  const language = item.language && item.language !== 'und' ? item.language : 'unknown language';
  return `${language} · ${item.source_kind || 'imported'} · v${item.version || 1}`;
}

async function loadTranscript(transcriptId) {
  state.transcript = await api(`/api/v1/transcripts/${encodeURIComponent(transcriptId)}`);
  state.activeIndex = -1;
  renderTranscript();
  updateExportLinks();
  onTimeUpdate();
}

function renderTranscript() {
  const query = searchEl.value.trim().toLowerCase();
  let matches = 0;
  const segments = state.transcript?.segments || [];
  transcriptEl.innerHTML = segments.map((segment, index) => {
    const text = String(segment.text || '');
    const match = query && text.toLowerCase().includes(query);
    if (match) matches += 1;
    return `<button class="segment ${match ? 'match' : ''}" type="button" data-index="${index}" data-start="${segment.start_ms ?? ''}">
      <span class="segment-time">${formatTime(segment.start_ms)}</span>
      <span class="segment-text">${escapeHtml(text)}</span>
    </button>`;
  }).join('') || '<p class="empty">No readable transcript segments.</p>';
  transcriptEl.classList.toggle('hide-timestamps', !showTimestampsEl.checked);
  countEl.textContent = query ? `${matches} match${matches === 1 ? '' : 'es'}` : `${segments.length} segments`;
  transcriptEl.querySelectorAll('.segment').forEach((button) => {
    button.addEventListener('click', () => seekToSegment(Number(button.dataset.index)));
  });
}

function seekToSegment(index) {
  const segment = state.transcript?.segments?.[index];
  if (!segment) return;
  const player = currentPlayer();
  if (player && segment.start_ms != null) {
    player.currentTime = Number(segment.start_ms) / 1000;
    player.play().catch(() => {});
  }
  activateSegment(index, true);
}

function findActiveSegment(positionMs) {
  const segments = state.transcript?.segments || [];
  let low = 0;
  let high = segments.length - 1;
  let candidate = -1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const start = segments[mid].start_ms;
    if (start == null || Number(start) > positionMs) {
      high = mid - 1;
    } else {
      candidate = mid;
      low = mid + 1;
    }
  }
  if (candidate < 0) return -1;
  const end = segments[candidate].end_ms;
  if (end != null && positionMs > Number(end) && candidate + 1 < segments.length) {
    return candidate + 1;
  }
  return candidate;
}

function activateSegment(index, forceScroll = false) {
  if (index < 0 || index === state.activeIndex) return;
  const previous = transcriptEl.querySelector('.segment.active');
  if (previous) previous.classList.remove('active');
  const next = transcriptEl.querySelector(`.segment[data-index="${index}"]`);
  if (!next) return;
  next.classList.add('active');
  next.setAttribute('aria-current', 'true');
  if (previous) previous.removeAttribute('aria-current');
  state.activeIndex = index;
  if (forceScroll || autoScrollEl.checked) {
    next.scrollIntoView({ block: 'center', behavior: forceScroll ? 'smooth' : 'auto' });
  }
}

function onTimeUpdate() {
  const player = currentPlayer();
  if (!player || !state.transcript) return;
  const positionMs = Math.floor(player.currentTime * 1000);
  activateSegment(findActiveSegment(positionMs));
  const now = Date.now();
  if (now - state.lastProgressSave >= 5000) {
    state.lastProgressSave = now;
    saveProgress(false).catch(showError);
  }
}

async function saveProgress(completed) {
  const player = currentPlayer();
  const lastPosition = player ? Math.floor(player.currentTime * 1000) : Number(state.progress?.last_position_ms || 0);
  const payload = await api(`/api/v1/lessons/${encodeURIComponent(lessonId)}/progress`, {
    method: 'PUT',
    body: JSON.stringify({
      last_position_ms: lastPosition,
      completed: Boolean(completed || state.progress?.completed),
    }),
  });
  state.progress = payload;
  completeEl.textContent = payload.completed ? 'Completed ✓' : 'Mark lesson complete';
  progressStatusEl.textContent = `Saved at ${formatTime(payload.last_position_ms)}`;
  window.setTimeout(() => {
    if (progressStatusEl.textContent.startsWith('Saved')) progressStatusEl.textContent = '';
  }, 1500);
}

function updateExportLinks() {
  const id = encodeURIComponent(state.transcript.id);
  for (const format of ['txt', 'json', 'srt', 'vtt']) {
    const link = document.querySelector(`#export-${format}`);
    link.href = `/api/v1/transcripts/${id}/export?format=${format}`;
    const timed = Boolean(state.transcript.has_timestamps);
    const disabled = (format === 'srt' || format === 'vtt') && !timed;
    link.classList.toggle('disabled', disabled);
    link.setAttribute('aria-disabled', String(disabled));
    if (disabled) link.removeAttribute('href');
  }
}

async function init() {
  if (!lessonId) throw new Error('Missing lesson id. Open the viewer from Course Intelligence.');
  const [lesson, progress] = await Promise.all([
    api(`/api/v1/lessons/${encodeURIComponent(lessonId)}`),
    api(`/api/v1/lessons/${encodeURIComponent(lessonId)}/progress`),
  ]);
  state.lesson = lesson;
  state.progress = progress;
  titleEl.textContent = lesson.title;
  metaEl.textContent = [lesson.source_platform, lesson.uploader, lesson.duration ? `${Math.round(lesson.duration / 60)} min` : null]
    .filter(Boolean).join(' · ');
  completeEl.textContent = progress.completed ? 'Completed ✓' : 'Mark lesson complete';

  const variants = lesson.transcripts || [];
  if (!variants.length) throw new Error('This lesson has no normalized transcript variants.');
  sourceEl.innerHTML = variants.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(sourceLabel(item))}</option>`).join('');
  configureMedia();
  await loadTranscript(variants[0].id);
}

function showError(error) {
  console.error(error);
  errorEl.textContent = error?.message || String(error);
  errorEl.hidden = false;
}

sourceEl.addEventListener('change', () => loadTranscript(sourceEl.value).catch(showError));
searchEl.addEventListener('input', renderTranscript);
showTimestampsEl.addEventListener('change', () => transcriptEl.classList.toggle('hide-timestamps', !showTimestampsEl.checked));
completeEl.addEventListener('click', () => saveProgress(true).catch(showError));

window.addEventListener('pagehide', () => {
  const player = currentPlayer();
  if (!lessonId || !player) return;
  fetch(`/api/v1/lessons/${encodeURIComponent(lessonId)}/progress`, {
    method: 'PUT',
    keepalive: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      last_position_ms: Math.floor(player.currentTime * 1000),
      completed: Boolean(state.progress?.completed),
    }),
  }).catch(() => {});
});

init().catch(showError);

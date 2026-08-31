const state = { library: null, lesson: null, transcript: null, bookmarks: [] };

const libraryEl = document.querySelector('#library');
const courseCountEl = document.querySelector('#course-count');
const lessonCountEl = document.querySelector('#lesson-count');
const filterEl = document.querySelector('#lesson-filter');
const librarySearchEl = document.querySelector('#library-search');
const librarySearchResultsEl = document.querySelector('#library-search-results');
const emptyStateEl = document.querySelector('#empty-state');
const workspaceEl = document.querySelector('#lesson-workspace');
const transcriptEl = document.querySelector('#transcript');
const transcriptSearchEl = document.querySelector('#transcript-search');
const searchCountEl = document.querySelector('#search-count');
const notesEl = document.querySelector('#lesson-notes');
const noteStatusEl = document.querySelector('#note-status');
const bookmarksEl = document.querySelector('#bookmark-list');
let librarySearchTimer = null;

function encodedFilePath(path) {
  return path.split('/').map(encodeURIComponent).join('/');
}

function formatTime(ms) {
  if (ms == null) return '—';
  const total = Math.floor(ms / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}` : `${minutes}:${String(seconds).padStart(2, '0')}`;
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

async function loadLibrary() {
  libraryEl.innerHTML = '<p class="muted">Indexing downloaded transcripts…</p>';
  state.library = await api('/api/library', { headers: {} });
  courseCountEl.textContent = state.library.course_count;
  lessonCountEl.textContent = state.library.lesson_count;
  renderLibrary();
}

function renderLibrary() {
  const query = filterEl.value.trim().toLowerCase();
  const courses = state.library?.courses || [];
  const blocks = [];
  for (const course of courses) {
    const lessons = course.lessons.filter((lesson) => !query || `${course.title} ${lesson.title} ${lesson.transcript_path}`.toLowerCase().includes(query));
    if (!lessons.length) continue;
    const lessonHtml = lessons.map((lesson) => `
      <button class="lesson-button ${state.lesson?.id === lesson.id ? 'active' : ''}" data-course="${escapeHtml(course.title)}" data-lesson-id="${lesson.id}">
        ${escapeHtml(lesson.title)}
        <small>${escapeHtml(lesson.language || lesson.transcript_format.toUpperCase())}</small>
      </button>`).join('');
    blocks.push(`<section class="course"><button type="button"><span>${escapeHtml(course.title)}</span><span>${lessons.length}</span></button><div class="course-lessons">${lessonHtml}</div></section>`);
  }
  libraryEl.innerHTML = blocks.join('') || '<p class="muted">No compatible transcripts found yet. Download subtitles with a course or add VTT/SRT/TXT/JSON3 files under downloads.</p>';
  libraryEl.querySelectorAll('.lesson-button').forEach((button) => button.addEventListener('click', () => openLesson(button.dataset.lessonId, button.dataset.course)));
}

function findLesson(id) {
  for (const course of state.library?.courses || []) {
    const lesson = course.lessons.find((item) => item.id === id);
    if (lesson) return { course, lesson };
  }
  return null;
}

async function openLesson(id, courseTitle, seekMs = null) {
  const found = findLesson(id);
  if (!found) return;
  state.lesson = found.lesson;
  renderLibrary();

  const [transcript, note, bookmarkPayload] = await Promise.all([
    api(`/api/learning/transcript?path=${encodeURIComponent(state.lesson.transcript_path)}`, { headers: {} }),
    api(`/api/learning/lessons/${encodeURIComponent(state.lesson.id)}/notes`, { headers: {} }),
    api(`/api/learning/lessons/${encodeURIComponent(state.lesson.id)}/bookmarks`, { headers: {} }),
  ]);
  state.transcript = transcript;
  state.bookmarks = bookmarkPayload.bookmarks || [];

  emptyStateEl.hidden = true;
  workspaceEl.hidden = false;
  document.querySelector('#lesson-course').textContent = courseTitle || found.course.title;
  document.querySelector('#lesson-title').textContent = state.lesson.title;
  document.querySelector('#lesson-meta').innerHTML = [
    `${state.transcript.word_count.toLocaleString()} words`,
    state.transcript.has_timestamps ? 'Timestamped' : 'Plain text',
    state.lesson.language || state.lesson.transcript_format.toUpperCase(),
  ].map((value) => `<span>${escapeHtml(value)}</span>`).join('');

  const media = document.querySelector('#open-media');
  if (state.lesson.media_path) {
    media.href = `/files/${encodedFilePath(state.lesson.media_path)}`;
    media.hidden = false;
  } else {
    media.hidden = true;
  }

  notesEl.value = note.body || '';
  transcriptSearchEl.value = '';
  searchCountEl.textContent = '';
  renderTranscript();
  renderBookmarks();
  if (seekMs != null) scrollToTimestamp(seekMs);
}

function renderTranscript() {
  const query = transcriptSearchEl.value.trim().toLowerCase();
  let matches = 0;
  transcriptEl.innerHTML = (state.transcript?.segments || []).map((segment, index) => {
    const match = query && segment.text.toLowerCase().includes(query);
    if (match) matches += 1;
    const saved = state.bookmarks.some((item) => item.segment_index === index);
    return `<article class="segment ${match ? 'match' : ''}" data-index="${index}" data-start="${segment.start ?? ''}">
      <button class="timestamp" type="button" data-seek="${segment.start ?? ''}">${formatTime(segment.start)}</button>
      <p>${escapeHtml(segment.text)}</p>
      <button class="bookmark ${saved ? 'saved' : ''}" type="button" aria-label="Bookmark transcript segment">${saved ? '★' : '☆'}</button>
    </article>`;
  }).join('') || '<p class="muted" style="padding:16px">This transcript contains no readable segments.</p>';

  searchCountEl.textContent = query ? `${matches} match${matches === 1 ? '' : 'es'}` : '';
  transcriptEl.querySelectorAll('.bookmark').forEach((button) => button.addEventListener('click', () => toggleBookmark(Number(button.closest('.segment').dataset.index)).catch(showError)));
  transcriptEl.querySelectorAll('.timestamp').forEach((button) => button.addEventListener('click', () => openAtTimestamp(Number(button.dataset.seek))));
}

function openAtTimestamp(ms) {
  if (!state.lesson?.media_path || !Number.isFinite(ms)) return;
  const seconds = Math.floor(ms / 1000);
  window.open(`/files/${encodedFilePath(state.lesson.media_path)}#t=${seconds}`, '_blank', 'noopener');
}

function scrollToTimestamp(ms) {
  if (!Number.isFinite(Number(ms))) return;
  const segments = [...transcriptEl.querySelectorAll('.segment')];
  if (!segments.length) return;
  let best = segments[0];
  let bestDistance = Infinity;
  for (const element of segments) {
    const start = Number(element.dataset.start);
    if (!Number.isFinite(start)) continue;
    const distance = Math.abs(start - Number(ms));
    if (distance < bestDistance) {
      best = element;
      bestDistance = distance;
    }
  }
  best.scrollIntoView({ behavior: 'smooth', block: 'center' });
  best.classList.add('match');
}

async function toggleBookmark(index) {
  const segment = state.transcript.segments[index];
  const existing = state.bookmarks.find((item) => item.segment_index === index);
  if (existing) {
    await api(`/api/learning/bookmarks/${encodeURIComponent(existing.id)}`, { method: 'DELETE' });
  } else {
    await api(`/api/learning/lessons/${encodeURIComponent(state.lesson.id)}/bookmarks`, {
      method: 'POST',
      body: JSON.stringify({
        segment_index: index,
        start_ms: segment.start,
        end_ms: segment.end,
        text: segment.text,
      }),
    });
  }
  const payload = await api(`/api/learning/lessons/${encodeURIComponent(state.lesson.id)}/bookmarks`, { headers: {} });
  state.bookmarks = payload.bookmarks || [];
  renderTranscript();
  renderBookmarks();
}

function renderBookmarks() {
  if (!state.bookmarks.length) {
    bookmarksEl.innerHTML = '<p class="muted">No bookmarks yet. Use ☆ next to any transcript segment.</p>';
    return;
  }
  bookmarksEl.innerHTML = state.bookmarks.map((item) => `<article class="bookmark-card"><button type="button" data-start="${item.start_ms ?? ''}"><strong>${formatTime(item.start_ms)}</strong><span>${escapeHtml(item.text)}</span></button></article>`).join('');
  bookmarksEl.querySelectorAll('button[data-start]').forEach((button) => button.addEventListener('click', () => {
    setTab('transcript');
    scrollToTimestamp(Number(button.dataset.start));
  }));
}

async function saveNotes() {
  if (!state.lesson) return;
  noteStatusEl.textContent = 'Saving…';
  await api(`/api/learning/lessons/${encodeURIComponent(state.lesson.id)}/notes`, {
    method: 'PUT',
    body: JSON.stringify({ body: notesEl.value }),
  });
  noteStatusEl.textContent = 'Saved';
  setTimeout(() => { noteStatusEl.textContent = ''; }, 1600);
}

function exportNotes() {
  if (!state.lesson) return;
  const body = `# ${state.lesson.title}\n\n${notesEl.value || '_No personal notes yet._'}\n\n## Source\n\nTranscript: ${state.lesson.transcript_path}\n`;
  const blob = new Blob([body], { type: 'text/markdown;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${state.lesson.title.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'lesson'}-notes.md`;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function searchLibrary() {
  const query = librarySearchEl.value.trim();
  if (!query) {
    librarySearchResultsEl.innerHTML = '';
    return;
  }
  const payload = await api(`/api/learning/search?q=${encodeURIComponent(query)}&limit=30`, { headers: {} });
  if (!payload.hits.length) {
    librarySearchResultsEl.innerHTML = '<p class="muted">No transcript matches.</p>';
    return;
  }
  librarySearchResultsEl.innerHTML = payload.hits.map((hit) => {
    const snippet = String(hit.snippet || '').replace(/<\/?mark>/g, '');
    return `<button type="button" data-lesson-id="${escapeHtml(hit.lesson_id)}" data-course="${escapeHtml(hit.course_title)}" data-start="${hit.start_ms ?? ''}"><strong>${escapeHtml(hit.course_title)} · ${escapeHtml(hit.lesson_title)}</strong><span>${formatTime(hit.start_ms)} — ${escapeHtml(snippet)}</span></button>`;
  }).join('');
  librarySearchResultsEl.querySelectorAll('button').forEach((button) => button.addEventListener('click', () => openLesson(button.dataset.lessonId, button.dataset.course, Number(button.dataset.start)).catch(showError)));
}

function setTab(name) {
  document.querySelectorAll('.tab').forEach((button) => button.classList.toggle('active', button.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach((panel) => { panel.hidden = panel.id !== `tab-${name}`; });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}

function showError(error) {
  console.error(error);
  noteStatusEl.textContent = error.message || String(error);
  if (!state.library) libraryEl.innerHTML = `<p class="muted">${escapeHtml(error.message || String(error))}</p>`;
}

document.querySelector('#refresh-library').addEventListener('click', () => loadLibrary().catch(showError));
filterEl.addEventListener('input', renderLibrary);
librarySearchEl.addEventListener('input', () => {
  clearTimeout(librarySearchTimer);
  librarySearchTimer = setTimeout(() => searchLibrary().catch(showError), 250);
});
transcriptSearchEl.addEventListener('input', renderTranscript);
document.querySelector('#save-notes').addEventListener('click', () => saveNotes().catch(showError));
document.querySelector('#export-notes').addEventListener('click', exportNotes);
document.querySelectorAll('.tab').forEach((button) => button.addEventListener('click', () => setTab(button.dataset.tab)));

loadLibrary().catch(showError);

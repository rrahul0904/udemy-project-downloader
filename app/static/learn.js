const state = { library: null, lesson: null, transcript: null, bookmarks: [] };

const libraryEl = document.querySelector('#library');
const courseCountEl = document.querySelector('#course-count');
const lessonCountEl = document.querySelector('#lesson-count');
const filterEl = document.querySelector('#lesson-filter');
const emptyStateEl = document.querySelector('#empty-state');
const workspaceEl = document.querySelector('#lesson-workspace');
const transcriptEl = document.querySelector('#transcript');
const transcriptSearchEl = document.querySelector('#transcript-search');
const searchCountEl = document.querySelector('#search-count');
const notesEl = document.querySelector('#lesson-notes');
const noteStatusEl = document.querySelector('#note-status');
const bookmarksEl = document.querySelector('#bookmark-list');

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

function storageKey(kind) {
  return state.lesson ? `course-intelligence:${kind}:${state.lesson.id}` : '';
}

async function loadLibrary() {
  libraryEl.innerHTML = '<p class="muted">Scanning downloaded transcripts…</p>';
  const response = await fetch('/api/library');
  if (!response.ok) throw new Error('Unable to load the local course library.');
  state.library = await response.json();
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

async function openLesson(id, courseTitle) {
  const found = findLesson(id);
  if (!found) return;
  state.lesson = found.lesson;
  renderLibrary();

  const response = await fetch(`/api/learning/transcript?path=${encodeURIComponent(state.lesson.transcript_path)}`);
  if (!response.ok) throw new Error('Unable to parse this transcript.');
  state.transcript = await response.json();
  state.bookmarks = JSON.parse(localStorage.getItem(storageKey('bookmarks')) || '[]');

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

  notesEl.value = localStorage.getItem(storageKey('notes')) || '';
  transcriptSearchEl.value = '';
  searchCountEl.textContent = '';
  renderTranscript();
  renderBookmarks();
}

function renderTranscript() {
  const query = transcriptSearchEl.value.trim().toLowerCase();
  let matches = 0;
  transcriptEl.innerHTML = (state.transcript?.segments || []).map((segment, index) => {
    const match = query && segment.text.toLowerCase().includes(query);
    if (match) matches += 1;
    const saved = state.bookmarks.some((item) => item.index === index);
    return `<article class="segment ${match ? 'match' : ''}" data-index="${index}">
      <button class="timestamp" type="button" data-seek="${segment.start ?? ''}">${formatTime(segment.start)}</button>
      <p>${escapeHtml(segment.text)}</p>
      <button class="bookmark ${saved ? 'saved' : ''}" type="button" aria-label="Bookmark transcript segment">${saved ? '★' : '☆'}</button>
    </article>`;
  }).join('') || '<p class="muted" style="padding:16px">This transcript contains no readable segments.</p>';

  searchCountEl.textContent = query ? `${matches} match${matches === 1 ? '' : 'es'}` : '';
  transcriptEl.querySelectorAll('.bookmark').forEach((button) => button.addEventListener('click', () => toggleBookmark(Number(button.closest('.segment').dataset.index))));
  transcriptEl.querySelectorAll('.timestamp').forEach((button) => button.addEventListener('click', () => openAtTimestamp(Number(button.dataset.seek))));
}

function openAtTimestamp(ms) {
  if (!state.lesson?.media_path || !Number.isFinite(ms)) return;
  const seconds = Math.floor(ms / 1000);
  window.open(`/files/${encodedFilePath(state.lesson.media_path)}#t=${seconds}`, '_blank', 'noopener');
}

function toggleBookmark(index) {
  const segment = state.transcript.segments[index];
  const existing = state.bookmarks.findIndex((item) => item.index === index);
  if (existing >= 0) state.bookmarks.splice(existing, 1);
  else state.bookmarks.push({ index, start: segment.start, text: segment.text });
  localStorage.setItem(storageKey('bookmarks'), JSON.stringify(state.bookmarks));
  renderTranscript();
  renderBookmarks();
}

function renderBookmarks() {
  if (!state.bookmarks.length) {
    bookmarksEl.innerHTML = '<p class="muted">No bookmarks yet. Use ☆ next to any transcript segment.</p>';
    return;
  }
  bookmarksEl.innerHTML = state.bookmarks.sort((a, b) => (a.start || 0) - (b.start || 0)).map((item) => `<article class="bookmark-card"><strong>${formatTime(item.start)}</strong><span>${escapeHtml(item.text)}</span></article>`).join('');
}

function saveNotes() {
  if (!state.lesson) return;
  localStorage.setItem(storageKey('notes'), notesEl.value);
  noteStatusEl.textContent = 'Saved locally';
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

function setTab(name) {
  document.querySelectorAll('.tab').forEach((button) => button.classList.toggle('active', button.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach((panel) => { panel.hidden = panel.id !== `tab-${name}`; });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}

document.querySelector('#refresh-library').addEventListener('click', () => loadLibrary().catch(showError));
filterEl.addEventListener('input', renderLibrary);
transcriptSearchEl.addEventListener('input', renderTranscript);
document.querySelector('#save-notes').addEventListener('click', saveNotes);
document.querySelector('#export-notes').addEventListener('click', exportNotes);
document.querySelectorAll('.tab').forEach((button) => button.addEventListener('click', () => setTab(button.dataset.tab)));

function showError(error) {
  console.error(error);
  libraryEl.innerHTML = `<p class="muted">${escapeHtml(error.message || String(error))}</p>`;
}

loadLibrary().catch(showError);

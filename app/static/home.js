function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const payload = await response.json(); message = payload?.detail || message; } catch (_) {}
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return response.json();
}

function bytes(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / (1024 ** i)).toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}

function flattenLessons(library) {
  return (library.courses || []).flatMap((course) => (course.lessons || []).map((lesson) => ({ course, lesson })));
}

async function enrichLesson(item) {
  const id = encodeURIComponent(item.lesson.id);
  const [progress, note, bookmarks] = await Promise.all([
    api(`/api/v1/lessons/${id}/progress`).catch(() => ({ last_position_ms: 0, completed: 0 })),
    api(`/api/learning/lessons/${id}/notes`).catch(() => ({ body: '' })),
    api(`/api/learning/lessons/${id}/bookmarks`).catch(() => ({ bookmarks: [] })),
  ]);
  return { ...item, progress, note, bookmarks: bookmarks.bookmarks || [] };
}

function renderContinue(items) {
  const root = document.querySelector('#continue-learning');
  if (!items.length) {
    root.innerHTML = '<div class="ci-empty">No lessons are indexed yet. Archive authorized material to start building your library.</div>';
    return;
  }
  root.innerHTML = items.slice(0, 6).map(({ course, lesson, progress, note, bookmarks }) => {
    const completed = Boolean(progress.completed);
    const percent = completed ? 100 : progress.last_position_ms > 0 ? 35 : 0;
    const noteCount = String(note.body || '').trim() ? 1 : 0;
    const viewer = lesson.media_path ? `/viewer?lesson=${encodeURIComponent(lesson.id)}` : `/learn?lesson=${encodeURIComponent(lesson.id)}`;
    return `<article class="ci-card ci-card-pad">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:start"><span class="ci-badge blue">${escapeHtml(lesson.language || lesson.transcript_format || 'transcript')}</span><span class="ci-badge ${completed ? 'green' : ''}">${completed ? 'complete' : percent ? 'in progress' : 'not started'}</span></div>
      <h3 style="margin-top:14px">${escapeHtml(lesson.title)}</h3>
      <p class="ci-secondary" style="margin:5px 0 14px">${escapeHtml(course.title)}</p>
      <div class="ci-progress" aria-label="${percent}% complete"><span style="width:${percent}%"></span></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin:13px 0 16px"><span class="ci-badge">${noteCount} note${noteCount === 1 ? '' : 's'}</span><span class="ci-badge">${bookmarks.length} bookmark${bookmarks.length === 1 ? '' : 's'}</span></div>
      <a class="ci-button-secondary" style="display:inline-flex;text-decoration:none" href="${viewer}">Open ${lesson.media_path ? 'viewer' : 'lesson'}</a>
    </article>`;
  }).join('');
}

function renderCourses(library) {
  const root = document.querySelector('#home-courses');
  const courses = library.courses || [];
  if (!courses.length) {
    root.innerHTML = '<div class="ci-empty">Your course library is empty.</div>';
    return;
  }
  root.innerHTML = courses.map((course) => {
    const lessons = course.lessons || [];
    const transcriptCount = lessons.reduce((sum, lesson) => sum + (lesson.transcripts?.length || (lesson.transcript_path ? 1 : 0)), 0);
    const mediaCount = lessons.filter((lesson) => lesson.media_path).length;
    const platform = lessons.find((lesson) => lesson.source_platform)?.source_platform || 'local';
    return `<article class="ci-card ci-card-pad">
      <div style="display:flex;justify-content:space-between;gap:12px"><span class="ci-badge blue">${escapeHtml(platform)}</span><span class="ci-mono ci-muted" style="font-size:11px">${lessons.length} lessons</span></div>
      <h3 style="margin-top:14px">${escapeHtml(course.title)}</h3>
      <div class="ci-list" style="margin-top:14px"><div class="ci-list-row"><span>Transcript variants</span><strong>${transcriptCount}</strong></div><div class="ci-list-row"><span>Media available</span><strong>${mediaCount}</strong></div></div>
      <a href="/learn" style="display:inline-block;margin-top:14px;color:var(--course-blue);font-weight:750;text-decoration:none">Study course →</a>
    </article>`;
  }).join('');
}

function renderStatus({ jobs, downloads, readiness }) {
  const active = (jobs.jobs || []).filter((job) => ['queued', 'running'].includes(job.status)).length;
  const checks = readiness?.checks || {};
  document.querySelector('#system-status').innerHTML = [
    ['Active jobs', String(active), true],
    ['SQLite', checks.database || 'unknown', checks.database === 'ok'],
    ['FFmpeg', checks.ffmpeg ? 'available' : 'not available', Boolean(checks.ffmpeg)],
    ['yt-dlp', checks.yt_dlp ? 'available' : 'not available', Boolean(checks.yt_dlp)],
    ['Storage', downloads.root || 'local', true],
  ].map(([label, value, ok]) => `<div class="ci-list-row"><span style="display:flex;align-items:center;gap:9px"><span class="ci-status-dot ${ok ? 'ok' : ''}"></span>${escapeHtml(label)}</span><strong class="ci-mono" style="font-size:12px">${escapeHtml(value)}</strong></div>`).join('');
}

async function init() {
  const [library, jobs, downloads, readiness] = await Promise.all([
    api('/api/library'), api('/api/jobs').catch(() => ({ jobs: [] })), api('/api/downloads').catch(() => ({ files: [], usage: {} })), api('/api/readiness').catch(() => ({ checks: {} })),
  ]);
  const lessons = flattenLessons(library);
  const transcriptCount = lessons.reduce((sum, item) => sum + (item.lesson.transcripts?.length || (item.lesson.transcript_path ? 1 : 0)), 0);
  const usage = downloads.usage || {};
  const directUsed = Number(usage.used);
  const used = Number.isFinite(directUsed) ? directUsed : Math.max(0, Number(usage.total || 0) - Number(usage.free || 0));
  document.querySelector('#home-course-count').textContent = library.course_count ?? (library.courses || []).length;
  document.querySelector('#home-lesson-count').textContent = library.lesson_count ?? lessons.length;
  document.querySelector('#home-transcript-count').textContent = transcriptCount;
  document.querySelector('#home-storage').textContent = bytes(used);
  renderCourses(library);
  renderStatus({ jobs, downloads, readiness });
  const enriched = await Promise.all(lessons.slice(0, 8).map(enrichLesson));
  enriched.sort((a, b) => Number(Boolean(a.progress.completed)) - Number(Boolean(b.progress.completed)) || Number(b.progress.last_position_ms || 0) - Number(a.progress.last_position_ms || 0));
  renderContinue(enriched);

  let timer;
  document.querySelector('#home-search').addEventListener('input', (event) => {
    clearTimeout(timer);
    const query = event.target.value.trim();
    timer = setTimeout(async () => {
      const root = document.querySelector('#home-search-results');
      if (!query) { root.innerHTML = ''; return; }
      const payload = await api(`/api/learning/search?q=${encodeURIComponent(query)}&limit=12`).catch(() => ({ hits: [] }));
      root.innerHTML = payload.hits?.length ? payload.hits.map((hit) => `<a class="ci-list-row" style="text-decoration:none" href="/learn?lesson=${encodeURIComponent(hit.lesson_id)}&t=${hit.start_ms || 0}"><span><strong>${escapeHtml(hit.lesson_title)}</strong><small>${escapeHtml(hit.course_title)} · ${escapeHtml(String(hit.snippet || '').replace(/<\/?mark>/g, ''))}</small></span><span class="ci-badge cyan">source</span></a>`).join('') : '<div class="ci-empty">No transcript evidence matched that search.</div>';
    }, 220);
  });
}

init().catch((error) => {
  console.error(error);
  document.querySelector('#continue-learning').innerHTML = `<div class="ci-empty">${escapeHtml(error.message || String(error))}</div>`;
});

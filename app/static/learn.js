const state = { library: null, course: null, lesson: null, transcript: null, bookmarks: [], progress: null };
const $ = (selector) => document.querySelector(selector);
const libraryEl = $('#library');
const courseCountEl = $('#course-count');
const lessonCountEl = $('#lesson-count');
const filterEl = $('#lesson-filter');
const librarySearchEl = $('#library-search');
const librarySearchResultsEl = $('#library-search-results');
const emptyStateEl = $('#empty-state');
const workspaceEl = $('#lesson-workspace');
const transcriptEl = $('#transcript');
const transcriptSearchEl = $('#transcript-search');
const searchCountEl = $('#search-count');
const notesEl = $('#lesson-notes');
const noteStatusEl = $('#note-status');
const bookmarksEl = $('#bookmark-list');
let librarySearchTimer = null;
let noteTimer = null;

function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]); }
function formatTime(ms) { if (ms == null || !Number.isFinite(Number(ms))) return '—'; const total=Math.max(0,Math.floor(Number(ms)/1000)); const h=Math.floor(total/3600); const m=Math.floor((total%3600)/60); const s=total%60; return h?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${m}:${String(s).padStart(2,'0')}`; }
function segmentStart(segment) { return segment.start_ms ?? segment.start ?? null; }
function segmentEnd(segment) { return segment.end_ms ?? segment.end ?? null; }
async function api(url, options={}) { const response=await fetch(url,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}}); if(!response.ok){let message=`Request failed (${response.status})`;try{const payload=await response.json();if(payload?.detail)message=typeof payload.detail==='string'?payload.detail:JSON.stringify(payload.detail);}catch(_){}throw new Error(message);} return response.status===204?null:response.json(); }

async function loadLibrary() {
  libraryEl.innerHTML='<p class="muted">Indexing downloaded transcripts…</p>';
  state.library=await api('/api/library',{headers:{}});
  courseCountEl.textContent=state.library.course_count ?? state.library.courses?.length ?? 0;
  lessonCountEl.textContent=state.library.lesson_count ?? (state.library.courses||[]).reduce((n,c)=>n+(c.lessons?.length||0),0);
  renderLibrary();
  const params=new URLSearchParams(location.search); const lesson=params.get('lesson');
  if(lesson) await openLesson(lesson,null,Number(params.get('t')||0));
}

function renderLibrary() {
  const query=filterEl.value.trim().toLowerCase(); const blocks=[];
  for(const course of state.library?.courses||[]) {
    const lessons=(course.lessons||[]).filter((lesson)=>!query||`${course.title} ${lesson.title} ${lesson.language||''}`.toLowerCase().includes(query));
    if(!lessons.length) continue;
    const lessonHtml=lessons.map((lesson)=>`<button class="lesson-button ${state.lesson?.id===lesson.id?'active':''}" data-lesson-id="${escapeHtml(lesson.id)}"><span>${escapeHtml(lesson.title)}</span><small>${escapeHtml(lesson.language||lesson.transcript_format?.toUpperCase()||'source')} · ${lesson.media_path?'media':'transcript'}</small></button>`).join('');
    blocks.push(`<section class="course"><button type="button" aria-expanded="true"><span>${escapeHtml(course.title)}</span><span>${lessons.length}</span></button><div class="course-lessons">${lessonHtml}</div></section>`);
  }
  libraryEl.innerHTML=blocks.join('')||'<p class="muted">No compatible transcripts found yet. Archive authorized material with subtitles to build the library.</p>';
  libraryEl.querySelectorAll('.lesson-button').forEach((button)=>button.addEventListener('click',()=>openLesson(button.dataset.lessonId).catch(showError)));
}

function findLesson(id){for(const course of state.library?.courses||[]){const lesson=(course.lessons||[]).find((item)=>item.id===id);if(lesson)return{course,lesson};}return null;}

async function openLesson(id, _courseTitle=null, seekMs=null) {
  const found=findLesson(id); if(!found) return;
  state.course=found.course; state.lesson=found.lesson; renderLibrary();
  const [detail,note,bookmarkPayload,progress]=await Promise.all([
    api(`/api/v1/lessons/${encodeURIComponent(id)}`),
    api(`/api/learning/lessons/${encodeURIComponent(id)}/notes`),
    api(`/api/learning/lessons/${encodeURIComponent(id)}/bookmarks`),
    api(`/api/v1/lessons/${encodeURIComponent(id)}/progress`).catch(()=>({last_position_ms:0,completed:0})),
  ]);
  state.lesson={...state.lesson,...detail}; state.bookmarks=bookmarkPayload.bookmarks||[]; state.progress=progress;
  const variants=state.lesson.transcripts||[];
  if(variants.length) state.transcript=await api(`/api/v1/transcripts/${encodeURIComponent(variants[0].id)}`);
  else state.transcript=await api(`/api/learning/transcript?path=${encodeURIComponent(state.lesson.transcript_path)}`);

  emptyStateEl.hidden=true; workspaceEl.hidden=false;
  $('#lesson-course').textContent=state.course.title; $('#lesson-title').textContent=state.lesson.title;
  const source=state.transcript.source_kind?`${state.transcript.language||'und'} · ${state.transcript.source_kind} · v${state.transcript.version||1}`:(state.lesson.language||state.lesson.transcript_format?.toUpperCase());
  $('#lesson-meta').innerHTML=[`${Number(state.transcript.word_count||0).toLocaleString()} words`,state.transcript.has_timestamps?'timestamped':'plain text',source,state.progress.completed?'completed':'in progress'].filter(Boolean).map((value)=>`<span>${escapeHtml(value)}</span>`).join('');
  const viewer=$('#open-media'); viewer.href=`/viewer?lesson=${encodeURIComponent(id)}`; viewer.hidden=false;
  notesEl.value=note.body||''; transcriptSearchEl.value=''; searchCountEl.textContent=''; renderTranscript(); renderBookmarks(); renderOverview(); renderFiles();
  setTab('overview');
  if(Number(seekMs)>0){setTab('transcript');scrollToTimestamp(Number(seekMs));}
  window.dispatchEvent(new CustomEvent('ci:lesson-opened',{detail:{course:state.course,lesson:state.lesson,transcript:state.transcript,progress:state.progress}}));
  history.replaceState(null,'',`/learn?lesson=${encodeURIComponent(id)}${Number(seekMs)>0?`&t=${Number(seekMs)}`:''}`);
}

function renderOverview(){const variants=state.lesson.transcripts||[];const attachments=state.lesson.attachments||state.course.attachments||[];$('#lesson-overview').innerHTML=`<div class="ci-grid ci-grid-3"><article class="artifact-card"><span class="ci-eyebrow">SOURCE</span><h4>${variants.length} transcript variant${variants.length===1?'':'s'}</h4><p>${state.lesson.media_path?'Local media is linked to the synchronized viewer.':'Transcript-only mode is available.'}</p></article><article class="artifact-card"><span class="ci-eyebrow">YOUR WORK</span><h4>${state.bookmarks.length} bookmark${state.bookmarks.length===1?'':'s'}</h4><p>${notesEl.value.trim()?'Personal notes saved for this lesson.':'No personal notes yet.'}</p></article><article class="artifact-card"><span class="ci-eyebrow">PROGRESS</span><h4>${state.progress?.completed?'Completed':'Continue learning'}</h4><p>${state.progress?.last_position_ms?`Last saved near ${formatTime(state.progress.last_position_ms)}.`:'No saved playback position yet.'}</p></article></div><div class="ci-privacy"><span>●</span><div>Generated study material is separate from My Notes and should remain tied to source transcript evidence.</div></div>`;}

function renderTranscript(){const query=transcriptSearchEl.value.trim().toLowerCase();let matches=0;transcriptEl.innerHTML=(state.transcript?.segments||[]).map((segment,index)=>{const text=String(segment.text||'');const match=query&&text.toLowerCase().includes(query);if(match)matches++;const segmentIndex=Number(segment.segment_index??index);const saved=state.bookmarks.some((item)=>item.segment_index===segmentIndex);const start=segmentStart(segment);return `<article class="segment ${match?'match':''}" data-index="${segmentIndex}" data-start="${start??''}"><button class="timestamp" type="button" data-seek="${start??''}" aria-label="Open synchronized viewer at ${formatTime(start)}">${formatTime(start)}</button><p>${escapeHtml(text)}</p><button class="bookmark ${saved?'saved':''}" type="button" aria-label="${saved?'Remove bookmark':'Bookmark transcript segment'}">${saved?'★':'☆'}</button></article>`;}).join('')||'<p class="muted" style="padding:16px">This transcript contains no readable segments.</p>';searchCountEl.textContent=query?`${matches} match${matches===1?'':'es'}`:`${state.transcript?.segments?.length||0} segments`;transcriptEl.querySelectorAll('.bookmark').forEach((button)=>button.addEventListener('click',()=>toggleBookmark(Number(button.closest('.segment').dataset.index)).catch(showError)));transcriptEl.querySelectorAll('.timestamp').forEach((button)=>button.addEventListener('click',()=>openAtTimestamp(Number(button.dataset.seek))));}
function openAtTimestamp(ms){if(!state.lesson||!Number.isFinite(ms))return;window.location.href=`/viewer?lesson=${encodeURIComponent(state.lesson.id)}&t=${Math.max(0,Math.floor(ms))}`;}
function scrollToTimestamp(ms){const segments=[...transcriptEl.querySelectorAll('.segment')];let best=null,bestDistance=Infinity;for(const element of segments){const start=Number(element.dataset.start);if(!Number.isFinite(start))continue;const d=Math.abs(start-ms);if(d<bestDistance){best=element;bestDistance=d;}}if(best){best.scrollIntoView({behavior:'smooth',block:'center'});best.classList.add('match');}}
async function toggleBookmark(segmentIndex){const segment=(state.transcript.segments||[]).find((item,index)=>Number(item.segment_index??index)===segmentIndex);if(!segment)return;const existing=state.bookmarks.find((item)=>item.segment_index===segmentIndex);if(existing)await api(`/api/learning/bookmarks/${encodeURIComponent(existing.id)}`,{method:'DELETE'});else await api(`/api/learning/lessons/${encodeURIComponent(state.lesson.id)}/bookmarks`,{method:'POST',body:JSON.stringify({segment_index:segmentIndex,start_ms:segmentStart(segment),end_ms:segmentEnd(segment),text:segment.text})});const payload=await api(`/api/learning/lessons/${encodeURIComponent(state.lesson.id)}/bookmarks`);state.bookmarks=payload.bookmarks||[];renderTranscript();renderBookmarks();renderOverview();}
function renderBookmarks(){if(!state.bookmarks.length){bookmarksEl.innerHTML='<div class="ci-empty">No bookmarks yet. Use ☆ next to any transcript segment.</div>';return;}bookmarksEl.innerHTML=state.bookmarks.map((item)=>`<article class="bookmark-card"><button type="button" data-start="${item.start_ms??''}"><strong>${formatTime(item.start_ms)}</strong><span>${escapeHtml(item.text)}</span></button></article>`).join('');bookmarksEl.querySelectorAll('button[data-start]').forEach((button)=>button.addEventListener('click',()=>{setTab('transcript');scrollToTimestamp(Number(button.dataset.start));}));}
function renderFiles(){const items=state.lesson.attachments||state.course.attachments||[];const root=$('#lesson-files');if(!items.length){root.innerHTML='<div class="ci-empty">No indexed course attachments are available for this selection.</div>';return;}root.innerHTML=items.map((item)=>`<div class="ci-list-row"><span><strong>${escapeHtml(item.filename||item.name)}</strong><small class="ci-mono">${escapeHtml(item.relative_path||item.path||'local attachment')}</small></span><a class="ci-badge orange" href="/lab">Study Lab</a></div>`).join('');}
async function saveNotes(){if(!state.lesson)return;noteStatusEl.textContent='Saving…';await api(`/api/learning/lessons/${encodeURIComponent(state.lesson.id)}/notes`,{method:'PUT',body:JSON.stringify({body:notesEl.value})});noteStatusEl.textContent=`Saved ${new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})}`;renderOverview();}
function exportNotes(){if(!state.lesson)return;const body=`# ${state.lesson.title}\n\n${notesEl.value||'_No personal notes yet._'}\n\n## Source\n\nCourse: ${state.course.title}\n`;const blob=new Blob([body],{type:'text/markdown;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`${state.lesson.title.replace(/[^a-z0-9]+/gi,'-').replace(/^-|-$/g,'').toLowerCase()||'lesson'}-notes.md`;link.click();URL.revokeObjectURL(link.href);}
async function searchLibrary(){const query=librarySearchEl.value.trim();if(!query){librarySearchResultsEl.innerHTML='';return;}const payload=await api(`/api/learning/search?q=${encodeURIComponent(query)}&limit=30`);librarySearchResultsEl.innerHTML=payload.hits?.length?payload.hits.map((hit)=>`<button type="button" data-lesson-id="${escapeHtml(hit.lesson_id)}" data-start="${hit.start_ms??0}"><strong>${escapeHtml(hit.course_title)} · ${escapeHtml(hit.lesson_title)}</strong><span>${formatTime(hit.start_ms)} — ${escapeHtml(String(hit.snippet||'').replace(/<\/?mark>/g,''))}</span></button>`).join(''):'<p class="muted">No transcript matches.</p>';librarySearchResultsEl.querySelectorAll('button').forEach((button)=>button.addEventListener('click',()=>openLesson(button.dataset.lessonId,null,Number(button.dataset.start)).catch(showError)));}
function setTab(name){document.querySelectorAll('.tab').forEach((button)=>{const active=button.dataset.tab===name;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active));});document.querySelectorAll('.tab-panel').forEach((panel)=>{panel.hidden=panel.id!==`tab-${name}`;});}
function showError(error){console.error(error);noteStatusEl.textContent=error.message||String(error);if(!state.library)libraryEl.innerHTML=`<p class="muted">${escapeHtml(error.message||String(error))}</p>`;}

$('#refresh-library').addEventListener('click',()=>loadLibrary().catch(showError));
filterEl.addEventListener('input',renderLibrary);
librarySearchEl.addEventListener('input',()=>{clearTimeout(librarySearchTimer);librarySearchTimer=setTimeout(()=>searchLibrary().catch(showError),220);});
transcriptSearchEl.addEventListener('input',renderTranscript);
$('#save-notes').addEventListener('click',()=>saveNotes().catch(showError));
notesEl.addEventListener('input',()=>{clearTimeout(noteTimer);noteStatusEl.textContent='Unsaved changes';noteTimer=setTimeout(()=>saveNotes().catch(showError),900);});
$('#export-notes').addEventListener('click',exportNotes);
document.querySelectorAll('.tab').forEach((button)=>button.addEventListener('click',()=>setTab(button.dataset.tab)));
loadLibrary().catch(showError);

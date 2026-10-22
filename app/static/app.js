const form = document.querySelector("#job-form");
const formMessage = document.querySelector("#form-message");
const jobsEl = document.querySelector("#jobs");
const logsEl = document.querySelector("#logs");
const detailsEl = document.querySelector("#job-details");
const filesEl = document.querySelector("#files");
const diskEl = document.querySelector("#disk");
const rootEl = document.querySelector("#download-root");
const refreshButton = document.querySelector("#refresh");
const cancelButton = document.querySelector("#cancel-job");
const browserRow = document.querySelector("#browser-row");
const cookiesRow = document.querySelector("#cookies-row");
const urlInput = form.elements.course_url;
const practiceTestsInput = form.elements.include_practice_tests;
const videosInput = form.elements.download_videos;
const modeEl = document.querySelector("#job-mode");

let selectedJobId = null;
let latestJobs = [];
let authTouched = false;
let practiceTouched = false;

for (const input of form.elements.auth_method) {
  input.addEventListener("change", () => {
    authTouched = true;
    syncAuthMode();
  });
}

urlInput.addEventListener("input", syncUrlMode);
practiceTestsInput.addEventListener("change", () => {
  practiceTouched = true;
  syncJobMode();
});
videosInput.addEventListener("change", syncJobMode);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formMessage.textContent = "";

  if (!videosInput.checked && !practiceTestsInput.checked) {
    formMessage.textContent = "Select videos, practice tests, or both.";
    return;
  }

  const submit = form.querySelector("button[type='submit']");
  submit.disabled = true;

  try {
    const data = new FormData(form);
    for (const name of ["subtitles", "auto_subtitles", "include_practice_tests", "download_videos", "confirm_authorized"]) {
      data.set(name, form.elements[name].checked ? "true" : "false");
    }

    const response = await fetch("/api/jobs", {
      method: "POST",
      body: data,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Could not create job.");
    }

    selectedJobId = payload.id;
    form.reset();
    authTouched = false;
    practiceTouched = false;
    form.elements.auth_method.value = "none";
    form.elements.subtitles.checked = true;
    form.elements.include_practice_tests.checked = false;
    form.elements.include_practice_tests.disabled = false;
    form.elements.subtitle_languages.value = "en.*";
    syncUrlMode();
    await refreshAll();
  } catch (error) {
    formMessage.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

refreshButton.addEventListener("click", refreshAll);

cancelButton.addEventListener("click", async () => {
  if (!selectedJobId) return;
  cancelButton.disabled = true;
  await fetch(`/api/jobs/${selectedJobId}`, { method: "DELETE" });
  await refreshAll();
});

async function refreshAll() {
  await Promise.all([loadJobs(), loadDownloads()]);
}

async function loadJobs() {
  const response = await fetch("/api/jobs");
  const payload = await response.json();
  latestJobs = payload.jobs || [];

  if (!selectedJobId && latestJobs.length) {
    selectedJobId = latestJobs[0].id;
  }

  renderJobs();
  renderSelectedLog();
}

function renderJobs() {
  if (!latestJobs.length) {
    jobsEl.innerHTML = `<div class="empty">No jobs yet.</div>`;
    return;
  }

  jobsEl.innerHTML = latestJobs
    .map((job) => {
      const title = courseTitle(job.course_url);
      const created = new Date(job.created_at).toLocaleString();
      const auth =
        job.auth_method === "none"
          ? "no cookies"
          : job.auth_method === "browser"
            ? `browser: ${job.browser}`
            : "cookies.txt";
      const platform = job.platform || "udemy";
      const videoEnabled = job.download_videos !== false;
      const content = platform === "udemy" && job.include_practice_tests
        ? videoEnabled ? "videos + practice tests" : "practice tests only"
        : "videos + resources";
      const components = job.component_statuses || {};
      const componentStatus = [
        videoEnabled && components.video ? `video: ${components.video}` : null,
        job.include_practice_tests && components.practice ? `practice: ${components.practice}` : null,
      ].filter(Boolean).join(" · ");
      return `
        <article class="job ${job.id === selectedJobId ? "active" : ""}" data-job="${job.id}">
          <div class="job-top">
            <span class="job-title" title="${escapeHtml(job.course_url)}">${escapeHtml(title)}</span>
            <span class="status ${job.status}">${escapeHtml(job.status)}</span>
          </div>
          <div class="job-meta">${escapeHtml(created)} · ${escapeHtml(platform)} · ${escapeHtml(job.quality)} · ${escapeHtml(auth)} · ${content}${componentStatus ? ` · ${escapeHtml(componentStatus)}` : ""}</div>
        </article>
      `;
    })
    .join("");

  for (const el of jobsEl.querySelectorAll(".job")) {
    el.addEventListener("click", () => {
      selectedJobId = el.dataset.job;
      renderJobs();
      renderSelectedLog();
    });
  }
}

function syncAuthMode() {
  const mode = form.elements.auth_method.value;
  const useBrowser = mode === "browser";
  const useCookiesFile = mode === "cookies_file";
  browserRow.hidden = !useBrowser;
  cookiesRow.hidden = !useCookiesFile;
  form.elements.browser.disabled = !useBrowser;
  form.elements.cookies_file.disabled = !useCookiesFile;
  if (!useCookiesFile) form.elements.cookies_file.value = "";
  form.elements.cookies_file.required = useCookiesFile;
}

function syncUrlMode() {
  const platform = detectPlatform(urlInput.value);
  if (platform !== "udemy") {
    practiceTestsInput.checked = false;
    practiceTestsInput.disabled = true;
    if (urlInput.value.trim() && !videosInput.checked) videosInput.checked = true;
    if (!authTouched) {
      form.elements.auth_method.value = "none";
    }
  } else {
    practiceTestsInput.disabled = false;
    if (!practiceTouched) {
      practiceTestsInput.checked = true;
    }
    if (!authTouched) form.elements.auth_method.value = "cookies_file";
  }
  syncAuthMode();
  syncJobMode();
}

function syncJobMode() {
  if (videosInput.checked && practiceTestsInput.checked) {
    modeEl.textContent = "Videos and authorized practice tests";
  } else if (practiceTestsInput.checked) {
    modeEl.textContent = "Practice tests only · video downloader skipped";
  } else if (videosInput.checked) {
    modeEl.textContent = "Video and resources only";
  } else {
    modeEl.textContent = "Select at least one option";
  }
}

function renderSelectedLog() {
  const job = latestJobs.find((item) => item.id === selectedJobId);
  if (!job) {
    logsEl.textContent = "No job selected.";
    detailsEl.textContent = "";
    cancelButton.disabled = true;
    return;
  }

  const components = job.component_statuses || {};
  const validation = job.practice_validation;
  const parts = [
    job.download_videos !== false ? `Video: ${components.video || job.status}` : "Video: not requested",
    job.include_practice_tests ? `Practice tests: ${components.practice || job.status}` : "Practice tests: not requested",
  ];
  if (validation) {
    parts.push(`Course discovered: ${validation.course_discovered ? "YES" : "NO"}`);
    parts.push(`Practice sets: ${validation.practice_sets_discovered ?? 0}`);
    parts.push(`Questions: ${validation.questions_retrieved ?? 0} retrieved / ${validation.questions_expected ?? "unknown"} expected`);
    parts.push(`Questions with choices: ${validation.questions_with_answer_choices ?? 0}`);
    parts.push(`Count reconciliation: ${validation.count_reconciliation || "UNKNOWN"}`);
    parts.push(`Answers: ${validation.questions_with_correct_answers ?? 0} · Explanations: ${validation.questions_with_explanations ?? 0}`);
    parts.push(`Exports: ${["json", "html", "markdown", "pdf"]
      .map((format) => `${format.toUpperCase()} ${validation[`${format}_generated`] ? "YES" : "NO"}`)
      .join(" · ")}`);
  }
  detailsEl.textContent = parts.join("\n");
  logsEl.textContent = job.logs.length ? job.logs.join("\n") : "Waiting for output...";
  logsEl.scrollTop = logsEl.scrollHeight;
  cancelButton.disabled = !["queued", "running"].includes(job.status);
}

async function loadDownloads() {
  const response = await fetch("/api/downloads");
  const payload = await response.json();
  rootEl.textContent = payload.root;
  diskEl.textContent = payload.usage ? `${formatBytes(payload.usage.free)} free` : "";

  const files = payload.files || [];
  if (!files.length) {
    filesEl.innerHTML = `<div class="empty">No downloaded files yet.</div>`;
    return;
  }

  filesEl.innerHTML = files
    .filter((file) => file.type === "file")
    .slice(0, 80)
    .map((file) => {
      const href = `/files/${encodePath(file.path)}`;
      return `
        <a class="file" href="${href}" target="_blank" rel="noreferrer">
          <span title="${escapeHtml(file.path)}">${escapeHtml(file.path)}</span>
          <small>${formatBytes(file.size)}</small>
        </a>
      `;
    })
    .join("");
}

function courseTitle(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    if (host === "youtu.be") {
      return parsed.pathname.split("/").filter(Boolean)[0] || host;
    }
    if (host.endsWith("youtube.com") || host.endsWith("youtube-nocookie.com")) {
      const videoId = parsed.searchParams.get("v");
      const playlistId = parsed.searchParams.get("list");
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (videoId) return `youtube-${videoId}`;
      if (parts[0] === "playlist" && playlistId) return `playlist-${playlistId}`;
      if (["shorts", "embed", "live"].includes(parts[0]) && parts[1]) return `youtube-${parts[1]}`;
    }
    const parts = parsed.pathname.split("/").filter(Boolean);
    return parts[parts.length - 1] || parsed.hostname;
  } catch {
    return url;
  }
}

function formatBytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function detectPlatform(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    if (host === "udemy.com" || host.endsWith(".udemy.com")) return "udemy";
    if (
      host === "youtu.be" ||
      host === "youtube.com" ||
      host === "www.youtube.com" ||
      host === "m.youtube.com" ||
      host === "music.youtube.com" ||
      host === "youtube-nocookie.com" ||
      host === "www.youtube-nocookie.com"
    ) {
      return "youtube";
    }
  } catch {
    return null;
  }
  return null;
}

refreshAll();
syncAuthMode();
syncUrlMode();
setInterval(refreshAll, 2500);

const form = document.querySelector("#job-form");
const formMessage = document.querySelector("#form-message");
const jobsEl = document.querySelector("#jobs");
const logsEl = document.querySelector("#logs");
const filesEl = document.querySelector("#files");
const diskEl = document.querySelector("#disk");
const rootEl = document.querySelector("#download-root");
const refreshButton = document.querySelector("#refresh");
const cancelButton = document.querySelector("#cancel-job");
const browserRow = document.querySelector("#browser-row");
const cookiesRow = document.querySelector("#cookies-row");

let selectedJobId = null;
let latestJobs = [];

for (const input of form.elements.auth_method) {
  input.addEventListener("change", syncAuthMode);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formMessage.textContent = "";

  const submit = form.querySelector("button[type='submit']");
  submit.disabled = true;

  try {
    const data = new FormData(form);
    for (const name of ["subtitles", "auto_subtitles", "include_practice_tests", "confirm_authorized"]) {
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
    form.elements.auth_method.value = "browser";
    form.elements.subtitles.checked = true;
    form.elements.include_practice_tests.checked = true;
    form.elements.subtitle_languages.value = "en.*";
    syncAuthMode();
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
      const auth = job.auth_method === "browser" ? `browser: ${job.browser}` : "cookies.txt";
      return `
        <article class="job ${job.id === selectedJobId ? "active" : ""}" data-job="${job.id}">
          <div class="job-top">
            <span class="job-title" title="${escapeHtml(job.course_url)}">${escapeHtml(title)}</span>
            <span class="status ${job.status}">${escapeHtml(job.status)}</span>
          </div>
          <div class="job-meta">${created} · ${escapeHtml(job.quality)} · ${escapeHtml(auth)} · ${job.include_practice_tests ? "tests" : "media"}</div>
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
  const useCookiesFile = mode === "cookies_file";
  browserRow.hidden = useCookiesFile;
  cookiesRow.hidden = !useCookiesFile;
  form.elements.cookies_file.required = useCookiesFile;
}

function renderSelectedLog() {
  const job = latestJobs.find((item) => item.id === selectedJobId);
  if (!job) {
    logsEl.textContent = "No job selected.";
    cancelButton.disabled = true;
    return;
  }

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

refreshAll();
syncAuthMode();
setInterval(refreshAll, 2500);

// Visual Evidence is a separate opt-in workflow for archived local media.
// Image evidence and OCR are unverified: never present inferred diagram links as facts.
const $ = (selector) => document.querySelector(selector);
const analyze = $("#visual-analyze");
const status = $("#visual-status");
const target = $("#visual-evidence");
let lesson = null;
let interval = null;
let generation = 0;

function clearPoll() {
  if (interval !== null) { clearInterval(interval); interval = null; }
}
function message(value) {
  status.textContent = value;
}
function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}
function display(data) {
  target.replaceChildren();
  const items = Array.isArray(data.items) ? data.items : [];
  if (!items.length) {
    target.append(node("div", "ci-empty", data.status === "not_started"
      ? "No visual inspection yet. Analyze an archived video to extract slide, code and diagram evidence."
      : "No sampled frames are ready yet."));
    return;
  }
  const warning = node("p", "visual-disclaimer",
    "Sampled frames and OCR are NOT a complete or independently verified representation of the lecture.");
  target.append(warning);
  for (const [position, item] of items.entries()) {
    const card = node("article", "visual-card");
    const head = node("div", "visual-head");
    head.append(node("strong", "", "Frame " + (position + 1) + " · " + String(item.category || "unclassified")));
    if (Number.isFinite(item.timestamp_ms)) {
      const source = node("a", "visual-time", (item.timestamp_ms / 1000).toFixed(1) + "s · Open in viewer");
      source.href = "/viewer?lesson=" + encodeURIComponent(lesson.id) + "&t=" + encodeURIComponent(item.timestamp_ms);
      head.append(source);
    } else head.append(node("span", "muted", "Timestamp unavailable"));
    card.append(head);
    const basename = String(item.frame_file || "").split("/").pop();
    if (/^(periodic|scene)-\d{4}\.jpg$/.test(basename)) {
      const image = node("img", "visual-frame");
      image.src = "/api/v1/lessons/" + encodeURIComponent(lesson.id)
        + "/visuals/frame/" + encodeURIComponent(basename);
      image.alt = "Lecture frame " + (position + 1) + ", unverified visual evidence";
      image.loading = "lazy";
      card.append(image);
    }
    if (item.ocr?.text) {
      const detail = node("details", "visual-text");
      const label = item.category === "code_candidate" ? "On-screen code (OCR: verify before use)"
        : "Visible text (OCR: unverified)";
      detail.append(node("summary", "", label));
      detail.append(node("pre", "visual-ocr", item.ocr.text));
      const conf = item.ocr.confidence;
      if (conf !== null && conf !== undefined)
        detail.append(node("small", "muted", "Tesseract average retained-word confidence: " + conf));
      card.append(detail);
    }
    if (item.vision_description) {
      card.append(node("h4", "", "Local model description · unverified"));
      card.append(node("p", "visual-description", item.vision_description));
    }
    target.append(card);
  }
  if (data.warnings?.length) {
    const list = node("ul", "visual-warnings");
    for (const warning of data.warnings) list.append(node("li", "", String(warning)));
    target.append(list);
  }
}
async function fetchVisuals() {
  if (!lesson) return;
  const current = lesson.id;
  const response = await fetch("/api/v1/lessons/" + encodeURIComponent(current) + "/visuals", {cache: "no-store"});
  const data = await response.json();
  if (!lesson || lesson.id !== current) return;
  if (!response.ok) throw new Error(data.detail || "Unable to read visual analysis.");
  if (["running", "queued"].includes(data.status)) {
    analyze.disabled = true;
    message("Visual analysis running. Extracting frames, OCR, and code/diagram candidates...");
    if (interval === null) interval = setInterval(() => fetchVisuals().catch(showError), 2000);
    return;
  }
  clearPoll();
  analyze.disabled = !lesson.media_path;
  if (data.status === "failed") message("Visual analysis failed: " + (data.error || "Unknown error"));
  else if (data.status === "not_started") message("Ready to analyze the downloaded lesson video.");
  else message("Visual evidence: " + (data.frames_examined || 0)
               + " frame(s) captured. All OCR and diagram relationships require review.");
  display(data);
}
function showError(error) {
  clearPoll();
  analyze.disabled = !lesson?.media_path;
  message(error?.message || "Visual analysis failed.");
}
window.addEventListener("ci:lesson-opened", (event) => {
  lesson = event.detail.lesson;
  generation += 1;
  clearPoll();
  target.replaceChildren();
  if (!lesson?.media_path) {
    analyze.disabled = true;
    message("This lesson has no archived local video. Acquire an authorized video first.");
    target.append(node("div", "ci-empty", "Transcript-only lessons have no video frames to analyze."));
    return;
  }
  analyze.disabled = false;
  message("Looking for previously extracted visual evidence...");
  fetchVisuals().catch(showError);
});
analyze?.addEventListener("click", async () => {
  if (!lesson?.media_path) return;
  const current = lesson.id;
  analyze.disabled = true;
  message("Submitting local visual analysis...");
  try {
    const response = await fetch("/api/v1/lessons/" + encodeURIComponent(current) + "/visuals", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({max_frames: 36}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not start visual analysis.");
    if (lesson?.id === current) await fetchVisuals();
  } catch (error) {
    if (lesson?.id === current) showError(error);
  }
});

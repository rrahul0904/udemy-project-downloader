import * as StemJournals from '../vendor/stemkit-core/journals.js';
import * as StemIso4 from '../vendor/stemkit-core/iso4.js';

const wiredPanels = new WeakSet();
const ltwaByPanel = new WeakMap();

const STARTER_RULES = `# Editable whole-title rules. These are examples, not a complete authority list.
Journal of Molecular Biology = J. Mol. Biol.
Journal of Chemical Physics = J. Chem. Phys.
Journal of the American Chemical Society = J. Am. Chem. Soc.
Physical Review Letters = Phys. Rev. Lett.`;

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[char]));
}

function value(panel, id, fallback = '') {
  const raw = panel.querySelector(`#${CSS.escape(id)}`)?.value;
  return raw == null || raw === '' ? fallback : raw;
}

function selectField(id, label, options) {
  return `<label class="field"><span>${esc(label)}</span><select id="${id}">${options.map(([v, text]) => `<option value="${esc(v)}">${esc(text)}</option>`).join('')}</select></label>`;
}

function field(id, label, defaultValue = '') {
  return `<label class="field"><span>${esc(label)}</span><input id="${id}" type="text" value="${esc(defaultValue)}" /></label>`;
}

function textareaField(id, label, defaultValue = '') {
  return `<label class="field"><span>${esc(label)}</span><textarea id="${id}">${esc(defaultValue)}</textarea></label>`;
}

function restoreExtendedState(panel) {
  let state = {};
  try {
    state = JSON.parse(sessionStorage.getItem('study-lab:journal') || '{}');
  } catch (_) {}
  for (const [id, saved] of Object.entries(state)) {
    const control = panel.querySelector(`#${CSS.escape(id)}`);
    if (!control || control.type === 'file') continue;
    control.value = saved;
  }
}

function saveExtendedState(panel) {
  let state = {};
  try {
    state = JSON.parse(sessionStorage.getItem('study-lab:journal') || '{}');
  } catch (_) {}
  panel.querySelectorAll('#stemkit-journal-config input,#stemkit-journal-config textarea,#stemkit-journal-config select').forEach(control => {
    if (!control.id || control.type === 'file') return;
    state[control.id] = control.value;
  });
  sessionStorage.setItem('study-lab:journal', JSON.stringify(state));
}

function renderWholeTitle(panel, title) {
  const custom = StemJournals.parseCustomRules(value(panel, 'journal-custom-rules', STARTER_RULES));
  const engine = StemJournals.buildEngine([], custom);
  const abbreviation = StemJournals.abbreviate(title, engine.lookup);
  const processed = StemJournals.processText(title, engine);

  const lines = [
    abbreviation || processed.text,
    '',
    `Recognized exact/custom title: ${abbreviation !== null ? 'yes' : 'no'}`,
    `Rules indexed: ${engine.entryCount}`,
  ];
  if (abbreviation === null) {
    lines.push('No exact whole-title rule matched. Add a rule below or use ISO-4 mode with a licensed/user-provided LTWA file.');
  }
  if (processed.unknown.length) lines.push(`Journal-like unknowns: ${processed.unknown.join(' | ')}`);
  return lines.join('\n');
}

function renderIso4(panel, title) {
  const loaded = ltwaByPanel.get(panel);
  if (!loaded?.engine) {
    throw new Error('ISO-4 mode requires an LTWA CSV/TSV file that you are licensed or otherwise permitted to use. Load it locally first.');
  }
  const result = StemIso4.abbreviateTitle(title, loaded.engine);
  const lines = [
    result.abbreviation,
    '',
    `LTWA entries indexed: ${loaded.stats.indexed}`,
    `Rows parsed: ${loaded.stats.parsed}; skipped: ${loaded.stats.skipped}`,
    `Changed: ${result.changed ? 'yes' : 'no'}`,
  ];
  if (result.unmatched.length) lines.push(`Unmatched words (review manually): ${[...new Set(result.unmatched)].join(', ')}`);
  return lines.join('\n');
}

export function runJournalAbbreviation(panel) {
  const title = panel.querySelector('#journal-title')?.value.trim();
  if (!title) throw new Error('Enter a journal title.');
  saveExtendedState(panel);

  const mode = value(panel, 'journal-mode', 'rules');
  const output = mode === 'iso4' ? renderIso4(panel, title) : renderWholeTitle(panel, title);
  panel.querySelector('#result').textContent = output;
  return output;
}

function updateMode(panel) {
  const mode = value(panel, 'journal-mode', 'rules');
  const rules = panel.querySelector('#journal-rules-section');
  const iso = panel.querySelector('#journal-iso4-section');
  if (rules) rules.hidden = mode !== 'rules';
  if (iso) iso.hidden = mode !== 'iso4';
  const status = panel.querySelector('#journal-mode-status');
  if (status) {
    status.textContent = mode === 'iso4'
      ? 'ISO-4 uses only the LTWA file you explicitly load in this browser. No LTWA dataset is bundled or uploaded.'
      : 'Whole-title mode uses editable exact rules through STEMKit’s journal normalization/matching engine.';
  }
}

function installRunInterceptor(panel) {
  if (wiredPanels.has(panel)) return;
  wiredPanels.add(panel);
  panel.addEventListener('click', event => {
    const button = event.target.closest('[data-action="run"]');
    if (!button || !panel.querySelector('#stemkit-journal-config')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      runJournalAbbreviation(panel);
    } catch (error) {
      panel.querySelector('#result').textContent = `Error: ${error.message}`;
    }
  }, true);
}

export function enhanceJournalPanel(panel) {
  if (!panel || panel.querySelector('#stemkit-journal-config')) return false;
  if (document.querySelector('#workspace-title')?.textContent !== 'Journal Abbreviator') return false;
  const form = panel.querySelector('.tool-form');
  if (!form || !panel.querySelector('#journal-title') || !panel.querySelector('#result')) return false;

  const root = document.createElement('section');
  root.id = 'stemkit-journal-config';
  root.className = 'journal-config';
  root.innerHTML = `
    <p class="status"><strong>STEMKit journal core.</strong> Use editable whole-title rules, or load an LTWA export you are permitted to use for ISO-4 word-level abbreviation.</p>
    <div class="form-grid">
      ${selectField('journal-mode', 'Abbreviation mode', [['rules', 'Whole-title rules'], ['iso4', 'ISO-4 with local LTWA file']])}
      ${field('journal-languages', 'LTWA language filter (optional)', 'en')}
    </div>
    <p id="journal-mode-status" class="status"></p>
    <div id="journal-rules-section">
      ${textareaField('journal-custom-rules', 'Editable title rules (Full title = Abbreviation)', STARTER_RULES)}
    </div>
    <div id="journal-iso4-section" hidden>
      <label class="field"><span>LTWA CSV/TSV file (local only)</span><input id="journal-ltwa-file" type="file" accept=".csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain" /></label>
      <p id="journal-ltwa-status" class="status">No LTWA file loaded. This project intentionally does not bundle the ISSN LTWA dataset because its distribution terms are separate from STEMKit’s MIT license.</p>
    </div>
  `;

  const actions = form.querySelector('.actions');
  if (actions) form.insertBefore(root, actions);
  else form.append(root);

  restoreExtendedState(panel);
  updateMode(panel);
  panel.querySelector('#journal-mode')?.addEventListener('change', () => {
    updateMode(panel);
    saveExtendedState(panel);
  });
  panel.querySelector('#journal-languages')?.addEventListener('input', () => saveExtendedState(panel));
  panel.querySelector('#journal-custom-rules')?.addEventListener('input', () => saveExtendedState(panel));

  panel.querySelector('#journal-ltwa-file')?.addEventListener('change', event => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const languages = value(panel, 'journal-languages', '')
          .split(/[,;\s]+/).map(item => item.trim()).filter(Boolean);
        const loaded = StemIso4.loadIso4(String(reader.result || ''), languages.length ? { languages } : {});
        ltwaByPanel.set(panel, loaded);
        panel.querySelector('#journal-ltwa-status').textContent = `Loaded locally: ${file.name} · ${loaded.stats.parsed} rows parsed · ${loaded.stats.indexed} indexed.`;
      } catch (error) {
        panel.querySelector('#journal-ltwa-status').textContent = `Could not parse LTWA file: ${error.message}`;
      }
    };
    reader.readAsText(file);
  });

  installRunInterceptor(panel);
  const description = document.querySelector('#workspace-description');
  if (description) description.textContent = 'Abbreviate journal titles with STEMKit whole-title matching or ISO-4 rules driven by an LTWA file you explicitly load locally.';
  return true;
}

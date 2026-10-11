import * as StemPlumed from '../vendor/stemkit-core/plumed.js';

const wiredPanels = new WeakSet();

export const PLUMED_CATALOGUE = Object.freeze({
  DISTANCE: {
    cat: 'geometry',
    fields: [
      { k: 'ATOMS', type: 'atoms', def: '1,2', required: true },
      { k: 'COMPONENTS', type: 'flag', def: false },
      { k: 'NOPBC', type: 'flag', def: false },
    ],
  },
  TORSION: {
    cat: 'angles',
    fields: [
      { k: 'ATOMS', type: 'atoms', def: '1,2,3,4', required: true },
    ],
  },
  COORDINATION: {
    cat: 'contacts',
    fields: [
      { k: 'GROUPA', type: 'atoms', def: '1-10', required: true },
      { k: 'GROUPB', type: 'atoms', def: '11-20' },
      { k: 'SWITCH', type: 'text', def: '' },
      { k: 'NL_CUTOFF', type: 'num', def: '' },
      { k: 'NL_STRIDE', type: 'num', def: '' },
    ],
  },
  DIHEDRAL_CORRELATION: {
    cat: 'angles',
    minVersion: '2.10',
    fallback: 'DIHCOR',
    fields: [
      { k: 'ATOMS', type: 'atoms', def: '1,2,3,4,5,6,7,8', required: true },
    ],
  },
});

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[char]));
}

function value(panel, id, fallback = '') {
  const raw = panel.querySelector(`#${CSS.escape(id)}`)?.value;
  return raw == null || raw === '' ? fallback : raw;
}

function checked(panel, id) {
  return Boolean(panel.querySelector(`#${CSS.escape(id)}`)?.checked);
}

function numberValue(panel, id, fallback = null) {
  const raw = value(panel, id, '');
  if (raw === '') return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function field(id, label, defaultValue = '', type = 'text', step = '') {
  return `<label class="field"><span>${esc(label)}</span><input id="${id}" type="${type}" value="${esc(defaultValue)}"${step ? ` step="${esc(step)}"` : ''} /></label>`;
}

function selectField(id, label, options) {
  return `<label class="field"><span>${esc(label)}</span><select id="${id}">${options.map(([v, text]) => `<option value="${esc(v)}">${esc(text)}</option>`).join('')}</select></label>`;
}

function checkboxField(id, label, checkedByDefault = false) {
  return `<label class="field"><span>${esc(label)}</span><input id="${id}" type="checkbox"${checkedByDefault ? ' checked' : ''} /></label>`;
}

function restoreExtendedState(panel) {
  let state = {};
  try {
    state = JSON.parse(sessionStorage.getItem('study-lab:workflow') || '{}');
  } catch (_) {}

  for (const [id, saved] of Object.entries(state)) {
    const control = panel.querySelector(`#${CSS.escape(id)}`);
    if (!control) continue;
    if (control.type === 'checkbox') control.checked = Boolean(saved);
    else control.value = saved;
  }
}

function buildCv(panel, slot, warnings) {
  const type = value(panel, `plumed-cv${slot}-type`, '');
  if (!type) return null;

  const label = value(panel, `plumed-cv${slot}-label`, `cv${slot}`).trim() || `cv${slot}`;
  const atomText = value(panel, `plumed-cv${slot}-atoms`, '').trim();
  const values = {};

  if (type === 'DISTANCE' || type === 'TORSION' || type === 'DIHEDRAL_CORRELATION') {
    values.ATOMS = atomText;
  } else if (type === 'COORDINATION') {
    values.GROUPA = atomText;
    values.GROUPB = value(panel, `plumed-cv${slot}-groupb`, '').trim();
    const r0 = numberValue(panel, `plumed-cv${slot}-r0`, null);
    const dmax = numberValue(panel, `plumed-cv${slot}-dmax`, null);
    if (Number.isFinite(r0) && r0 > 0) {
      const sw = StemPlumed.buildSwitchBlock({ r0, dmax });
      values.SWITCH = sw.block;
      warnings.push(...sw.warnings);
    }
  }

  return {
    type,
    label,
    values,
    bias: checked(panel, `plumed-cv${slot}-bias`),
  };
}

function biasParams(panel, method) {
  if (method === 'wt_metad' || method === 'metad') {
    return {
      pace: numberValue(panel, 'plumed-metad-pace', 500),
      height: numberValue(panel, 'plumed-metad-height', 1.2),
      sigma: value(panel, 'plumed-metad-sigma', '').trim(),
      biasfactor: numberValue(panel, 'plumed-metad-biasfactor', 10),
      temp: numberValue(panel, 'temperature', 300),
      gridMin: value(panel, 'plumed-metad-grid-min', '').trim(),
      gridMax: value(panel, 'plumed-metad-grid-max', '').trim(),
      gridBin: value(panel, 'plumed-metad-grid-bin', '').trim(),
      file: value(panel, 'plumed-metad-hills-file', 'HILLS').trim() || 'HILLS',
    };
  }
  if (method === 'opes') {
    return {
      pace: numberValue(panel, 'plumed-opes-pace', 500),
      barrier: numberValue(panel, 'plumed-opes-barrier', 30),
      sigma: value(panel, 'plumed-opes-sigma', 'ADAPTIVE').trim() || 'ADAPTIVE',
      temp: numberValue(panel, 'temperature', 300),
    };
  }
  if (method === 'restraint' || method === 'upper' || method === 'lower') {
    return {
      at: value(panel, 'plumed-static-at', '').trim(),
      kappa: numberValue(panel, 'plumed-static-kappa', method === 'restraint' ? 100 : 150),
    };
  }
  if (method === 'moving') {
    return {
      at0: value(panel, 'plumed-moving-at0', '').trim(),
      at1: value(panel, 'plumed-moving-at1', '').trim(),
      step0: numberValue(panel, 'plumed-moving-step0', 0),
      step1: numberValue(panel, 'plumed-moving-step1', 100000),
      kappa: numberValue(panel, 'plumed-moving-kappa', 100),
    };
  }
  return {};
}

export function buildPlumedConfig(panel) {
  const warnings = [];
  const cvs = [buildCv(panel, 1, warnings), buildCv(panel, 2, warnings)].filter(Boolean);
  const biasMethod = value(panel, 'plumed-bias', 'none');
  const structure = value(panel, 'plumed-structure', '').trim();
  const moltype = value(panel, 'plumed-moltype', '').trim();

  return {
    warnings,
    config: {
      cvs,
      biasMethod,
      biasParams: biasParams(panel, biasMethod),
      version: value(panel, 'plumed-version', StemPlumed.DEFAULT_PLUMED_VERSION),
      catalogue: PLUMED_CATALOGUE,
      units: {
        length: value(panel, 'plumed-unit-length', 'nm').trim(),
        energy: value(panel, 'plumed-unit-energy', 'kj/mol').trim(),
        time: value(panel, 'plumed-unit-time', 'ps').trim(),
      },
      molinfo: structure ? { structure, moltype } : null,
      printStride: numberValue(panel, 'plumed-print-stride', 500),
      printFile: value(panel, 'plumed-print-file', 'COLVAR').trim() || 'COLVAR',
    },
  };
}

export function renderPlumedInput(panel) {
  const built = buildPlumedConfig(panel);
  if (!built.config.cvs.length) throw new Error('Add at least one PLUMED collective variable.');

  const generated = StemPlumed.generatePlumedInput(built.config);
  const warnings = [...built.warnings, ...generated.warnings];
  const notes = [
    '# Course Intelligence Study Lab · STEMKit PLUMED adapter',
    `# Target PLUMED version: ${built.config.version}`,
  ];
  for (const warning of warnings) notes.push(`# STEMKit WARNING: ${warning}`);

  const result = panel.querySelector('#result');
  result.textContent = `${notes.join('\n')}\n\n${generated.input}`;

  const summary = panel.querySelector('#plumed-summary');
  if (summary) {
    summary.textContent = `PLUMED input ready · ${generated.cvLines.length} CV${generated.cvLines.length === 1 ? '' : 's'} · ${warnings.length} warning${warnings.length === 1 ? '' : 's'}.`;
  }
  return { ...generated, warnings };
}

function updateBiasFields(panel) {
  const method = value(panel, 'plumed-bias', 'none');
  panel.querySelectorAll('[data-plumed-bias]').forEach(section => {
    const allowed = section.dataset.plumedBias.split(',');
    section.hidden = !allowed.includes(method);
  });
}

function updateMode(panel) {
  const engine = value(panel, 'engine', 'gromacs');
  const root = panel.querySelector('#stemkit-plumed-config');
  if (!root) return;
  root.hidden = engine !== 'plumed';
  if (engine === 'plumed') {
    const description = document.querySelector('#workspace-description');
    if (description) description.textContent = 'Generate version-aware PLUMED 2.9/2.10 input with validated collective variables, bias settings, output configuration, and STEMKit warnings.';
  }
}

function installRunInterceptor(panel) {
  if (wiredPanels.has(panel)) return;
  wiredPanels.add(panel);
  panel.addEventListener('click', event => {
    const button = event.target.closest('[data-action="run"]');
    if (!button || !panel.querySelector('#stemkit-plumed-config')) return;
    if (value(panel, 'engine', 'gromacs') !== 'plumed') return;

    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      renderPlumedInput(panel);
    } catch (error) {
      const result = panel.querySelector('#result');
      if (result) result.textContent = `Error: ${error.message}`;
    }
  }, true);
}

function cvSection(slot, defaultLabel, defaultAtoms, defaultBias) {
  const typeOptions = slot === 1
    ? [['DISTANCE', 'Distance'], ['TORSION', 'Torsion'], ['COORDINATION', 'Coordination'], ['DIHEDRAL_CORRELATION', 'Dihedral correlation']]
    : [['', 'Disabled'], ['DISTANCE', 'Distance'], ['TORSION', 'Torsion'], ['COORDINATION', 'Coordination'], ['DIHEDRAL_CORRELATION', 'Dihedral correlation']];
  return `
    <section class="plumed-cv" data-plumed-cv-slot="${slot}">
      <div class="form-grid three">
        ${selectField(`plumed-cv${slot}-type`, `CV ${slot} type`, typeOptions)}
        ${field(`plumed-cv${slot}-label`, `CV ${slot} label`, defaultLabel)}
        ${checkboxField(`plumed-cv${slot}-bias`, `Bias CV ${slot}`, defaultBias)}
      </div>
      <div class="form-grid three">
        ${field(`plumed-cv${slot}-atoms`, 'Atoms / GROUPA', defaultAtoms)}
        ${field(`plumed-cv${slot}-groupb`, 'GROUPB (coordination)', slot === 1 ? '11-20' : '')}
        ${field(`plumed-cv${slot}-r0`, 'R₀ (coordination)', slot === 1 ? '0.3' : '', 'number', 'any')}
      </div>
      <div class="form-grid three">
        ${field(`plumed-cv${slot}-dmax`, 'D_MAX (coordination)', slot === 1 ? '1.0' : '', 'number', 'any')}
        <div class="field"><span>Version behavior</span><small>Dihedral correlation emits DIHEDRAL_CORRELATION on 2.10 and falls back to DIHCOR on 2.9.</small></div>
        <div class="field"><span>Switching function</span><small>Coordination uses STEMKit's validated rational switch builder.</small></div>
      </div>
    </section>`;
}

export function enhancePlumedPanel(panel) {
  if (!panel || panel.querySelector('#stemkit-plumed-config')) return false;
  const engine = panel.querySelector('#engine');
  const form = panel.querySelector('.tool-form');
  if (!engine || !form || !panel.querySelector('#result')) return false;

  const root = document.createElement('section');
  root.id = 'stemkit-plumed-config';
  root.className = 'plumed-config';
  root.hidden = true;
  root.innerHTML = `
    <p class="status"><strong>STEMKit PLUMED core.</strong> Build CVs and enhanced-sampling bias input locally. Warnings are preserved as comments instead of silently changing the scientific request.</p>
    <div class="form-grid three">
      ${selectField('plumed-version', 'PLUMED version', StemPlumed.PLUMED_VERSIONS.map(v => [v, v]))}
      ${field('plumed-structure', 'MOLINFO structure', 'ref.pdb')}
      ${field('plumed-moltype', 'Molecule type', 'protein')}
    </div>
    <div class="form-grid three">
      ${field('plumed-unit-length', 'Length unit', 'nm')}
      ${field('plumed-unit-energy', 'Energy unit', 'kj/mol')}
      ${field('plumed-unit-time', 'Time unit', 'ps')}
    </div>
    ${cvSection(1, 'd1', '1,2', true)}
    ${cvSection(2, 'phi', '5,7,9,15', false)}
    <div class="form-grid three">
      ${selectField('plumed-bias', 'Bias method', [
        ['none', 'None'], ['wt_metad', 'Well-tempered metadynamics'], ['metad', 'Metadynamics'],
        ['opes', 'OPES'], ['restraint', 'Restraint'], ['moving', 'Moving restraint'],
        ['upper', 'Upper wall'], ['lower', 'Lower wall']
      ])}
      ${field('plumed-print-stride', 'PRINT stride', '500', 'number', '1')}
      ${field('plumed-print-file', 'PRINT file', 'COLVAR')}
    </div>
    <div data-plumed-bias="wt_metad,metad" hidden>
      <div class="form-grid three">
        ${field('plumed-metad-pace', 'PACE', '500', 'number', '1')}
        ${field('plumed-metad-height', 'HEIGHT', '1.2', 'number', 'any')}
        ${field('plumed-metad-sigma', 'SIGMA', '0.05')}
      </div>
      <div class="form-grid three">
        ${field('plumed-metad-biasfactor', 'BIASFACTOR (WT only)', '10', 'number', 'any')}
        ${field('plumed-metad-grid-min', 'GRID_MIN', '0')}
        ${field('plumed-metad-grid-max', 'GRID_MAX', '2')}
      </div>
      <div class="form-grid three">
        ${field('plumed-metad-grid-bin', 'GRID_BIN', '200')}
        ${field('plumed-metad-hills-file', 'HILLS file', 'HILLS')}
      </div>
    </div>
    <div data-plumed-bias="opes" hidden>
      <div class="form-grid three">
        ${field('plumed-opes-pace', 'PACE', '500', 'number', '1')}
        ${field('plumed-opes-barrier', 'BARRIER', '30', 'number', 'any')}
        ${field('plumed-opes-sigma', 'SIGMA', 'ADAPTIVE')}
      </div>
    </div>
    <div data-plumed-bias="restraint,upper,lower" hidden>
      <div class="form-grid three">
        ${field('plumed-static-at', 'AT', '1.0')}
        ${field('plumed-static-kappa', 'KAPPA', '100', 'number', 'any')}
      </div>
    </div>
    <div data-plumed-bias="moving" hidden>
      <div class="form-grid three">
        ${field('plumed-moving-at0', 'AT0', '1.0')}
        ${field('plumed-moving-at1', 'AT1', '2.0')}
        ${field('plumed-moving-kappa', 'KAPPA', '100', 'number', 'any')}
      </div>
      <div class="form-grid three">
        ${field('plumed-moving-step0', 'STEP0', '0', 'number', '1')}
        ${field('plumed-moving-step1', 'STEP1', '100000', 'number', '1')}
      </div>
    </div>
    <p id="plumed-summary" class="status">Choose PLUMED mode, configure CVs, then generate the workflow.</p>
  `;

  const actions = form.querySelector('.actions');
  if (actions) form.insertBefore(root, actions);
  else form.append(root);

  restoreExtendedState(panel);
  updateBiasFields(panel);
  updateMode(panel);

  engine.addEventListener('change', () => updateMode(panel));
  panel.querySelector('#plumed-bias')?.addEventListener('change', () => updateBiasFields(panel));
  installRunInterceptor(panel);
  return true;
}

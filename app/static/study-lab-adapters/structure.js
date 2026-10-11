import * as StemStructure from '../vendor/stemkit-core/structure.js';
import * as StemSelection from '../vendor/stemkit-core/selection.js';

const wiredPanels = new WeakSet();

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

function numberValue(panel, id, fallback = 0) {
  const parsed = Number(value(panel, id, String(fallback)));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function field(id, label, defaultValue = '', type = 'text', step = '') {
  return `<label class="field"><span>${esc(label)}</span><input id="${id}" type="${type}" value="${esc(defaultValue)}"${step ? ` step="${esc(step)}"` : ''} /></label>`;
}

function selectField(id, label, options) {
  return `<label class="field"><span>${esc(label)}</span><select id="${id}">${options.map(([v, text]) => `<option value="${esc(v)}">${esc(text)}</option>`).join('')}</select></label>`;
}

function checkboxField(id, label, defaultChecked = false) {
  return `<label class="field"><span>${esc(label)}</span><input id="${id}" type="checkbox"${defaultChecked ? ' checked' : ''} /></label>`;
}

function restoreExtendedState(panel, tool) {
  let state = {};
  try {
    state = JSON.parse(sessionStorage.getItem(`study-lab:${tool}`) || '{}');
  } catch (_) {}
  for (const [id, saved] of Object.entries(state)) {
    const control = panel.querySelector(`#${CSS.escape(id)}`);
    if (!control) continue;
    if (control.type === 'checkbox') control.checked = Boolean(saved);
    else control.value = saved;
  }
}

function parseCurrent(panel) {
  const source = panel.querySelector('#input-data')?.value || '';
  const format = value(panel, 'structure-format', 'pdb');
  const parsed = StemStructure.parseStructure(source, format);
  if (!parsed || !parsed.atoms?.length) {
    throw new Error(`No valid ${format.toUpperCase()} atoms were parsed.`);
  }
  return parsed;
}

function selectedAtoms(panel, parsed) {
  const query = value(panel, 'structure-selection', '').trim();
  if (!query) return { atoms: parsed.atoms, errors: [], count: parsed.atoms.length };
  return StemSelection.selectAtoms(parsed.atoms, query, {
    unit: value(panel, 'structure-selection-unit', parsed.unit),
    coordinateUnit: parsed.unit,
    byres: checked(panel, 'structure-byres'),
  });
}

function fmt(value) {
  return Number.isFinite(value) ? Number(value).toFixed(5).replace(/\.?0+$/, '') : 'n/a';
}

function summaryText(parsed, selection) {
  const stats = StemStructure.structureStats(selection.atoms);
  const selectionStats = StemSelection.selectionSummary(selection.atoms);
  const b = stats.boundingBox;
  const lines = [
    `Format: ${parsed.format.toUpperCase()} · coordinate unit: ${parsed.unit}`,
    `Selected atoms: ${selection.count} / ${parsed.atoms.length}`,
    `Residues: ${stats.nResidues} · chains: ${stats.nChains}`,
    `Molecular mass: ${fmt(stats.totalMass)} Da`,
    `Radius of gyration: ${fmt(stats.radiusOfGyration)} ${parsed.unit}`,
    `Geometric centre: ${fmt(stats.geometricCentre.x)}, ${fmt(stats.geometricCentre.y)}, ${fmt(stats.geometricCentre.z)} ${parsed.unit}`,
    `Centre of mass: ${fmt(stats.centreOfMass.x)}, ${fmt(stats.centreOfMass.y)}, ${fmt(stats.centreOfMass.z)} ${parsed.unit}`,
    `Bounds X: ${fmt(b.minX)} → ${fmt(b.maxX)}; Y: ${fmt(b.minY)} → ${fmt(b.maxY)}; Z: ${fmt(b.minZ)} → ${fmt(b.maxZ)} ${parsed.unit}`,
    `Elements: ${Object.entries(selectionStats.elements).map(([key, count]) => `${key}:${count}`).join(', ') || 'n/a'}`,
  ];
  if (selection.errors.length) lines.push(`Selection warnings: ${selection.errors.join(' | ')}`);
  if (parsed.unknownElements?.length) lines.push(`Unknown elements: ${parsed.unknownElements.join(', ')}`);
  return lines.join('\n');
}

function renderInspector(panel) {
  const parsed = parseCurrent(panel);
  const selection = selectedAtoms(panel, parsed);
  const outputFormat = value(panel, 'structure-output-format', parsed.format);
  let text = summaryText(parsed, selection);

  if (checked(panel, 'structure-include-output')) {
    const converted = StemStructure.formatStructure(selection.atoms, outputFormat, {
      sourceUnit: parsed.unit,
      box: parsed.box,
      boxVectors: parsed.boxVectors,
      title: parsed.title || parsed.comment || 'Converted by Course Intelligence Study Lab',
    });
    text += `\n\n# Converted ${outputFormat.toUpperCase()}\n${converted}`;
  }

  panel.querySelector('#result').textContent = text;
  const status = panel.querySelector('#structure-summary');
  if (status) status.textContent = `Parsed ${parsed.atoms.length} atom${parsed.atoms.length === 1 ? '' : 's'}; selection contains ${selection.count}.`;
}

function transformAll(panel, parsed) {
  let atoms = parsed.atoms;
  const center = value(panel, 'structure-center', 'none');
  if (center === 'geometric' || center === 'mass') atoms = StemStructure.centreAtoms(atoms, center);

  const rx = numberValue(panel, 'structure-rx', 0);
  const ry = numberValue(panel, 'structure-ry', 0);
  const rz = numberValue(panel, 'structure-rz', 0);
  if (rx || ry || rz) {
    const pivot = center === 'none' ? StemStructure.geometricCentre(atoms) : { x: 0, y: 0, z: 0 };
    atoms = StemStructure.rotateAtoms(atoms, rx, ry, rz, pivot);
  }

  const scale = numberValue(panel, 'structure-scale', 1);
  if (!Number.isFinite(scale) || scale <= 0) throw new Error('Scale must be a positive number.');
  if (scale !== 1) atoms = StemStructure.scaleAtoms(atoms, scale);

  const dx = numberValue(panel, 'dx', 0);
  const dy = numberValue(panel, 'dy', 0);
  const dz = numberValue(panel, 'dz', 0);
  if (dx || dy || dz) atoms = StemStructure.translateAtoms(atoms, dx, dy, dz);
  return atoms;
}

function renderManipulator(panel) {
  const parsed = parseCurrent(panel);
  const atoms = transformAll(panel, parsed);
  const outputFormat = value(panel, 'structure-output-format', parsed.format);
  const output = StemStructure.formatStructure(atoms, outputFormat, {
    sourceUnit: parsed.unit,
    box: parsed.box,
    boxVectors: parsed.boxVectors,
    title: parsed.title || parsed.comment || 'Transformed by Course Intelligence Study Lab',
  });
  const stats = StemStructure.structureStats(atoms);
  panel.querySelector('#result').textContent = [
    `# STEMKit structure transform: ${parsed.format.toUpperCase()} → ${outputFormat.toUpperCase()}`,
    `# atoms=${atoms.length}; radius_of_gyration=${fmt(stats.radiusOfGyration)} ${parsed.unit}`,
    output,
  ].join('\n');
  const status = panel.querySelector('#structure-summary');
  if (status) status.textContent = `Transformed ${atoms.length} atom${atoms.length === 1 ? '' : 's'} and serialized as ${outputFormat.toUpperCase()}.`;
}

function installRunInterceptor(panel, mode) {
  if (wiredPanels.has(panel)) return;
  wiredPanels.add(panel);
  panel.addEventListener('click', event => {
    const button = event.target.closest('[data-action="run"]');
    if (!button || !panel.querySelector('#stemkit-structure-config')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      if (mode === 'manipulator') renderManipulator(panel);
      else renderInspector(panel);
    } catch (error) {
      const result = panel.querySelector('#result');
      if (result) result.textContent = `Error: ${error.message}`;
    }
  }, true);
}

export function enhanceStructurePanel(panel) {
  if (!panel || panel.querySelector('#stemkit-structure-config')) return false;
  const title = document.querySelector('#workspace-title')?.textContent || '';
  const mode = title === 'Coordinate Manipulator' ? 'manipulator' : title === 'Structure Inspector' ? 'inspector' : '';
  if (!mode || !panel.querySelector('#input-data') || !panel.querySelector('#result')) return false;

  const root = document.createElement('section');
  root.id = 'stemkit-structure-config';
  root.className = 'structure-config';
  root.innerHTML = `
    <p class="status"><strong>STEMKit structure core.</strong> PDB, GRO, and XYZ parsing uses the vendored format-aware engine. Selection expressions support attributes, named groups, ranges, negation, union, and spatial <code>within:</code> queries.</p>
    <div class="form-grid three">
      ${selectField('structure-format', 'Input format', [['pdb', 'PDB'], ['gro', 'GROMACS GRO'], ['xyz', 'XYZ']])}
      ${selectField('structure-output-format', 'Output format', [['pdb', 'PDB'], ['gro', 'GROMACS GRO'], ['xyz', 'XYZ']])}
      ${selectField('structure-selection-unit', 'Selection distance unit', [['A', 'Ångström'], ['nm', 'Nanometer']])}
    </div>
    ${mode === 'inspector' ? `
      <div class="form-grid three">
        ${field('structure-selection', 'Selection query', 'protein:')}
        ${checkboxField('structure-byres', 'Expand selection by residue', false)}
        ${checkboxField('structure-include-output', 'Include converted selected coordinates', false)}
      </div>
      <p class="status">Examples: <code>protein:</code>, <code>chain:A resi:10-25</code>, <code>elem:C</code>, <code>within:5,chain:A</code>, <code>not:solvent:</code>.</p>
    ` : `
      <div class="form-grid three">
        ${selectField('structure-center', 'Center first', [['none', 'No centering'], ['geometric', 'Geometric center'], ['mass', 'Center of mass']])}
        ${field('structure-scale', 'Scale factor', '1', 'number', 'any')}
        <div class="field"><span>Translation</span><small>Existing ΔX / ΔY / ΔZ fields are applied after centering, rotation, and scaling.</small></div>
      </div>
      <div class="form-grid three">
        ${field('structure-rx', 'Rotate X (degrees)', '0', 'number', 'any')}
        ${field('structure-ry', 'Rotate Y (degrees)', '0', 'number', 'any')}
        ${field('structure-rz', 'Rotate Z (degrees)', '0', 'number', 'any')}
      </div>
    `}
    <p id="structure-summary" class="status">Configure the structure operation, then run the tool.</p>
  `;

  const actions = panel.querySelector('.tool-form .actions');
  if (actions) panel.querySelector('.tool-form').insertBefore(root, actions);
  else panel.querySelector('.tool-form')?.append(root);

  restoreExtendedState(panel, mode === 'manipulator' ? 'coordinates' : 'structure');
  installRunInterceptor(panel, mode);

  const description = document.querySelector('#workspace-description');
  if (description) {
    description.textContent = mode === 'manipulator'
      ? 'Transform and convert PDB/GRO/XYZ coordinates with STEMKit centering, rotation, scaling, translation, and unit-aware serialization.'
      : 'Inspect PDB/GRO/XYZ structures with STEMKit mass/geometry statistics and atom-selection/spatial-query support.';
  }
  return true;
}

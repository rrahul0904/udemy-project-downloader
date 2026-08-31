const panel = document.querySelector('#tool-panel');
const titleEl = document.querySelector('#workspace-title');
const descriptionEl = document.querySelector('#workspace-description');
const workspace = document.querySelector('#workspace');
const searchInput = document.querySelector('#tool-search');
const courseFile = document.querySelector('#course-file');
const courseFileButton = document.querySelector('#load-course-file');
const courseFileStatus = document.querySelector('#course-file-status');

let currentTool = null;
let timerInterval = null;
let timerSeconds = 25 * 60;
let digitizerImage = null;
let digitizerPoints = [];

const toolMeta = {
  statistics: ['Statistics Calculator', 'Compute descriptive statistics from numeric values separated by spaces, commas, tabs, or new lines.'],
  cleaner: ['Data Cleaner', 'Normalize delimited data locally, remove empty rows, and optionally deduplicate records.'],
  outliers: ['Outlier Detector', 'Flag numeric observations with the IQR rule or an absolute z-score threshold.'],
  curve: ['Curve Fitter', 'Fit an ordinary least-squares straight line to x/y observations and inspect R².'],
  errorbars: ['Error-Bar Generator', 'Group observations and calculate mean, sample SD, SEM, and an approximate 95% confidence interval.'],
  plot: ['Plot Builder', 'Render a lightweight local SVG scatter or line plot from x/y pairs.'],
  digitizer: ['Plot Digitizer', 'Map clicks on an uploaded plot image into approximate x/y coordinates using full-image axis bounds.'],
  xvg: ['XVG Visualizer', 'Parse numeric GROMACS XVG rows and plot the first y series against the first x column.'],
  structure: ['Structure Inspector', 'Inspect PDB ATOM/HETATM records, residues, chains, elements, and coordinate bounds.'],
  coordinates: ['Coordinate Manipulator', 'Translate fixed-width PDB x/y/z coordinates without sending the structure to a server.'],
  workflow: ['MD Workflow Generator', 'Create starter GROMACS, LAMMPS, or PLUMED workflow text for adaptation in a real simulation environment.'],
  bibtex: ['BibTeX Sanitizer', 'Normalize common bibliography formatting issues while preserving the entries as editable text.'],
  bibdedupe: ['BibTeX Deduplicator', 'Remove likely duplicate entries by normalized DOI or title.'],
  doi: ['DOI → BibTeX', 'Fetch a BibTeX representation from Crossref when an internet connection is available.'],
  journal: ['Journal Abbreviator', 'Generate a practical abbreviated journal title using common title-word rules.'],
  latextable: ['LaTeX Table Builder', 'Convert comma- or tab-delimited rows into a copyable LaTeX tabular environment.'],
  equation: ['Equation Builder', 'Wrap a LaTeX expression as inline or display math and keep it ready to copy into notes.'],
  units: ['Scientific Converter', 'Convert common scientific length, energy, pressure, and temperature values.'],
  pomodoro: ['Pomodoro Timer', 'Run a local focus timer with configurable focus and break lengths.'],
  decision: ['Decision Matrix', 'Score alternatives from comma-delimited rows of numeric criteria.'],
  kinetics: ['Kinetics Sandbox', 'Explore first-order decay C(t)=C₀e⁻ᵏᵗ and the corresponding half-life.'],
};

const templates = {
  statistics: () => form(`
    ${textarea('input-data', 'Numeric observations', '10, 12, 15, 18, 20\n22 24 25')}
    ${runButton('Calculate statistics')}
    ${output('result')}
  `),
  cleaner: () => form(`
    ${textarea('input-data', 'Delimited rows', 'name,score\nAda, 95\nGrace, 88\nAda, 95\n,')}
    <div class="form-grid">
      ${check('trim-cells', 'Trim cell whitespace', true)}
      ${check('drop-empty', 'Drop empty rows', true)}
      ${check('dedupe', 'Remove duplicate rows', true)}
    </div>
    ${runButton('Clean data')}
    ${output('result')}
  `),
  outliers: () => form(`
    ${textarea('input-data', 'Numeric observations', '10, 11, 11, 12, 12, 13, 14, 55')}
    <div class="form-grid">
      ${select('method', 'Method', [['iqr','IQR (1.5 × IQR)'], ['z','Z-score']])}
      ${input('threshold', 'Z-score threshold', 'number', '3', '0.1')}
    </div>
    ${runButton('Detect outliers')}
    ${output('result')}
  `),
  curve: () => form(`
    ${textarea('input-data', 'x,y pairs', '1,2.2\n2,4.1\n3,5.9\n4,8.2\n5,10.1')}
    ${runButton('Fit line')}
    ${output('result')}
    <div id="plot-output" class="svg-wrap" hidden></div>
  `),
  errorbars: () => form(`
    ${textarea('input-data', 'group,value rows', 'Control,10\nControl,12\nControl,11\nTreatment,15\nTreatment,17\nTreatment,16')}
    ${runButton('Generate summary')}
    <div id="table-output" class="output light">Results will appear here.</div>
  `),
  plot: () => form(`
    ${textarea('input-data', 'x,y pairs', '0,0\n1,1.1\n2,3.8\n3,9.2\n4,15.8')}
    ${select('plot-type', 'Plot style', [['scatter','Scatter'], ['line','Line + points']])}
    ${runButton('Build plot')}
    <div id="plot-output" class="svg-wrap">Plot will appear here.</div>
  `),
  digitizer: () => form(`
    <label class="field"><span>Plot image</span><input id="digitizer-file" type="file" accept="image/*" /></label>
    <div class="form-grid three">
      ${input('xmin', 'X min', 'number', '0', 'any')}
      ${input('xmax', 'X max', 'number', '100', 'any')}
      ${input('ymin', 'Y min', 'number', '0', 'any')}
    </div>
    <div class="form-grid three">
      ${input('ymax', 'Y max', 'number', '100', 'any')}
      <div class="field"><span>Captured points</span><button id="clear-digitizer" class="ghost" type="button">Clear points</button></div>
      <div class="field"><span>Export</span><button id="copy-digitizer" class="ghost" type="button">Copy CSV</button></div>
    </div>
    <div class="digitizer-stage">
      <canvas id="digitizer-canvas" width="900" height="480"></canvas>
      ${output('result', 'Upload an image, set full-image axis bounds, then click data points.')}
    </div>
  `),
  xvg: () => form(`
    ${textarea('input-data', 'XVG text', '# example\n@ title "RMSD"\n0.0 0.10\n1.0 0.12\n2.0 0.18\n3.0 0.15')}
    ${runButton('Parse XVG')}
    ${output('result')}
    <div id="plot-output" class="svg-wrap" hidden></div>
  `),
  structure: () => form(`
    ${textarea('input-data', 'PDB structure', 'ATOM      1  N   ALA A   1      11.104  13.207   9.798  1.00 20.00           N\nATOM      2  CA  ALA A   1      12.560  13.400   9.620  1.00 20.00           C\nATOM      3  C   ALA A   1      13.105  12.157   8.900  1.00 20.00           C')}
    ${runButton('Inspect structure')}
    ${output('result')}
  `),
  coordinates: () => form(`
    ${textarea('input-data', 'PDB structure', 'ATOM      1  N   ALA A   1      11.104  13.207   9.798  1.00 20.00           N\nATOM      2  CA  ALA A   1      12.560  13.400   9.620  1.00 20.00           C')}
    <div class="form-grid three">
      ${input('dx', 'ΔX', 'number', '1', 'any')}
      ${input('dy', 'ΔY', 'number', '0', 'any')}
      ${input('dz', 'ΔZ', 'number', '0', 'any')}
    </div>
    ${runButton('Translate coordinates')}
    ${output('result')}
  `),
  workflow: () => form(`
    <div class="form-grid">
      ${select('engine', 'Engine', [['gromacs','GROMACS'], ['lammps','LAMMPS'], ['plumed','PLUMED']])}
      ${input('project-name', 'Project name', 'text', 'md-course-lab')}
    </div>
    <div class="form-grid three">
      ${input('temperature', 'Temperature (K)', 'number', '300', 'any')}
      ${input('steps', 'Production steps', 'number', '500000', '1')}
      ${input('timestep', 'Timestep', 'number', '0.002', 'any')}
    </div>
    ${runButton('Generate workflow')}
    ${output('result')}
  `),
  bibtex: () => form(`
    ${textarea('input-data', 'BibTeX entries', '@article{example,\n title = {A  Study & Results},\n AUTHOR={Ada Lovelace},\n journal={Journal of Examples},\n year={2026}\n}')}
    ${runButton('Sanitize BibTeX')}
    ${output('result')}
  `),
  bibdedupe: () => form(`
    ${textarea('input-data', 'BibTeX entries', '@article{a, title={Example Study}, doi={10.1000/test}, year={2025}}\n\n@article{b, title={Example Study}, doi={https://doi.org/10.1000/test}, year={2025}}')}
    ${runButton('Deduplicate')}
    ${output('result')}
  `),
  doi: () => form(`
    ${input('doi-value', 'DOI', 'text', '10.1038/s41586-020-2649-2')}
    ${runButton('Fetch BibTeX')}
    ${output('result', 'Crossref will be queried only when you press Fetch BibTeX.')}
  `),
  journal: () => form(`
    ${input('journal-title', 'Journal title', 'text', 'Journal of Molecular Biology')}
    ${runButton('Abbreviate')}
    ${output('result')}
  `),
  latextable: () => form(`
    ${textarea('input-data', 'CSV or tab-delimited table', 'Group,Mean,SD\nControl,12.3,1.2\nTreatment,15.8,1.5')}
    ${runButton('Build LaTeX table')}
    ${output('result')}
  `),
  equation: () => form(`
    ${input('equation-value', 'LaTeX expression', 'text', 'E = mc^2')}
    ${select('equation-mode', 'Mode', [['display','Display math'], ['inline','Inline math']])}
    ${runButton('Build snippet')}
    ${output('result')}
  `),
  units: () => form(`
    <div class="form-grid">
      ${select('unit-category', 'Category', [['length','Length'], ['energy','Energy'], ['pressure','Pressure'], ['temperature','Temperature']])}
      ${input('unit-value', 'Value', 'number', '1', 'any')}
    </div>
    <div class="form-grid">
      <label class="field"><span>From</span><select id="unit-from"></select></label>
      <label class="field"><span>To</span><select id="unit-to"></select></label>
    </div>
    ${runButton('Convert')}
    ${output('result')}
  `),
  pomodoro: () => form(`
    <div id="timer-display" class="timer-display">25:00</div>
    <div class="form-grid">
      ${input('focus-minutes', 'Focus minutes', 'number', '25', '1')}
      ${input('break-minutes', 'Break minutes', 'number', '5', '1')}
    </div>
    <div class="actions">
      <button id="timer-start" type="button">Start</button>
      <button id="timer-pause" class="ghost" type="button">Pause</button>
      <button id="timer-reset" class="ghost" type="button">Reset</button>
      <button id="timer-break" class="ghost" type="button">Start break</button>
    </div>
    <p id="timer-status" class="status">Focus session ready.</p>
  `),
  decision: () => form(`
    ${textarea('input-data', 'option,criterion1,criterion2,...', 'Option A,8,7,9\nOption B,9,5,8\nOption C,6,9,7')}
    ${runButton('Score options')}
    ${output('result')}
  `),
  kinetics: () => form(`
    <div class="form-grid three">
      ${input('c0', 'Initial concentration C₀', 'number', '100', 'any')}
      ${input('rate-k', 'Rate constant k', 'number', '0.15', 'any')}
      ${input('max-time', 'Max time', 'number', '30', 'any')}
    </div>
    ${runButton('Simulate')}
    ${output('result')}
    <div id="plot-output" class="svg-wrap" hidden></div>
  `),
};

function form(inner) { return `<div class="tool-form">${inner}</div>`; }
function textarea(id, label, placeholder='') { return `<label class="field"><span>${escapeHtml(label)}</span><textarea id="${id}" placeholder="${escapeAttr(placeholder)}">${escapeHtml(placeholder)}</textarea></label>`; }
function input(id, label, type='text', value='', step='') { return `<label class="field"><span>${escapeHtml(label)}</span><input id="${id}" type="${type}" value="${escapeAttr(value)}"${step ? ` step="${escapeAttr(step)}"` : ''} /></label>`; }
function select(id, label, options) { return `<label class="field"><span>${escapeHtml(label)}</span><select id="${id}">${options.map(([v,t]) => `<option value="${escapeAttr(v)}">${escapeHtml(t)}</option>`).join('')}</select></label>`; }
function check(id, label, checked=false) { return `<label class="field"><span>${escapeHtml(label)}</span><input id="${id}" type="checkbox"${checked ? ' checked' : ''} /></label>`; }
function runButton(label) { return `<div class="actions"><button data-action="run" type="button">${escapeHtml(label)}</button><button data-action="copy" class="ghost" type="button">Copy result</button></div>`; }
function output(id, initial='Results will appear here.') { return `<pre id="${id}" class="output">${escapeHtml(initial)}</pre>`; }

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
}
function escapeAttr(value) { return escapeHtml(value).replace(/\n/g, '&#10;'); }
function fmt(value, digits=6) {
  if (!Number.isFinite(value)) return 'n/a';
  const abs = Math.abs(value);
  if ((abs > 0 && abs < 1e-4) || abs >= 1e7) return value.toExponential(4);
  return Number(value.toFixed(digits)).toString();
}
function numericValues(text) {
  return String(text).split(/[\s,;]+/).map(Number).filter(Number.isFinite);
}
function pairs(text) {
  return String(text).split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
    const values = line.split(/[\s,;\t]+/).map(Number).filter(Number.isFinite);
    return values.length >= 2 ? [values[0], values[1]] : null;
  }).filter(Boolean);
}
function detectDelimiter(text) {
  const first = String(text).split(/\r?\n/).find((line) => line.trim()) || '';
  if (first.includes('\t')) return '\t';
  if (first.includes(';') && !first.includes(',')) return ';';
  return ',';
}
function rows(text) {
  const delimiter = detectDelimiter(text);
  return String(text).split(/\r?\n/).map((line) => line.split(delimiter));
}
function quantile(sorted, q) {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  return sorted[base + 1] !== undefined ? sorted[base] + rest * (sorted[base + 1] - sorted[base]) : sorted[base];
}
function summary(values) {
  const n = values.length;
  const sorted = [...values].sort((a,b) => a-b);
  const sum = values.reduce((a,b) => a+b, 0);
  const mean = n ? sum / n : NaN;
  const variancePop = n ? values.reduce((acc,v) => acc + (v-mean) ** 2, 0) / n : NaN;
  const varianceSample = n > 1 ? values.reduce((acc,v) => acc + (v-mean) ** 2, 0) / (n-1) : NaN;
  return {
    n, sum, mean,
    median: quantile(sorted, .5), q1: quantile(sorted, .25), q3: quantile(sorted, .75),
    min: sorted[0], max: sorted[n-1], sdPopulation: Math.sqrt(variancePop), sdSample: Math.sqrt(varianceSample)
  };
}
function lineFit(data) {
  const n = data.length;
  const sx = data.reduce((a,[x]) => a+x,0), sy = data.reduce((a,[,y]) => a+y,0);
  const mx = sx/n, my = sy/n;
  const sxx = data.reduce((a,[x]) => a+(x-mx)**2,0);
  const sxy = data.reduce((a,[x,y]) => a+(x-mx)*(y-my),0);
  if (!sxx) throw new Error('X values must not all be identical.');
  const slope = sxy/sxx, intercept = my-slope*mx;
  const ssTot = data.reduce((a,[,y]) => a+(y-my)**2,0);
  const ssRes = data.reduce((a,[x,y]) => a+(y-(slope*x+intercept))**2,0);
  const r2 = ssTot ? 1-ssRes/ssTot : 1;
  return {slope, intercept, r2};
}
function svgPlot(data, {line=false, fit=null, xLabel='x', yLabel='y'}={}) {
  if (!data.length) return '';
  const width=760, height=300, left=56, right=20, top=22, bottom=42;
  let xs=data.map(d=>d[0]), ys=data.map(d=>d[1]);
  let xmin=Math.min(...xs), xmax=Math.max(...xs), ymin=Math.min(...ys), ymax=Math.max(...ys);
  if (xmin===xmax) { xmin-=1; xmax+=1; }
  if (ymin===ymax) { ymin-=1; ymax+=1; }
  const px=x=>left+(x-xmin)/(xmax-xmin)*(width-left-right);
  const py=y=>top+(ymax-y)/(ymax-ymin)*(height-top-bottom);
  const points=data.map(([x,y])=>`${px(x)},${py(y)}`).join(' ');
  const circles=data.map(([x,y])=>`<circle cx="${px(x)}" cy="${py(y)}" r="4" fill="#0b746d"><title>${fmt(x)}, ${fmt(y)}</title></circle>`).join('');
  const dataLine=line ? `<polyline points="${points}" fill="none" stroke="#0b746d" stroke-width="2"/>` : '';
  let fitLine='';
  if (fit) {
    const y1=fit.slope*xmin+fit.intercept, y2=fit.slope*xmax+fit.intercept;
    fitLine=`<line x1="${px(xmin)}" y1="${py(y1)}" x2="${px(xmax)}" y2="${py(y2)}" stroke="#96631a" stroke-width="2" stroke-dasharray="6 5"/>`;
  }
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Plot of ${escapeHtml(yLabel)} versus ${escapeHtml(xLabel)}">
    <line x1="${left}" y1="${height-bottom}" x2="${width-right}" y2="${height-bottom}" stroke="#777"/>
    <line x1="${left}" y1="${top}" x2="${left}" y2="${height-bottom}" stroke="#777"/>
    <text x="${left}" y="${height-12}" font-size="12" fill="#555">${escapeHtml(xLabel)} ${fmt(xmin)}</text>
    <text x="${width-right}" y="${height-12}" text-anchor="end" font-size="12" fill="#555">${fmt(xmax)}</text>
    <text x="8" y="${top+6}" font-size="12" fill="#555">${escapeHtml(yLabel)} ${fmt(ymax)}</text>
    <text x="8" y="${height-bottom}" font-size="12" fill="#555">${fmt(ymin)}</text>
    ${dataLine}${fitLine}${circles}
  </svg>`;
}
function resultText(value) {
  const el = panel.querySelector('#result');
  if (el) el.textContent = value;
}
function requireValues(values, min=1) { if (values.length < min) throw new Error(`Provide at least ${min} valid numeric value${min===1?'':'s'}.`); }
function parseBibEntries(text) {
  const starts=[];
  for (let i=0;i<text.length;i++) if (text[i]==='@') starts.push(i);
  const entries=[];
  for (let s=0;s<starts.length;s++) {
    const start=starts[s], end=starts[s+1] ?? text.length;
    const chunk=text.slice(start,end).trim();
    if (chunk) entries.push(chunk);
  }
  return entries;
}
function bibField(entry, field) {
  const re = new RegExp(`${field}\\s*=\\s*[\\{\"]([^}\"]+)`, 'i');
  const match = entry.match(re);
  return match ? match[1].trim() : '';
}
function normalizeDoi(value) { return String(value).toLowerCase().replace(/^https?:\/\/(dx\.)?doi\.org\//,'').replace(/^doi:\s*/,'').trim(); }
function normalizeTitle(value) { return String(value).toLowerCase().replace(/[{}]/g,'').replace(/[^a-z0-9]+/g,' ').trim(); }
function pdbAtoms(text) {
  return String(text).split(/\r?\n/).filter(line => line.startsWith('ATOM  ') || line.startsWith('HETATM')).map(line => ({
    line,
    atom: line.slice(12,16).trim(), residue: line.slice(17,20).trim(), chain: line.slice(21,22).trim() || '_', resSeq: line.slice(22,26).trim(),
    x: Number(line.slice(30,38)), y: Number(line.slice(38,46)), z: Number(line.slice(46,54)), element: line.slice(76,78).trim() || line.slice(12,14).trim()
  })).filter(a => Number.isFinite(a.x) && Number.isFinite(a.y) && Number.isFinite(a.z));
}

function openTool(tool) {
  if (!templates[tool]) return;
  stopTimer();
  currentTool = tool;
  const [name, description] = toolMeta[tool];
  titleEl.textContent = name;
  descriptionEl.textContent = description;
  panel.innerHTML = templates[tool]();
  restoreToolState(tool);
  setupSpecialTool(tool);
  workspace.scrollIntoView({behavior:'smooth', block:'start'});
  sessionStorage.setItem('study-lab:active-tool', tool);
}

function setupSpecialTool(tool) {
  if (tool === 'units') setupUnitSelects();
  if (tool === 'digitizer') setupDigitizer();
  if (tool === 'pomodoro') setupTimer();
}

function saveToolState() {
  if (!currentTool) return;
  const state={};
  panel.querySelectorAll('input,textarea,select').forEach(el => {
    if (!el.id || el.type === 'file') return;
    state[el.id] = el.type === 'checkbox' ? el.checked : el.value;
  });
  sessionStorage.setItem(`study-lab:${currentTool}`, JSON.stringify(state));
}
function restoreToolState(tool) {
  try {
    const state=JSON.parse(sessionStorage.getItem(`study-lab:${tool}`) || '{}');
    Object.entries(state).forEach(([id,value]) => {
      const el=panel.querySelector(`#${CSS.escape(id)}`);
      if (!el) return;
      if (el.type === 'checkbox') el.checked=Boolean(value); else el.value=value;
    });
  } catch (_) {}
}

async function runCurrentTool() {
  try {
    saveToolState();
    switch (currentTool) {
      case 'statistics': return runStatistics();
      case 'cleaner': return runCleaner();
      case 'outliers': return runOutliers();
      case 'curve': return runCurve();
      case 'errorbars': return runErrorBars();
      case 'plot': return runPlot();
      case 'xvg': return runXvg();
      case 'structure': return runStructure();
      case 'coordinates': return runCoordinates();
      case 'workflow': return runWorkflow();
      case 'bibtex': return runBibtex();
      case 'bibdedupe': return runBibDedupe();
      case 'doi': return await runDoi();
      case 'journal': return runJournal();
      case 'latextable': return runLatexTable();
      case 'equation': return runEquation();
      case 'units': return runUnits();
      case 'decision': return runDecision();
      case 'kinetics': return runKinetics();
      default: return;
    }
  } catch (error) {
    resultText(`Error: ${error.message}`);
  }
}

function runStatistics() {
  const values=numericValues(panel.querySelector('#input-data').value); requireValues(values,1);
  const s=summary(values);
  resultText([
    `n: ${s.n}`, `sum: ${fmt(s.sum)}`, `mean: ${fmt(s.mean)}`, `median: ${fmt(s.median)}`,
    `min: ${fmt(s.min)}`, `Q1: ${fmt(s.q1)}`, `Q3: ${fmt(s.q3)}`, `max: ${fmt(s.max)}`,
    `population SD: ${fmt(s.sdPopulation)}`, `sample SD: ${fmt(s.sdSample)}`
  ].join('\n'));
}
function runCleaner() {
  const source=panel.querySelector('#input-data').value;
  const delimiter=detectDelimiter(source);
  let parsed=String(source).split(/\r?\n/).map(line => line.split(delimiter));
  if (panel.querySelector('#trim-cells').checked) parsed=parsed.map(row => row.map(cell => cell.trim()));
  if (panel.querySelector('#drop-empty').checked) parsed=parsed.filter(row => row.some(cell => cell !== ''));
  if (panel.querySelector('#dedupe').checked) {
    const seen=new Set(); parsed=parsed.filter(row => { const key=JSON.stringify(row); if(seen.has(key)) return false; seen.add(key); return true; });
  }
  resultText(parsed.map(row => row.map(cell => delimiter === ',' && /[",\n]/.test(cell) ? `"${cell.replace(/"/g,'""')}"` : cell).join(delimiter)).join('\n'));
}
function runOutliers() {
  const values=numericValues(panel.querySelector('#input-data').value); requireValues(values,4);
  const method=panel.querySelector('#method').value;
  const s=summary(values); let flagged=[]; let rule='';
  if (method==='iqr') {
    const iqr=s.q3-s.q1, low=s.q1-1.5*iqr, high=s.q3+1.5*iqr;
    flagged=values.filter(v=>v<low||v>high); rule=`Q1=${fmt(s.q1)}, Q3=${fmt(s.q3)}, IQR=${fmt(iqr)}\nBounds: ${fmt(low)} to ${fmt(high)}`;
  } else {
    const threshold=Math.abs(Number(panel.querySelector('#threshold').value)||3);
    if (!Number.isFinite(s.sdSample) || s.sdSample===0) throw new Error('Sample standard deviation must be greater than zero.');
    flagged=values.filter(v=>Math.abs((v-s.mean)/s.sdSample)>threshold); rule=`Mean=${fmt(s.mean)}, sample SD=${fmt(s.sdSample)}, |z|>${fmt(threshold)}`;
  }
  resultText(`${rule}\n\nFlagged (${flagged.length}): ${flagged.length ? flagged.map(v=>fmt(v)).join(', ') : 'none'}`);
}
function runCurve() {
  const data=pairs(panel.querySelector('#input-data').value); if(data.length<2) throw new Error('Provide at least two x,y pairs.');
  const fit=lineFit(data); resultText(`y = ${fmt(fit.slope)}x ${fit.intercept<0?'-':'+'} ${fmt(Math.abs(fit.intercept))}\nR² = ${fmt(fit.r2)}\nn = ${data.length}`);
  const plot=panel.querySelector('#plot-output'); plot.hidden=false; plot.innerHTML=svgPlot(data,{fit});
}
function runErrorBars() {
  const text=panel.querySelector('#input-data').value;
  const groups=new Map();
  String(text).split(/\r?\n/).forEach(line=>{
    if(!line.trim()) return; const parts=line.split(/[,\t;]/); const group=(parts[0]||'').trim(); const value=Number(parts[1]);
    if(group && Number.isFinite(value)) { if(!groups.has(group)) groups.set(group,[]); groups.get(group).push(value); }
  });
  if(!groups.size) throw new Error('Provide rows like Control,10.');
  const records=[...groups].map(([group,values])=>{const s=summary(values); const sem=s.sdSample/Math.sqrt(s.n); return {group,n:s.n,mean:s.mean,sd:s.sdSample,sem,ci:1.96*sem};});
  panel.querySelector('#table-output').innerHTML=`<table class="output-table"><thead><tr><th>Group</th><th>n</th><th>Mean</th><th>SD</th><th>SEM</th><th>95% CI ±</th></tr></thead><tbody>${records.map(r=>`<tr><td>${escapeHtml(r.group)}</td><td>${r.n}</td><td>${fmt(r.mean)}</td><td>${fmt(r.sd)}</td><td>${fmt(r.sem)}</td><td>${fmt(r.ci)}</td></tr>`).join('')}</tbody></table>`;
}
function runPlot() {
  const data=pairs(panel.querySelector('#input-data').value); if(data.length<1) throw new Error('Provide at least one x,y pair.');
  panel.querySelector('#plot-output').innerHTML=svgPlot(data,{line:panel.querySelector('#plot-type').value==='line'});
}
function runXvg() {
  const raw=panel.querySelector('#input-data').value;
  const data=String(raw).split(/\r?\n/).filter(line=>line.trim()&&!line.trim().startsWith('#')&&!line.trim().startsWith('@')).map(line=>line.trim().split(/\s+/).map(Number)).filter(v=>v.length>=2&&Number.isFinite(v[0])&&Number.isFinite(v[1])).map(v=>[v[0],v[1]]);
  if(data.length<1) throw new Error('No numeric XVG rows found.');
  const ys=data.map(d=>d[1]); const s=summary(ys); resultText(`Rows: ${data.length}\nX range: ${fmt(data[0][0])} → ${fmt(data[data.length-1][0])}\nY mean: ${fmt(s.mean)}\nY min/max: ${fmt(s.min)} / ${fmt(s.max)}`);
  const plot=panel.querySelector('#plot-output'); plot.hidden=false; plot.innerHTML=svgPlot(data,{line:true,xLabel:'XVG x',yLabel:'series 1'});
}
function runStructure() {
  const atoms=pdbAtoms(panel.querySelector('#input-data').value); if(!atoms.length) throw new Error('No valid PDB ATOM/HETATM coordinates found.');
  const chains=[...new Set(atoms.map(a=>a.chain))]; const residues=[...new Set(atoms.map(a=>`${a.chain}:${a.resSeq}:${a.residue}`))]; const elements=[...new Set(atoms.map(a=>a.element).filter(Boolean))];
  const xs=atoms.map(a=>a.x), ys=atoms.map(a=>a.y), zs=atoms.map(a=>a.z);
  resultText(`Atoms: ${atoms.length}\nResidues: ${residues.length}\nChains: ${chains.join(', ')}\nElements: ${elements.join(', ')}\nX: ${fmt(Math.min(...xs))} → ${fmt(Math.max(...xs))}\nY: ${fmt(Math.min(...ys))} → ${fmt(Math.max(...ys))}\nZ: ${fmt(Math.min(...zs))} → ${fmt(Math.max(...zs))}`);
}
function runCoordinates() {
  const dx=Number(panel.querySelector('#dx').value)||0, dy=Number(panel.querySelector('#dy').value)||0, dz=Number(panel.querySelector('#dz').value)||0;
  let changed=0;
  const translated=panel.querySelector('#input-data').value.split(/\r?\n/).map(line=>{
    if(!(line.startsWith('ATOM  ')||line.startsWith('HETATM'))) return line;
    const x=Number(line.slice(30,38)), y=Number(line.slice(38,46)), z=Number(line.slice(46,54)); if(![x,y,z].every(Number.isFinite)) return line;
    changed++; const coord=`${(x+dx).toFixed(3).padStart(8)}${(y+dy).toFixed(3).padStart(8)}${(z+dz).toFixed(3).padStart(8)}`;
    return line.slice(0,30)+coord+line.slice(54);
  }).join('\n');
  resultText(`# translated atoms: ${changed}\n${translated}`);
}
function runWorkflow() {
  const engine=panel.querySelector('#engine').value, name=panel.querySelector('#project-name').value.trim()||'md-project';
  const temp=Number(panel.querySelector('#temperature').value)||300, steps=Math.max(1,Math.floor(Number(panel.querySelector('#steps').value)||500000)), dt=Number(panel.querySelector('#timestep').value)||0.002;
  let text='';
  if(engine==='gromacs') text=`# ${name} — GROMACS starter workflow\n# Review force field, solvent, box, restraints, and resources before use.\ngmx pdb2gmx -f input.pdb -o processed.gro -water tip3p\ngmx editconf -f processed.gro -o boxed.gro -c -d 1.0 -bt cubic\ngmx solvate -cp boxed.gro -cs spc216.gro -o solvated.gro -p topol.top\ngmx grompp -f minim.mdp -c solvated.gro -p topol.top -o em.tpr\ngmx mdrun -deffnm em\n# Equilibrate at ${temp} K, then production (${steps} steps; dt=${dt} ps) using validated .mdp files.`;
  if(engine==='lammps') text=`# ${name} — LAMMPS starter input\nunits real\natom_style full\nread_data system.data\ntimestep ${dt}\n# Define force-field styles and coefficients for your system here.\nvelocity all create ${temp} 4928459 mom yes rot yes dist gaussian\nfix thermostat all nvt temp ${temp} ${temp} 100.0\nthermo 1000\nrun ${steps}\nunfix thermostat\nwrite_data ${name}-final.data`;
  if(engine==='plumed') text=`# ${name} — PLUMED starter file\n# Example distance collective variable; replace atom IDs and CVs for your system.\nd: DISTANCE ATOMS=1,2\nPRINT ARG=d STRIDE=100 FILE=COLVAR\n# Run with your MD engine's PLUMED integration at approximately ${temp} K.`;
  resultText(text);
}
function runBibtex() {
  let text=panel.querySelector('#input-data').value.replace(/[“”]/g,'"').replace(/[‘’]/g,"'").replace(/\r\n/g,'\n');
  text=text.replace(/\b(AUTHOR|TITLE|JOURNAL|YEAR|DOI|URL|VOLUME|NUMBER|PAGES)\s*=/gi,(m)=>m.toLowerCase());
  text=text.replace(/[ \t]+$/gm,'').replace(/\n{3,}/g,'\n\n');
  resultText(text.trim());
}
function runBibDedupe() {
  const entries=parseBibEntries(panel.querySelector('#input-data').value); if(!entries.length) throw new Error('No BibTeX entries found.');
  const seen=new Set(), kept=[], removed=[];
  entries.forEach(entry=>{
    const doi=normalizeDoi(bibField(entry,'doi')), title=normalizeTitle(bibField(entry,'title')); const key=doi?`doi:${doi}`:title?`title:${title}`:`raw:${normalizeTitle(entry)}`;
    if(seen.has(key)) removed.push(entry); else {seen.add(key); kept.push(entry);}
  });
  resultText(`# kept: ${kept.length}; removed duplicates: ${removed.length}\n\n${kept.join('\n\n')}`);
}
async function runDoi() {
  const doi=normalizeDoi(panel.querySelector('#doi-value').value); if(!doi) throw new Error('Enter a DOI.');
  resultText('Fetching from Crossref…');
  const response=await fetch(`https://api.crossref.org/works/${encodeURIComponent(doi)}/transform/application/x-bibtex`,{headers:{Accept:'application/x-bibtex'}});
  if(!response.ok) throw new Error(`Crossref returned HTTP ${response.status}.`);
  resultText(await response.text());
}
function runJournal() {
  const title=panel.querySelector('#journal-title').value.trim(); if(!title) throw new Error('Enter a journal title.');
  const stop=new Set(['of','the','and','in','on','for','to','a','an']);
  const map={journal:'J',international:'Int',molecular:'Mol',biology:'Biol',biological:'Biol',chemistry:'Chem',chemical:'Chem',physics:'Phys',physical:'Phys',medicine:'Med',medical:'Med',science:'Sci',scientific:'Sci',research:'Res',clinical:'Clin',experimental:'Exp',engineering:'Eng',technology:'Technol',computational:'Comput',methods:'Methods',materials:'Mater',environmental:'Environ',american:'Am',european:'Eur'};
  const words=title.split(/\s+/).map(word=>word.replace(/[^A-Za-z-]/g,'')).filter(Boolean);
  const abbr=words.map(word=>{const low=word.toLowerCase(); if(stop.has(low)) return ''; if(map[low]) return map[low]; if(word.length<=4) return word; return word.slice(0,4).replace(/[-.]$/,'');}).filter(Boolean).join(' ');
  resultText(`${abbr}\n\nNote: this is a practical local heuristic, not a complete LTWA/ISO 4 authority lookup.`);
}
function latexEscape(value) { return String(value).replace(/([&_#$%])/g,'\\$1'); }
function runLatexTable() {
  const parsed=rows(panel.querySelector('#input-data').value).filter(row=>row.some(cell=>cell.trim())); if(!parsed.length) throw new Error('Provide at least one table row.');
  const columns=Math.max(...parsed.map(r=>r.length)); const spec='l'+'r'.repeat(Math.max(0,columns-1));
  const body=parsed.map((row,index)=>`${row.map(cell=>latexEscape(cell.trim())).join(' & ')} \\\\${index===0?'\n\\hline':''}`).join('\n');
  resultText(`\\begin{tabular}{${spec}}\n\\hline\n${body}\n\\hline\n\\end{tabular}`);
}
function runEquation() {
  const eq=panel.querySelector('#equation-value').value.trim(); if(!eq) throw new Error('Enter a LaTeX expression.');
  resultText(panel.querySelector('#equation-mode').value==='inline' ? `\\(${eq}\\)` : `\\[\n${eq}\n\\]`);
}

const units = {
  length: {m:1, cm:1e-2, mm:1e-3, um:1e-6, nm:1e-9, angstrom:1e-10, km:1e3},
  energy: {J:1, kJ:1e3, cal:4.184, kcal:4184, eV:1.602176634e-19, kJmol:1000/6.02214076e23, kcalmol:4184/6.02214076e23},
  pressure: {Pa:1, kPa:1e3, MPa:1e6, bar:1e5, atm:101325, torr:133.322368421},
  temperature: {C:null, K:null, F:null},
};
function setupUnitSelects() {
  const category=panel.querySelector('#unit-category');
  const update=()=>{
    const names=Object.keys(units[category.value]); const from=panel.querySelector('#unit-from'), to=panel.querySelector('#unit-to');
    from.innerHTML=names.map(n=>`<option value="${n}">${n}</option>`).join(''); to.innerHTML=names.map(n=>`<option value="${n}">${n}</option>`).join('');
    if(names.length>1) to.selectedIndex=1;
  };
  category.addEventListener('change',update); update(); restoreToolState('units');
}
function convertTemperature(value, from, to) {
  let k=from==='K'?value:from==='C'?value+273.15:(value-32)*5/9+273.15;
  return to==='K'?k:to==='C'?k-273.15:(k-273.15)*9/5+32;
}
function runUnits() {
  const category=panel.querySelector('#unit-category').value, value=Number(panel.querySelector('#unit-value').value); if(!Number.isFinite(value)) throw new Error('Enter a numeric value.');
  const from=panel.querySelector('#unit-from').value, to=panel.querySelector('#unit-to').value;
  const result=category==='temperature'?convertTemperature(value,from,to):value*units[category][from]/units[category][to];
  resultText(`${fmt(value)} ${from} = ${fmt(result,10)} ${to}`);
}
function runDecision() {
  const parsed=String(panel.querySelector('#input-data').value).split(/\r?\n/).map(line=>line.split(',').map(v=>v.trim())).filter(row=>row.length>=2&&row[0]);
  const scored=parsed.map(row=>({option:row[0], scores:row.slice(1).map(Number).filter(Number.isFinite)})).filter(r=>r.scores.length).map(r=>({...r,total:r.scores.reduce((a,b)=>a+b,0),average:r.scores.reduce((a,b)=>a+b,0)/r.scores.length})).sort((a,b)=>b.total-a.total);
  if(!scored.length) throw new Error('Provide rows like Option A,8,7,9.');
  resultText(scored.map((r,i)=>`${i+1}. ${r.option}: total ${fmt(r.total)}, average ${fmt(r.average)} (${r.scores.join(', ')})`).join('\n'));
}
function runKinetics() {
  const c0=Number(panel.querySelector('#c0').value), k=Number(panel.querySelector('#rate-k').value), maxTime=Number(panel.querySelector('#max-time').value); if(![c0,k,maxTime].every(Number.isFinite)||c0<0||k<=0||maxTime<=0) throw new Error('Use C₀ ≥ 0, k > 0, and max time > 0.');
  const data=[]; for(let i=0;i<=40;i++){const t=maxTime*i/40; data.push([t,c0*Math.exp(-k*t)]);} const half=Math.log(2)/k;
  resultText(`C(t) = ${fmt(c0)} · e^(-${fmt(k)}t)\nHalf-life = ${fmt(half)} time units\nC(${fmt(maxTime)}) = ${fmt(c0*Math.exp(-k*maxTime))}`);
  const plot=panel.querySelector('#plot-output'); plot.hidden=false; plot.innerHTML=svgPlot(data,{line:true,xLabel:'time',yLabel:'concentration'});
}

function setupDigitizer() {
  const file=panel.querySelector('#digitizer-file'), canvas=panel.querySelector('#digitizer-canvas');
  file.addEventListener('change',()=>{
    const selected=file.files?.[0]; if(!selected) return;
    const reader=new FileReader(); reader.onload=()=>{const img=new Image(); img.onload=()=>{digitizerImage=img; digitizerPoints=[]; drawDigitizer();}; img.src=reader.result;}; reader.readAsDataURL(selected);
  });
  canvas.addEventListener('click',(event)=>{
    if(!digitizerImage) return;
    const rect=canvas.getBoundingClientRect(); const px=(event.clientX-rect.left)*canvas.width/rect.width, py=(event.clientY-rect.top)*canvas.height/rect.height;
    const xmin=Number(panel.querySelector('#xmin').value), xmax=Number(panel.querySelector('#xmax').value), ymin=Number(panel.querySelector('#ymin').value), ymax=Number(panel.querySelector('#ymax').value);
    if(![xmin,xmax,ymin,ymax].every(Number.isFinite)||xmin===xmax||ymin===ymax) return;
    digitizerPoints.push({px,py,x:xmin+(px/canvas.width)*(xmax-xmin),y:ymax-(py/canvas.height)*(ymax-ymin)}); drawDigitizer();
  });
  panel.querySelector('#clear-digitizer').addEventListener('click',()=>{digitizerPoints=[]; drawDigitizer();});
  panel.querySelector('#copy-digitizer').addEventListener('click',()=>copyText(['x,y',...digitizerPoints.map(p=>`${p.x},${p.y}`)].join('\n')));
  drawDigitizer();
}
function drawDigitizer() {
  const canvas=panel.querySelector('#digitizer-canvas'); if(!canvas) return; const ctx=canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height); ctx.fillStyle='#f7f7f7'; ctx.fillRect(0,0,canvas.width,canvas.height);
  if(digitizerImage) {
    const ratio=Math.min(900/digitizerImage.width,480/digitizerImage.height,1); canvas.width=Math.max(1,Math.round(digitizerImage.width*ratio)); canvas.height=Math.max(1,Math.round(digitizerImage.height*ratio)); ctx.drawImage(digitizerImage,0,0,canvas.width,canvas.height);
  }
  ctx.fillStyle='#0b746d'; digitizerPoints.forEach(p=>{ctx.beginPath();ctx.arc(p.px,p.py,5,0,Math.PI*2);ctx.fill();});
  const result=panel.querySelector('#result'); if(result) result.textContent=digitizerPoints.length ? ['x,y',...digitizerPoints.map(p=>`${fmt(p.x,8)},${fmt(p.y,8)}`)].join('\n') : 'Upload an image, set full-image axis bounds, then click data points.';
}

function setupTimer() {
  const focus=panel.querySelector('#focus-minutes'), display=panel.querySelector('#timer-display'), status=panel.querySelector('#timer-status');
  const resetTo=(minutes,label)=>{stopTimer(); timerSeconds=Math.max(1,Math.round(Number(minutes)||1))*60; renderTimer(display); status.textContent=`${label} ready.`;};
  panel.querySelector('#timer-start').addEventListener('click',()=>{if(timerInterval) return; status.textContent='Timer running.'; timerInterval=setInterval(()=>{timerSeconds--; renderTimer(display); if(timerSeconds<=0){stopTimer(); status.textContent='Session complete.';}},1000);});
  panel.querySelector('#timer-pause').addEventListener('click',()=>{stopTimer(); status.textContent='Paused.';});
  panel.querySelector('#timer-reset').addEventListener('click',()=>resetTo(focus.value,'Focus session'));
  panel.querySelector('#timer-break').addEventListener('click',()=>resetTo(panel.querySelector('#break-minutes').value,'Break'));
  timerSeconds=Math.max(1,Math.round(Number(focus.value)||25))*60; renderTimer(display);
}
function renderTimer(display) { const m=Math.floor(timerSeconds/60), s=Math.max(0,timerSeconds%60); display.textContent=`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`; }
function stopTimer() { if(timerInterval){clearInterval(timerInterval);timerInterval=null;} }

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); courseFileStatus.textContent='Copied to clipboard.'; }
  catch (_) { const area=document.createElement('textarea');area.value=text;document.body.append(area);area.select();document.execCommand('copy');area.remove();courseFileStatus.textContent='Copied to clipboard.'; }
}
async function copyResult() {
  const result=panel.querySelector('#result'); if(result) return copyText(result.textContent);
  const table=panel.querySelector('#table-output'); if(table) return copyText(table.innerText);
}

async function loadCourseFiles() {
  try {
    const response=await fetch('/api/downloads'); if(!response.ok) throw new Error(`HTTP ${response.status}`); const payload=await response.json();
    const allowed=['.txt','.csv','.tsv','.md','.json','.xvg','.pdb','.gro','.bib','.dat','.log'];
    const files=(payload.files||[]).filter(item=>item.type==='file'&&allowed.some(ext=>item.path.toLowerCase().endsWith(ext)));
    courseFile.innerHTML=files.length ? `<option value="">Choose a compatible downloaded file</option>${files.map(item=>`<option value="${escapeAttr(item.path)}">${escapeHtml(item.path)}</option>`).join('')}` : '<option value="">No compatible text/data files found</option>';
    courseFileButton.disabled=!files.length;
  } catch (error) {
    courseFile.innerHTML='<option value="">Downloads unavailable</option>'; courseFileButton.disabled=true; courseFileStatus.textContent=`Could not load downloads: ${error.message}`; courseFileStatus.classList.add('error');
  }
}
function encodedFilePath(path) { return String(path).split('/').map(encodeURIComponent).join('/'); }
async function loadSelectedCourseFile() {
  const path=courseFile.value; if(!path) return;
  const target=panel.querySelector('textarea'); if(!currentTool||!target){courseFileStatus.textContent='Open a text-based tool first.';return;}
  courseFileStatus.classList.remove('error'); courseFileStatus.textContent='Loading file…';
  try { const response=await fetch(`/files/${encodedFilePath(path)}`); if(!response.ok) throw new Error(`HTTP ${response.status}`); target.value=await response.text(); saveToolState(); courseFileStatus.textContent=`Loaded ${path} into ${toolMeta[currentTool][0]}.`; }
  catch(error){courseFileStatus.textContent=`Could not load file: ${error.message}`;courseFileStatus.classList.add('error');}
}

searchInput.addEventListener('input',()=>{
  const query=searchInput.value.trim().toLowerCase(); document.querySelectorAll('.tool-card').forEach(card=>{card.hidden=query&&!card.dataset.search.includes(query)&&!card.textContent.toLowerCase().includes(query);});
});
document.querySelector('#tool-grid').addEventListener('click',(event)=>{const button=event.target.closest('[data-open]');if(button)openTool(button.dataset.open);});
panel.addEventListener('click',(event)=>{const action=event.target.closest('[data-action]')?.dataset.action;if(action==='run')runCurrentTool();if(action==='copy')copyResult();});
panel.addEventListener('input',saveToolState);
document.querySelector('#clear-state').addEventListener('click',()=>{if(currentTool)sessionStorage.removeItem(`study-lab:${currentTool}`);panel.innerHTML='<div class="empty-state"><strong>Active tool cleared.</strong><p>Choose a tool above to start again.</p></div>';titleEl.textContent='Choose a tool';descriptionEl.textContent='Open any tool above to begin. Compatible downloaded files can be loaded into text-based tools.';currentTool=null;sessionStorage.removeItem('study-lab:active-tool');stopTimer();});
courseFileButton.addEventListener('click',loadSelectedCourseFile);
courseFile.addEventListener('change',()=>{courseFileButton.disabled=!courseFile.value;});

loadCourseFiles();
const restored=sessionStorage.getItem('study-lab:active-tool');
if(restored&&templates[restored]) openTool(restored);

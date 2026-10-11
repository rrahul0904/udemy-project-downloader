import * as StemCurve from '../vendor/stemkit-core/curve-fitting.js';
import { hasVendor, registerFromGlobals } from '../vendor/stemkit-core/vendor.js';

const REGRESSION_SRC = '/static/vendor/stemkit-dependencies/regression.min.js';
let regressionLoadPromise = null;

function isCurvePanel(panel) {
  return Boolean(panel?.querySelector('#input-data')) &&
    document.querySelector('#workspace-title')?.textContent?.trim() === 'Curve Fitter';
}

function ensureRegression() {
  registerFromGlobals();
  if (hasVendor('regression')) return Promise.resolve(true);
  if (regressionLoadPromise) return regressionLoadPromise;

  regressionLoadPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-stemkit-regression="true"]`);
    const onReady = () => {
      registerFromGlobals();
      if (hasVendor('regression')) resolve(true);
      else reject(new Error('regression.js loaded but did not register a browser global.'));
    };
    if (existing) {
      if (existing.dataset.loaded === 'true') onReady();
      else {
        existing.addEventListener('load', onReady, { once: true });
        existing.addEventListener('error', () => reject(new Error('Unable to load the local regression.js bundle.')), { once: true });
      }
      return;
    }

    const script = document.createElement('script');
    script.src = REGRESSION_SRC;
    script.dataset.stemkitRegression = 'true';
    script.addEventListener('load', () => {
      script.dataset.loaded = 'true';
      onReady();
    }, { once: true });
    script.addEventListener('error', () => reject(new Error('Unable to load the local regression.js bundle.')), { once: true });
    document.head.appendChild(script);
  });
  return regressionLoadPromise;
}

function addModelPicker(panel) {
  if (panel.querySelector('#curve-model')) return;
  const actions = panel.querySelector('.actions');
  if (!actions) return;
  const wrap = document.createElement('div');
  wrap.className = 'form-grid';
  wrap.dataset.stemkitCurveControls = 'true';
  wrap.innerHTML = `
    <label class="field"><span>Fit model</span><select id="curve-model">
      <option value="linear">Linear</option>
      <option value="polynomial2">Quadratic</option>
      <option value="polynomial3">Cubic</option>
      <option value="exponential">Exponential</option>
      <option value="power">Power</option>
      <option value="logarithmic">Logarithmic</option>
    </select></label>
    <div class="field"><span>Scientific engine</span><div class="status" data-curve-engine-status>Loading local regression.js…</div></div>`;
  actions.before(wrap);
  const run = actions.querySelector('[data-action="run"]');
  if (run) {
    run.textContent = 'Loading curve engine…';
    run.disabled = true;
  }

  ensureRegression().then(() => {
    const status = panel.querySelector('[data-curve-engine-status]');
    if (status) status.textContent = 'STEMKit core + regression.js 2.0.1';
    if (run) {
      run.textContent = 'Fit curve';
      run.disabled = false;
    }
  }).catch((err) => {
    const status = panel.querySelector('[data-curve-engine-status]');
    if (status) status.textContent = `Legacy linear fallback only: ${err.message}`;
    if (run) {
      run.textContent = 'Fit line (fallback)';
      run.disabled = false;
    }
  });
}

function numberText(value) {
  return Number.isFinite(value) ? Number(value).toPrecision(7).replace(/\.?0+$/, '') : 'n/a';
}

function renderCurvePlot(plot, fit) {
  if (!plot || !fit?.points?.length) return;
  const width = 700;
  const height = 320;
  const pad = 34;
  const samples = StemCurve.sampleCurve(fit.predict,
    Math.min(...fit.points.map(([x]) => x)),
    Math.max(...fit.points.map(([x]) => x)), 120);
  const allX = [...fit.points.map(([x]) => x), ...samples.x];
  const allY = [...fit.points.map(([, y]) => y), ...samples.y];
  let xmin = Math.min(...allX), xmax = Math.max(...allX);
  let ymin = Math.min(...allY), ymax = Math.max(...allY);
  if (xmin === xmax) { xmin -= 1; xmax += 1; }
  if (ymin === ymax) { ymin -= 1; ymax += 1; }
  const sx = (x) => pad + ((x - xmin) / (xmax - xmin)) * (width - pad * 2);
  const sy = (y) => height - pad - ((y - ymin) / (ymax - ymin)) * (height - pad * 2);
  const path = samples.x.map((x, i) => `${i ? 'L' : 'M'} ${sx(x).toFixed(2)} ${sy(samples.y[i]).toFixed(2)}`).join(' ');
  const dots = fit.points.map(([x, y]) => `<circle cx="${sx(x).toFixed(2)}" cy="${sy(y).toFixed(2)}" r="4" fill="currentColor" />`).join('');
  plot.hidden = false;
  plot.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Observed points and fitted ${fit.model} curve">
    <line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}" stroke="currentColor" opacity=".25" />
    <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height-pad}" stroke="currentColor" opacity=".25" />
    <path d="${path}" fill="none" stroke="currentColor" stroke-width="2.5" opacity=".75" />
    <g>${dots}</g>
  </svg>`;
}

async function runCurveParity(panel) {
  await ensureRegression();
  const raw = panel.querySelector('#input-data')?.value ?? '';
  const model = panel.querySelector('#curve-model')?.value || 'linear';
  const parsed = StemCurve.parseXYData(raw);
  if (parsed.data.length < 2) throw new Error('Provide at least two valid x,y pairs.');
  const fit = StemCurve.fitCurve(parsed.data, model, { precision: 10 });
  if (fit.error) throw new Error(fit.error);

  const notes = [];
  if (fit.adequacy?.message) notes.push(fit.adequacy.message);
  if (fit.linearised) notes.push('This model is fit by regression.js linearisation; R² and RMSE shown here are recomputed in the original y units.');
  notes.push(...parsed.warnings);

  const result = panel.querySelector('#result');
  if (result) result.textContent = [
    StemCurve.formatEquation(fit.equation, fit.model),
    `model = ${fit.model}`,
    `R² = ${numberText(fit.r2)}`,
    `adjusted R² = ${numberText(fit.adjR2)}`,
    `RMSE = ${numberText(fit.rmse)}`,
    `n = ${fit.n}; parameters = ${fit.nParams}`,
    ...notes.map((note) => `Note: ${note}`)
  ].join('\n');
  renderCurvePlot(panel.querySelector('#plot-output'), fit);
}

export function enhanceCurvePanel(panel) {
  if (!isCurvePanel(panel)) return;
  addModelPicker(panel);
  if (panel.dataset.stemkitCurveBound === 'true') return;
  panel.dataset.stemkitCurveBound = 'true';
  panel.addEventListener('click', (event) => {
    const run = event.target.closest('[data-action="run"]');
    if (!run || !isCurvePanel(panel)) return;
    if (!hasVendor('regression')) return; // Explicit legacy linear fallback if the local bundle failed to register.
    event.preventDefault();
    event.stopImmediatePropagation();
    runCurveParity(panel).catch((err) => {
      const result = panel.querySelector('#result');
      if (result) result.textContent = `Error: ${err.message}`;
    });
  }, true);
}

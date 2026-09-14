import * as StemDigitizer from '../vendor/stemkit-core/digitizer.js';

function field(id, label, value, step = 'any') {
  return `<label class="field"><span>${label}</span><input id="${id}" type="number" value="${value}" step="${step}" /></label>`;
}

function checkbox(id, label) {
  return `<label class="field"><span>${label}</span><input id="${id}" type="checkbox" /></label>`;
}

function number(panel, id) {
  return Number(panel.querySelector(`#${CSS.escape(id)}`)?.value);
}

function calibrationFromPanel(panel) {
  return {
    pxX1: number(panel, 'digitizer-px-x1'),
    pxX2: number(panel, 'digitizer-px-x2'),
    pxY1: number(panel, 'digitizer-px-y1'),
    pxY2: number(panel, 'digitizer-px-y2'),
    valX1: number(panel, 'xmin'),
    valX2: number(panel, 'xmax'),
    valY1: number(panel, 'ymin'),
    valY2: number(panel, 'ymax'),
    logX: Boolean(panel.querySelector('#digitizer-log-x')?.checked),
    logY: Boolean(panel.querySelector('#digitizer-log-y')?.checked),
  };
}

function formatResolution(calibration) {
  const resolution = StemDigitizer.pixelResolution(calibration);
  if (!resolution) return 'Resolution unavailable until calibration is valid.';
  const parts = [];
  if (Number.isFinite(resolution.dx)) parts.push(`X ≈ ${StemDigitizer.formatValue(resolution.dx)} units/pixel`);
  if (Number.isFinite(resolution.dy)) parts.push(`Y ≈ ${StemDigitizer.formatValue(resolution.dy)} units/pixel`);
  if (Number.isFinite(resolution.xRatio)) parts.push(`X ratio ≈ ${StemDigitizer.formatValue(resolution.xRatio)}×/pixel`);
  if (Number.isFinite(resolution.yRatio)) parts.push(`Y ratio ≈ ${StemDigitizer.formatValue(resolution.yRatio)}×/pixel`);
  return parts.length ? `Pixel resolution: ${parts.join(' · ')}` : 'Resolution unavailable until calibration is valid.';
}

function render(canvas, image, points, calibration) {
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#f7f7f7';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (image) ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

  const check = StemDigitizer.validateCalibration(calibration);
  if (check.valid) {
    const x1 = calibration.pxX1;
    const x2 = calibration.pxX2;
    const y1 = calibration.pxY1;
    const y2 = calibration.pxY2;
    ctx.save();
    ctx.strokeStyle = '#96631a';
    ctx.setLineDash([7, 5]);
    ctx.lineWidth = 2;
    ctx.strokeRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
    ctx.restore();
  }

  ctx.fillStyle = '#0b746d';
  for (const point of points) {
    ctx.beginPath();
    ctx.arc(point.px, point.py, 5, 0, Math.PI * 2);
    ctx.fill();
  }
}

function resultText(panel, points, calibration) {
  const result = panel.querySelector('#result');
  if (!result) return;
  const check = StemDigitizer.validateCalibration(calibration);
  if (!check.valid) {
    result.textContent = `Calibration error: ${check.errors.join(' ')}`;
    return;
  }
  const rows = points.length
    ? ['x,y', ...points.map(point => `${StemDigitizer.formatValue(point.x)},${StemDigitizer.formatValue(point.y)}`)]
    : ['Calibration valid. Click points inside the calibrated plot region.'];
  result.textContent = `${formatResolution(calibration)}\n\n${rows.join('\n')}`;
}

function copyCsv(points) {
  const text = ['x,y', ...points.map(point => `${StemDigitizer.formatValue(point.x)},${StemDigitizer.formatValue(point.y)}`)].join('\n');
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  const area = document.createElement('textarea');
  area.value = text;
  document.body.append(area);
  area.select();
  document.execCommand('copy');
  area.remove();
  return Promise.resolve();
}

export function enhanceDigitizerPanel(panel) {
  if (!panel || panel.querySelector('#stemkit-digitizer-calibration')) return false;
  const originalFile = panel.querySelector('#digitizer-file');
  const originalCanvas = panel.querySelector('#digitizer-canvas');
  const originalClear = panel.querySelector('#clear-digitizer');
  const originalCopy = panel.querySelector('#copy-digitizer');
  if (!originalFile || !originalCanvas || !originalClear || !originalCopy) return false;

  const file = originalFile.cloneNode(true);
  originalFile.replaceWith(file);
  const canvas = originalCanvas.cloneNode(true);
  originalCanvas.replaceWith(canvas);
  const clearButton = originalClear.cloneNode(true);
  originalClear.replaceWith(clearButton);
  const copyButton = originalCopy.cloneNode(true);
  originalCopy.replaceWith(copyButton);

  const calibrationUi = document.createElement('div');
  calibrationUi.id = 'stemkit-digitizer-calibration';
  calibrationUi.className = 'digitizer-calibration';
  calibrationUi.innerHTML = `
    <p class="status"><strong>Calibrated axes.</strong> Enter the pixel columns/rows corresponding to the numeric axis endpoints. The dashed box shows the active plot region.</p>
    <div class="form-grid four">
      ${field('digitizer-px-x1', 'X₁ pixel', '0')}
      ${field('digitizer-px-x2', 'X₂ pixel', String(canvas.width))}
      ${field('digitizer-px-y1', 'Y₁ pixel', String(canvas.height))}
      ${field('digitizer-px-y2', 'Y₂ pixel', '0')}
    </div>
    <div class="form-grid">
      ${checkbox('digitizer-log-x', 'Logarithmic X axis')}
      ${checkbox('digitizer-log-y', 'Logarithmic Y axis')}
    </div>
    <div class="actions"><button id="digitizer-use-edges" class="ghost" type="button">Use image edges as calibration</button></div>
  `;
  canvas.closest('.digitizer-stage')?.before(calibrationUi);

  const description = document.querySelector('#workspace-description');
  if (description) description.textContent = 'Digitize plot coordinates with explicit pixel calibration, linear or logarithmic axes, validation, and resolution reporting.';

  let image = null;
  let points = [];

  const refresh = () => {
    const calibration = calibrationFromPanel(panel);
    render(canvas, image, points, calibration);
    resultText(panel, points, calibration);
  };

  const useEdges = () => {
    panel.querySelector('#digitizer-px-x1').value = '0';
    panel.querySelector('#digitizer-px-x2').value = String(canvas.width);
    panel.querySelector('#digitizer-px-y1').value = String(canvas.height);
    panel.querySelector('#digitizer-px-y2').value = '0';
    points = [];
    refresh();
  };

  file.addEventListener('change', () => {
    const selected = file.files?.[0];
    if (!selected) return;
    const reader = new FileReader();
    reader.onload = () => {
      const next = new Image();
      next.onload = () => {
        const ratio = Math.min(900 / next.width, 480 / next.height, 1);
        canvas.width = Math.max(1, Math.round(next.width * ratio));
        canvas.height = Math.max(1, Math.round(next.height * ratio));
        image = next;
        points = [];
        useEdges();
      };
      next.src = reader.result;
    };
    reader.readAsDataURL(selected);
  });

  canvas.addEventListener('click', event => {
    if (!image) return;
    const rect = canvas.getBoundingClientRect();
    const px = (event.clientX - rect.left) * canvas.width / rect.width;
    const py = (event.clientY - rect.top) * canvas.height / rect.height;
    const calibration = calibrationFromPanel(panel);
    const check = StemDigitizer.validateCalibration(calibration);
    if (!check.valid) {
      resultText(panel, points, calibration);
      return;
    }
    const mapped = StemDigitizer.toDataCoordinates(px, py, calibration);
    if (!mapped || !Number.isFinite(mapped.x) || !Number.isFinite(mapped.y)) return;
    points.push({ px, py, x: mapped.x, y: mapped.y });
    refresh();
  });

  clearButton.addEventListener('click', () => {
    points = [];
    refresh();
  });
  copyButton.addEventListener('click', () => copyCsv(points));
  panel.querySelector('#digitizer-use-edges').addEventListener('click', useEdges);
  panel.querySelectorAll('#xmin,#xmax,#ymin,#ymax,#digitizer-px-x1,#digitizer-px-x2,#digitizer-px-y1,#digitizer-px-y2,#digitizer-log-x,#digitizer-log-y')
    .forEach(control => control.addEventListener('input', () => {
      points = [];
      refresh();
    }));

  refresh();
  return true;
}

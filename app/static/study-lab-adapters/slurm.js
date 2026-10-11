import * as StemSlurm from '../vendor/stemkit-core/slurm.js';
import * as StemScheduler from '../vendor/stemkit-core/scheduler.js';

const wiredPanels = new WeakSet();

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[char]));
}

function textField(id, label, value, type = 'text', step = '') {
  return `<label class="field"><span>${esc(label)}</span><input id="${id}" type="${type}" value="${esc(value)}"${step ? ` step="${esc(step)}"` : ''} /></label>`;
}

function selectField(id, label, options) {
  return `<label class="field"><span>${esc(label)}</span><select id="${id}">${options.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join('')}</select></label>`;
}

function checked(panel, id) {
  return Boolean(panel.querySelector(`#${CSS.escape(id)}`)?.checked);
}

function value(panel, id, fallback = '') {
  const raw = panel.querySelector(`#${CSS.escape(id)}`)?.value;
  return raw == null || raw === '' ? fallback : raw;
}

function intValue(panel, id, fallback) {
  const parsed = Number.parseInt(value(panel, id, String(fallback)), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function floatValue(panel, id, fallback = null) {
  const raw = value(panel, id, '');
  if (raw === '') return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
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

function buildConfig(panel) {
  const engine = value(panel, 'engine', 'gromacs');
  const rawName = value(panel, 'project-name', 'md-project').trim() || 'md-project';
  const jobName = rawName.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'md-project';
  const modules = value(panel, 'slurm-modules', '')
    .split(/[\n,]+/)
    .map(item => item.trim())
    .filter(Boolean);

  const config = {
    scheduler: value(panel, 'hpc-scheduler', 'slurm'),
    engine,
    jobName,
    partition: value(panel, 'slurm-partition', '').trim(),
    nodes: intValue(panel, 'slurm-nodes', 1),
    gpus: intValue(panel, 'slurm-gpus', 0),
    cpusPerTask: intValue(panel, 'slurm-cpus', 1),
    tasksPerNode: intValue(panel, 'slurm-tasks', 1),
    walltime: value(panel, 'slurm-walltime', StemSlurm.DEFAULT_WALLTIME).trim(),
    memory: value(panel, 'slurm-memory', '').trim(),
    array: checked(panel, 'slurm-array'),
    arrayRange: value(panel, 'slurm-array-range', StemSlurm.DEFAULT_ARRAY_RANGE).trim(),
    mailUser: value(panel, 'slurm-mail', '').trim(),
    pe: value(panel, 'hpc-pe', StemScheduler.DEFAULT_PE).trim(),
    modules,
    purge: true,
  };

  if (engine === 'gromacs') {
    config.tpr = value(panel, 'slurm-tpr', 'topol.tpr').trim() || 'topol.tpr';
    config.deffnm = value(panel, 'slurm-deffnm', 'md').trim() || 'md';
    config.maxh = floatValue(panel, 'slurm-maxh', null);
    config.plumed = value(panel, 'slurm-plumed', '').trim();
    config.appendCheckpoint = true;
  } else if (engine === 'lammps') {
    config.input = value(panel, 'slurm-lammps-input', 'in.lammps').trim() || 'in.lammps';
    config.log = value(panel, 'slurm-lammps-log', 'log.lammps').trim() || 'log.lammps';
    config.suffix = value(panel, 'slurm-lammps-suffix', '').trim();
  }

  return config;
}

function genericEngineBody(config) {
  const scheduler = config.scheduler;
  const env = StemScheduler.envVars(scheduler);
  const launch = StemScheduler.launcher(scheduler, config);
  const lines = [];

  if (env.submitDir) lines.push(`cd "\$${env.submitDir}"`, '');
  const modules = StemSlurm.buildModuleBlock(config.modules || [], config);
  if (modules) lines.push(modules.trimEnd(), '');
  lines.push('mkdir -p logs', '');

  if (config.engine === 'gromacs') {
    const threadExpr = env.cpusPerTask ? `\${${env.cpusPerTask}:-${Math.max(1, config.cpusPerTask)}}` : String(Math.max(1, config.cpusPerTask));
    lines.push(`export OMP_NUM_THREADS=${threadExpr}`, '');
    let command = `${launch} gmx mdrun -s ${config.tpr} -deffnm ${config.deffnm} -ntomp \${OMP_NUM_THREADS}`;
    if (config.gpus > 0) command += ' -nb gpu -pme gpu -bonded gpu';
    if (Number.isFinite(config.maxh) && config.maxh > 0) command += ` -maxh ${config.maxh}`;
    if (config.plumed) command += ` -plumed ${config.plumed}`;
    if (config.appendCheckpoint) {
      lines.push(`if [ -f ${config.deffnm}.cpt ]; then`);
      lines.push(`    ${command} -cpi ${config.deffnm}.cpt -append`);
      lines.push('else');
      lines.push(`    ${command}`);
      lines.push('fi');
    } else {
      lines.push(command);
    }
  } else {
    let command = `${launch} lmp`;
    if (config.gpus > 0) command += ` -sf ${config.suffix || 'gpu'} -pk gpu ${config.gpus}`;
    else if (config.suffix) command += ` -sf ${config.suffix}`;
    command += ` -in ${config.input} -log ${config.log}`;
    lines.push(command);
  }

  return `${lines.join('\n')}\n`;
}

function generateAcrossScheduler(config) {
  if (config.scheduler === 'slurm') {
    return {
      ...StemSlurm.generateScript(config),
      submit: StemScheduler.submitCommand('slurm'),
      scheduler: StemScheduler.getScheduler('slurm'),
    };
  }

  const header = StemScheduler.buildHeader(config);
  const resourceWarnings = StemSlurm.validateResources(config);
  return {
    script: `${header.script}\n${genericEngineBody(config)}`.replace(/\n{3,}/g, '\n\n'),
    warnings: [...header.warnings, ...resourceWarnings],
    submit: StemScheduler.submitCommand(config.scheduler),
    scheduler: StemScheduler.getScheduler(config.scheduler),
  };
}

function renderGeneratedScript(panel) {
  const config = buildConfig(panel);
  if (config.engine === 'plumed') return false;

  const generated = generateAcrossScheduler(config);
  const hardErrors = generated.warnings.filter(item => item.level === 'error');
  if (hardErrors.length) throw new Error(hardErrors.map(item => item.message).join(' '));

  const effectiveWalltime = StemSlurm.isValidWallTime(config.walltime)
    ? config.walltime
    : StemSlurm.DEFAULT_WALLTIME;
  const estimate = StemSlurm.estimateCoreHours({ ...config, walltime: effectiveWalltime });
  const temperature = Number(value(panel, 'temperature', '300'));
  const steps = intValue(panel, 'steps', 500000);
  const timestep = Number(value(panel, 'timestep', '0.002'));

  const notes = [
    `# Generated by Course Intelligence Study Lab using STEMKit ${generated.scheduler.label} scheduler semantics.`,
    `# Submit with: ${generated.submit}`,
    `# Simulation context: temperature=${Number.isFinite(temperature) ? temperature : 300} K; steps=${steps}; timestep=${Number.isFinite(timestep) ? timestep : 0.002} ps.`
  ];
  if (generated.scheduler.logDirAtStart) notes.push('# Create logs/ before submission because this scheduler opens log paths at job start.');
  if (estimate) notes.push(`# Allocation estimate: ${estimate.cores} core(s) × ${estimate.hours.toFixed(3)} h = ${estimate.coreHours.toFixed(3)} core-hours.`);
  for (const warning of generated.warnings) notes.push(`# STEMKit ${String(warning.level || 'note').toUpperCase()}: ${warning.message}`);

  panel.querySelector('#result').textContent = `${notes.join('\n')}\n\n${generated.script}`;
  const summary = panel.querySelector('#slurm-summary');
  if (summary) {
    const warnings = generated.warnings.length;
    summary.textContent = `${config.engine === 'gromacs' ? 'GROMACS' : 'LAMMPS'} · ${generated.scheduler.label}${estimate ? ` · ${estimate.coreHours.toFixed(2)} core-hours` : ''}${warnings ? ` · ${warnings} warning${warnings === 1 ? '' : 's'}` : ''}.`;
  }
  return true;
}

function updateMode(panel) {
  const engine = value(panel, 'engine', 'gromacs');
  const root = panel.querySelector('#stemkit-slurm-resources');
  if (!root) return;
  root.hidden = engine === 'plumed';
  panel.querySelectorAll('[data-slurm-engine]').forEach(section => {
    section.hidden = section.dataset.slurmEngine !== engine;
  });
  const scheduler = value(panel, 'hpc-scheduler', 'slurm');
  const pe = panel.querySelector('#hpc-pe')?.closest('.field');
  if (pe) pe.hidden = scheduler !== 'sge';
  const note = panel.querySelector('#slurm-mode-note');
  if (note) {
    note.textContent = engine === 'plumed'
      ? 'PLUMED input is generated by the version-aware STEMKit PLUMED adapter below.'
      : `This mode generates a validated ${StemScheduler.getScheduler(scheduler).label} batch script using STEMKit scheduler semantics.`;
  }
}

function installRunInterceptor(panel) {
  if (wiredPanels.has(panel)) return;
  wiredPanels.add(panel);
  panel.addEventListener('click', event => {
    const button = event.target.closest('[data-action="run"]');
    if (!button || !panel.querySelector('#stemkit-slurm-resources')) return;
    const engine = value(panel, 'engine', 'gromacs');
    if (engine === 'plumed') return;

    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      renderGeneratedScript(panel);
    } catch (error) {
      const result = panel.querySelector('#result');
      if (result) result.textContent = `Error: ${error.message}`;
    }
  }, true);
}

export function enhanceSlurmPanel(panel) {
  if (!panel || panel.querySelector('#stemkit-slurm-resources')) return false;
  const engine = panel.querySelector('#engine');
  const project = panel.querySelector('#project-name');
  const form = panel.querySelector('.tool-form');
  if (!engine || !project || !form || !panel.querySelector('#result')) return false;

  const resources = document.createElement('section');
  resources.id = 'stemkit-slurm-resources';
  resources.className = 'slurm-resources';
  resources.innerHTML = `
    <p id="slurm-mode-note" class="status"></p>
    <div class="form-grid three">
      ${selectField('hpc-scheduler', 'Batch scheduler', StemScheduler.SCHEDULERS.map(item => [item.id, item.label]))}
      ${textField('slurm-partition', 'Queue / partition', 'gpu')}
      ${textField('slurm-walltime', 'Wall time', '24:00:00')}
    </div>
    <div class="form-grid three">
      ${textField('slurm-memory', 'Memory', '32G')}
      ${textField('hpc-pe', 'Grid Engine parallel environment', StemScheduler.DEFAULT_PE)}
      ${textField('slurm-mail', 'Notification email (optional)', '', 'email')}
    </div>
    <div class="form-grid four">
      ${textField('slurm-nodes', 'Nodes', '1', 'number', '1')}
      ${textField('slurm-gpus', 'GPUs / node', '1', 'number', '1')}
      ${textField('slurm-cpus', 'CPUs / task', '8', 'number', '1')}
      ${textField('slurm-tasks', 'Tasks / node', '1', 'number', '1')}
    </div>
    ${textField('slurm-modules', 'Modules (comma separated)', 'gromacs/2024,cuda/12.4')}
    <div class="form-grid">
      <label class="field"><span>Job array</span><input id="slurm-array" type="checkbox" /></label>
      ${textField('slurm-array-range', 'Array range', '1-5')}
    </div>
    <div data-slurm-engine="gromacs">
      <div class="form-grid three">
        ${textField('slurm-tpr', 'TPR file', 'topol.tpr')}
        ${textField('slurm-deffnm', 'Output prefix', 'md')}
        ${textField('slurm-maxh', 'Max runtime for mdrun (h)', '23.5', 'number', 'any')}
      </div>
      ${textField('slurm-plumed', 'PLUMED input (optional)', '')}
    </div>
    <div data-slurm-engine="lammps" hidden>
      <div class="form-grid three">
        ${textField('slurm-lammps-input', 'LAMMPS input', 'in.lammps')}
        ${textField('slurm-lammps-log', 'LAMMPS log', 'log.lammps')}
        ${textField('slurm-lammps-suffix', 'Accelerator suffix (optional)', '')}
      </div>
    </div>
    <p id="slurm-summary" class="status">Configure scheduler/resources, then generate the workflow.</p>
  `;

  const actions = form.querySelector('.actions');
  if (actions) form.insertBefore(resources, actions);
  else form.append(resources);

  restoreExtendedState(panel);
  updateMode(panel);
  engine.addEventListener('change', () => updateMode(panel));
  panel.querySelector('#hpc-scheduler')?.addEventListener('change', () => updateMode(panel));
  installRunInterceptor(panel);

  const description = document.querySelector('#workspace-description');
  if (description) description.textContent = 'Generate validated GROMACS or LAMMPS batch scripts for SLURM, PBS Pro/OpenPBS, LSF, or Grid Engine with scheduler-specific warnings and submission commands.';
  return true;
}

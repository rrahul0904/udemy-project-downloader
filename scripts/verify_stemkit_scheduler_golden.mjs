import assert from 'node:assert/strict';

import * as Scheduler from '../app/static/vendor/stemkit-core/scheduler.js';
import * as Slurm from '../app/static/vendor/stemkit-core/slurm.js';

const threaded = {
  engine: 'gromacs', jobName: 'md_prod', nodes: 1, gpus: 1, cpusPerTask: 8,
  walltime: '24:00:00', memory: '32G'
};
const mpi = {
  engine: 'lammps', jobName: 'melt', nodes: 2, gpus: 0, tasksPerNode: 16, cpusPerTask: 1,
  walltime: '1-12:00:00', memory: '64G'
};

assert.deepEqual(Scheduler.SCHEDULERS.map(s => s.id), ['slurm', 'pbs', 'lsf', 'sge']);
assert.equal(Scheduler.submitCommand('slurm'), 'sbatch submit.sh');
assert.equal(Scheduler.submitCommand('pbs'), 'qsub submit.sh');
assert.equal(Scheduler.submitCommand('lsf'), 'bsub < submit.sh');
assert.equal(Scheduler.submitCommand('sge', 'run.sh'), 'qsub run.sh');

assert.equal(Scheduler.envVars('pbs').nodeFile, 'PBS_NODEFILE');
assert.equal(Scheduler.launcher('pbs', { cpusPerTask: 4 }), 'mpirun -np $(wc -l < "$PBS_NODEFILE")');
assert.equal(Scheduler.launcher('lsf', { cpusPerTask: 2 }), 'mpirun -np $((LSB_DJOB_NUMPROC / 2))');
assert.equal(Scheduler.launcher('sge', { cpusPerTask: 4 }), 'mpirun -np $((NSLOTS / 4))');

assert.equal(Scheduler.walltimeToSeconds('1-12:00:00'), 129600);
assert.equal(Scheduler.formatHMS(129600), '36:00:00');
assert.deepEqual(Scheduler.lsfWallTime('00:30:30'), { value: '0:31', rounded: true });
assert.equal(Scheduler.convertMemory('1.5T', 'pbs'), '1536gb');
assert.equal(Scheduler.convertMemory('32G', 'lsf'), '32768');
assert.equal(Scheduler.convertMemory('1.5T', 'sge'), '1536G');
assert.deepEqual(Scheduler.parseArrayRange('1-100:2%4'), {
  segments: [{ start: 1, end: 100, step: 2 }], cap: 4
});

// SLURM scheduler abstraction must remain byte-for-byte delegated to the established core.
const slurmConfig = { scheduler: 'slurm', ...threaded, array: true, arrayRange: '1-10%2', partition: 'gpu' };
assert.deepEqual(Scheduler.buildHeader(slurmConfig), Slurm.buildSlurmHeader(slurmConfig));

const pbs = Scheduler.buildHeader({ scheduler: 'pbs', ...mpi });
assert.match(pbs.script, /#PBS -l select=2:ncpus=16:mpiprocs=16:ompthreads=1:mem=64gb/);
assert.match(pbs.script, /#PBS -l place=scatter/);
assert.match(pbs.script, /#PBS -l walltime=36:00:00/);

const pbsArray = Scheduler.buildHeader({
  scheduler: 'pbs', ...threaded, array: true, arrayRange: '1-100:2%4'
});
assert.match(pbsArray.script, /#PBS -J 1-100:2%4/);
assert.ok(pbsArray.warnings.some(w => w.field === 'arrayMemory' && w.concurrent === 4));

const lsf = Scheduler.buildHeader({ scheduler: 'lsf', ...threaded });
assert.match(lsf.script, /#BSUB -n 8/);
assert.match(lsf.script, /#BSUB -R "span\[ptile=8\]"/);
assert.match(lsf.script, /#BSUB -R "rusage\[mem=32768\]"/);
assert.match(lsf.script, /#BSUB -gpu "num=1"/);
assert.match(lsf.script, /#BSUB -W 24:00/);
assert.match(lsf.script, /bsub < submit\.sh/).not;

const sge = Scheduler.buildHeader({
  scheduler: 'sge', ...mpi, pe: 'mpi', gpus: 2, array: true, arrayRange: '1-10%3'
});
assert.match(sge.script, /#\$ -pe mpi 32/);
assert.match(sge.script, /#\$ -l h_rt=36:00:00/);
assert.match(sge.script, /#\$ -t 1-10/);
assert.match(sge.script, /#\$ -tc 3/);
assert.ok(sge.warnings.some(w => w.field === 'gpus' && /no standard GPU request/i.test(w.message)));

assert.throws(() => Scheduler.getScheduler('torque'), /Unknown scheduler/);

console.log('STEMKit multi-scheduler golden fixtures: ok');

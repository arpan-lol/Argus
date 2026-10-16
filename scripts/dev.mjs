import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const npmCli = process.env.npm_execpath;
if (!npmCli) throw new Error('Start the workspace with npm run dev.');

const children = ['backend', 'frontend'].map((directory) => spawn(process.execPath, [npmCli, '--prefix', directory, 'run', 'dev'], {
  cwd: root,
  stdio: 'inherit',
  env: process.env,
  windowsHide: true,
}));

let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (process.platform === 'win32' && child.pid) spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore', windowsHide: true });
    else child.kill();
  }
  process.exitCode = code;
}

for (const child of children) {
  child.on('error', (error) => { console.error(error.message); stop(1); });
  child.on('exit', (code) => stop(code ?? 0));
}
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());

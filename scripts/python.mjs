import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const venv = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const mode = process.argv[2] || 'dev';
if (mode === 'setup' && !existsSync(venv)) {
  const created = spawnSync(process.env.PYTHON || 'python', ['-m', 'venv', path.join(root, '.venv')], { cwd: root, stdio: 'inherit', windowsHide: true });
  if (created.error) throw created.error;
  if (created.status !== 0) process.exit(created.status ?? 1);
}
const python = existsSync(venv) ? venv : (process.env.PYTHON || 'python');
const commands = {
  dev: ['-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend/python', '--host', '127.0.0.1', '--port', '4000', '--reload', '--reload-dir', 'backend/python/app'],
  start: ['-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend/python', '--host', '127.0.0.1', '--port', '4000'],
  build: ['-m', 'compileall', '-q', 'backend/python/app', 'backend/python/scripts'],
  setup: ['-m', 'pip', 'install', '-r', 'backend/python/requirements.txt', '-r', 'backend/python/requirements-ingestion.txt'],
  migrate: ['backend/python/scripts/migrate_legacy.py'],
  ingest: ['scripts/python/ingest.py'],
};
if (!commands[mode]) throw new Error(`Unknown Python command: ${mode}`);
const child = spawn(python, [...commands[mode], ...process.argv.slice(3)], { cwd: root, stdio: 'inherit', windowsHide: true, env: process.env });
child.on('exit', code => { process.exitCode = code ?? 1; });
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill());

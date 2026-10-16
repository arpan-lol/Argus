import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { config } from '../config/env.js';

fs.mkdirSync(config.dataDir, { recursive: true });
const database = new DatabaseSync(path.join(config.dataDir, 'runs.sqlite'));
database.exec('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)');

export const runService = {
  save(run: { runId: string }) { database.prepare('INSERT OR REPLACE INTO runs(id,created_at,payload) VALUES(?,?,?)').run(run.runId, new Date().toISOString(), JSON.stringify(run)); },
  get(id: string) { const row = database.prepare('SELECT payload FROM runs WHERE id=?').get(id); return row ? JSON.parse(String(row.payload)) : null; },
  list() { return database.prepare('SELECT id,created_at FROM runs ORDER BY created_at DESC LIMIT 100').all(); },
};

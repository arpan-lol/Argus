import 'dotenv/config';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../../', import.meta.url));
export const config = {
  port: Number(process.env.PORT || 4000),
  host: process.env.HOST || '127.0.0.1',
  origin: process.env.FRONTEND_ORIGIN || 'http://localhost:3001',
  dataDir: process.env.DATA_DIR ? path.resolve(process.env.DATA_DIR) : path.join(root, 'data'),
  redisUrl: process.env.REDIS_URL || 'redis://127.0.0.1:6379',
  graphName: process.env.FALKOR_GRAPH || 'materials_evidence_v1',
};

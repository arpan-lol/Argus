import express from 'express';
import cors from 'cors';
import { config } from './config/env.js';
import evidenceRoutes from './routes/evidence.routes.js';
import { globalErrorHandler } from './middleware/errorHandler.js';
import { logger } from './utils/logger.util.js';
import { graphService } from './services/graph.service.js';

const app = express();
app.disable('x-powered-by');
app.use(cors({ origin: config.origin, methods: ['GET', 'POST'] }));
app.use(express.json({ limit: '128kb' }));
app.use('/api', evidenceRoutes);
app.use((_req, res) => { res.status(404).json({ error: 'Endpoint not found' }); });
app.use(globalErrorHandler);
app.listen(config.port, config.host, () => {
  logger.info('server', `Listening on http://${config.host}:${config.port}`);
  void graphService.ensure();
});

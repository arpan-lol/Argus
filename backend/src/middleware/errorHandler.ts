import type { ErrorRequestHandler } from 'express';
import { AppError } from '../types/errors.js';
import { logger } from '../utils/logger.util.js';

export const globalErrorHandler: ErrorRequestHandler = (error, req, res, next) => {
  logger.error('GlobalErrorHandler', 'Request failed', error, { url: req.path, method: req.method });
  if (res.headersSent) { next(error); return; }
  const status = error instanceof AppError ? error.statusCode : error.type === 'entity.parse.failed' ? 400 : error.type === 'entity.too.large' ? 413 : 500;
  res.status(status).json({ error: error instanceof AppError && error.shouldExposeToClient ? error.clientMessage || error.message : status === 400 ? 'Invalid JSON request' : 'Request could not be completed. Inspect backend logs for details.' });
};

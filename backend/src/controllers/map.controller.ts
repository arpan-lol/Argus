import type { Request, Response } from 'express';
import { mapService, type MapMode } from '../services/map.service.js';
import { AppError } from '../types/errors.js';

const modeFor = (req: Request): MapMode => {
  const mode = req.query.mode;
  if (mode === undefined) return 'network';
  if (mode !== 'network' && mode !== 'grouped') throw new AppError('Map mode must be network or grouped', 400, true);
  return mode;
};

export const mapController = {
  overview(req: Request, res: Response) { res.json(mapService.overview(modeFor(req))); },
  async view(req: Request, res: Response) {
    const values = ['minX', 'minY', 'maxX', 'maxY', 'zoom'].map(key => Number(req.query[key]));
    if (values.some(value => !Number.isFinite(value))) throw new AppError('Finite viewport bounds and zoom are required', 400, true);
    const [minX, minY, maxX, maxY, zoom] = values;
    if (minX >= maxX || minY >= maxY || zoom <= 0 || maxX - minX > 1000000 || maxY - minY > 1000000) throw new AppError('Invalid source map viewport', 400, true);
    const rawLimit = Number(req.query.limit || 800);
    res.json(await mapService.view({ minX, minY, maxX, maxY }, zoom, Number.isFinite(rawLimit) ? rawLimit : 800, modeFor(req)));
  },
  locate(req: Request, res: Response) { res.json(mapService.locate(String(req.params.id), modeFor(req))); },
  async node(req: Request, res: Response) { res.json(await mapService.node(String(req.params.id), modeFor(req))); },
  async neighborhood(req: Request, res: Response) { res.json(await mapService.neighborhood(String(req.params.id), modeFor(req))); },
};

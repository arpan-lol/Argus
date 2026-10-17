import type { Request, Response } from 'express';
import { mapService } from '../services/map.service.js';
import { AppError } from '../types/errors.js';

export const mapController = {
  overview(_req: Request, res: Response) { res.json(mapService.overview()); },
  async view(req: Request, res: Response) {
    const values = ['minX', 'minY', 'maxX', 'maxY', 'zoom'].map(key => Number(req.query[key]));
    if (values.some(value => !Number.isFinite(value))) throw new AppError('Finite viewport bounds and zoom are required', 400, true);
    const [minX, minY, maxX, maxY, zoom] = values;
    if (minX >= maxX || minY >= maxY || zoom <= 0 || maxX - minX > 1000000 || maxY - minY > 1000000) throw new AppError('Invalid source map viewport', 400, true);
    const rawLimit = Number(req.query.limit || 800);
    res.json(await mapService.view({ minX, minY, maxX, maxY }, zoom, Number.isFinite(rawLimit) ? rawLimit : 800));
  },
  locate(req: Request, res: Response) { res.json(mapService.locate(String(req.params.id))); },
  async node(req: Request, res: Response) { res.json(await mapService.node(String(req.params.id))); },
  async neighborhood(req: Request, res: Response) { res.json(await mapService.neighborhood(String(req.params.id))); },
};

import { api } from './evidence-types';

export interface Project {
  id: string;
  name: string;
  description: string;
  categories?: string[];
  configurationLocked?: boolean;
  files?: number;
  published?: number;
  entity_types: string[];
  relationship_types: string[];
  lastEventSequence?: number;
}

export interface ProcessingEvent {
  sequence: number;
  type: string;
  jobId?: string;
  stage?: string;
  filename?: string;
  at?: string;
  attempt?: number;
  itemId?: string;
  message?: string;
  status?: string;
  kind?: string;
  model?: string;
  durationMs?: number;
  rateWaitSeconds?: number;
  counts?: Record<string, number>;
  usage?: { input_tokens?: number; output_tokens?: number; total_tokens?: number; prompt_tokens?: number; completion_tokens?: number };
}

export const projectRoot = (id: string) => `/projects/${encodeURIComponent(id)}`;

export function projectApi<T>(id: string, path: string, init?: RequestInit) {
  return api<T>(projectRoot(id) + path, init);
}

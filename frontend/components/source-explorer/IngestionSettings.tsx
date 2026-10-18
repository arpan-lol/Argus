'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/evidence-types';
import type { IngestionJob } from '@/lib/ingestion-types';
import './IngestionSetup.css';

interface Settings {
  entityTypes: string[];
  relationshipTypes: string[];
  extractionInstructions: string;
  rationale?: string;
  sampling?: { sampledDocuments?: number; availableDocuments?: number; excluded?: unknown[]; callsThisRun?: number; startWindowSeconds?: number; tokenBudget?: number; stopReason?: string };
}

interface Profile {
  prompt?: string;
  status?: string;
  settings?: Settings | null;
  sampling?: Settings['sampling'];
  tokensReserved?: number;
}

export function IngestionSettings({ job, apiRoot = '' }: { job: IngestionJob; apiRoot?: string }) {
  const [open, setOpen] = useState(false);
  const [profile, setProfile] = useState<Profile>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const stage = job.stages.find(stage => stage.name === 'configure');
  const profileId = job.configuration?.corpusProfileId || stage?.metadata?.profileId;
  const ready = ['complete', 'completed', 'succeeded'].includes(stage?.status || '');

  useEffect(() => {
    if (!open) return;
    let active = true;
    setError('');
    if (!profileId && !ready) {
      setProfile(undefined);
      return;
    }
    setLoading(true);
    const request = profileId
      ? api<Profile>(`${apiRoot}/ingestion/profiles/${encodeURIComponent(profileId)}`)
      : api<Settings>(`${apiRoot}/ingestion/jobs/${encodeURIComponent(job.id)}/artifacts/configure`).then(settings => ({ settings }));
    request.then(result => { if (active) setProfile(result); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Could not load settings. Try again.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, job.id, profileId, ready, refresh, apiRoot]);

  const settings = profile?.settings;
  const sampling = profile?.sampling || settings?.sampling;
  return <details className="ce-ingestion-settings" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Extraction settings</summary>
    {open && <div className="ce-ingestion-settings-content" aria-busy={loading}>
      {loading ? <p role="status">Loading settings…</p> : error ? <><p role="alert">{error}</p><button onClick={() => setRefresh(value => value + 1)}>Try again</button></> : <>
        {profile?.prompt && <><strong>Your instructions</strong><p>{profile.prompt}</p></>}
        {settings ? <>
          <dl><div><dt>Entity types</dt><dd>{settings.entityTypes.join(', ')}</dd></div><div><dt>Relationship types</dt><dd>{settings.relationshipTypes.length ? settings.relationshipTypes.join(', ') : 'Any relationship explicitly stated in the source'}</dd></div><div><dt>Extraction scope</dt><dd>{settings.extractionInstructions}</dd></div></dl>
          {settings.rationale && <><strong>Why these settings</strong><p>{settings.rationale}</p></>}
          {sampling?.sampledDocuments != null && <p>Based on {sampling.sampledDocuments.toLocaleString()} sampled {sampling.sampledDocuments === 1 ? 'file' : 'files'}{sampling.availableDocuments != null ? ` from ${sampling.availableDocuments.toLocaleString()}` : ''}.{sampling.excluded?.length ? ` ${sampling.excluded.length.toLocaleString()} could not be sampled.` : ''} These settings apply automatically.</p>}
          {sampling?.startWindowSeconds != null && <p>Label discovery starts calls for up to {sampling.startWindowSeconds} seconds; an active response can finish afterward. {sampling.callsThisRun ?? 0} calls started.{sampling.tokenBudget != null && ` Workspace token budget: ${sampling.tokenBudget.toLocaleString()}.`}{profile?.tokensReserved != null && ` Reserved: ${profile.tokensReserved.toLocaleString()} tokens, including response allowance. Reported usage appears in notifications.`}</p>}
        </> : <p>Argus starts with your selected document categories, then samples source text to discover additional entity and relationship types.</p>}
      </>}
    </div>}
  </details>;
}

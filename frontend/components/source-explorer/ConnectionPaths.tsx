'use client';

import { ArrowUpRight, Loader2, X } from 'lucide-react';
import styles from './ConnectionPaths.module.css';

export type ConnectionPath = {
  sourceChunkId: string;
  targetChunkId: string;
  entityId: string;
  label: string;
  documentId: string;
  documentTitle: string;
};

type Props = {
  paths: ConnectionPath[];
  loading: boolean;
  error?: string | null;
  truncated?: boolean;
  activeTargetChunkId?: string;
  onFollow: (path: ConnectionPath) => void;
  onClose: () => void;
};

export function ConnectionPaths({ paths, loading, error, truncated, activeTargetChunkId, onFollow, onClose }: Props) {
  const documentIds = new Set<string>();
  const visible = paths.filter((path) => {
    if (documentIds.has(path.documentId)) return false;
    documentIds.add(path.documentId);
    return true;
  }).slice(0, 3);

  return (
    <section className={styles.panel} aria-label="Shared connections" aria-busy={loading}>
      <header className={styles.header}>
        <h3>Shared connections</h3>
        <button type="button" className={styles.close} aria-label="Close shared connections" onClick={onClose}>
          <X size={15} aria-hidden="true" />
        </button>
      </header>
      <div className={styles.body}>
        {loading ? (
          <p className={styles.status} role="status"><Loader2 size={15} className={styles.spin} aria-hidden="true" /> Finding related chunks…</p>
        ) : error ? (
          <p className={styles.status} role="alert">Connections could not load. Select the chunk again to retry.</p>
        ) : visible.length ? (
          <ul className={styles.list}>
            {visible.map((path) => (
              <li key={`${path.sourceChunkId}:${path.targetChunkId}:${path.entityId}`}>
                <button type="button" className={styles.path} onClick={() => onFollow(path)} aria-pressed={activeTargetChunkId === path.targetChunkId} aria-label={`Show connection to ${path.documentTitle}`} title="Show connection">
                  <span className={styles.copy}>
                    <span className={styles.term}>Both chunks mention <strong>{path.label}</strong></span>
                    <span className={styles.document}>{path.documentTitle}</span>
                  </span>
                  <ArrowUpRight size={15} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.status}>No shared mentions with other documents were found for this chunk.</p>
        )}
        {!loading && !error && visible.length > 0 && (
          <footer className={styles.footer}>
            {(truncated || paths.length > visible.length) && <p>Showing a selection of connections.</p>}
            <p>Shared mentions do not imply agreement.</p>
          </footer>
        )}
      </div>
    </section>
  );
}

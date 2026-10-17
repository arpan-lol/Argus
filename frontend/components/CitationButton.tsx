import { FileText } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CitationButtonProps {
  citation: { chunkId?: string; documentTitle: string; sectionTitle: string };
  index: number;
  onCitationClick: () => void;
  selected?: boolean;
}

export function CitationButton({ citation, index, onCitationClick, selected }: CitationButtonProps) {
  return <button type="button" className={cn('citation-button', selected && 'selected')} onClick={onCitationClick}
    title={`${citation.documentTitle} · ${citation.sectionTitle}`} aria-label={`Inspect citation ${index}: ${citation.sectionTitle}`}>
    <FileText size={12} aria-hidden="true" /><span>{index} · {citation.sectionTitle || 'Source passage'}</span>
  </button>;
}

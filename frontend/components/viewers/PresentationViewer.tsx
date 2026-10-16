'use client';

import { Button } from '@/components/ui/button';
import { Download, FileX } from 'lucide-react';

interface PresentationViewerProps {
  fileUrl: string;
  filename: string;
}

export default function PresentationViewer({ fileUrl, filename }: PresentationViewerProps) {
  const handleDownload = async () => {
    try {
      const response = await fetch(fileUrl, { credentials: 'omit' });
      if (!response.ok) throw new Error('Failed to download file');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-4">
      <FileX className="h-16 w-16 mb-4 opacity-50" />
      <p className="text-sm mb-2">Presentation files cannot be previewed directly</p>
      <p className="text-xs text-muted-foreground mb-4">Download the file to view it</p>
      <Button onClick={handleDownload} variant="outline">
        <Download className="h-4 w-4 mr-2" />
        Download {filename}
      </Button>
    </div>
  );
}

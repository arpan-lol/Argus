'use client';

import { useState, useEffect } from 'react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Copy, Download, Loader2 } from 'lucide-react';


interface TextViewerProps {
  fileUrl: string;
  filename: string;
}

export default function TextViewer({ fileUrl, filename }: TextViewerProps) {
  const [copyStatus, setCopyStatus] = useState('Copy');
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchContent = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(fileUrl, { credentials: 'omit' });
        if (!response.ok) throw new Error('Failed to load file');
        const text = await response.text();
        setContent(text);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load file');
      } finally {
        setLoading(false);
      }
    };

    fetchContent();
  }, [fileUrl]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopyStatus('Copied');
    } catch {
      setCopyStatus('Copy failed');
    }
  };

  const handleDownload = () => {
    const link = document.createElement('a');
    link.href = fileUrl;
    link.download = filename;
    link.click();
  };

  const isJSON = filename.toLowerCase().endsWith('.json');

  let displayContent = content;
  if (isJSON && content) {
    try {
      const parsed = JSON.parse(content);
      displayContent = JSON.stringify(parsed, null, 2);
    } catch {
      displayContent = content;
    }
  }

  return (
    <div className="flex flex-col h-full relative">
      {loading && (
        <div className="flex items-center justify-center h-full">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      )}
      {error && (
        <div className="flex items-center justify-center h-full text-destructive">
          <p>{error}</p>
        </div>
      )}
      {!loading && !error && (
        <>
          <ScrollArea className="flex-1 bg-muted/30 rounded-lg p-4">
            <pre className="text-sm font-mono whitespace-pre-wrap break-words">
              {displayContent}
            </pre>
          </ScrollArea>
          <Card className="absolute bottom-4 left-1/2 transform -translate-x-1/2 p-3 flex items-center gap-2 z-10">
            <Button onClick={handleCopy} size="sm" variant="outline">
              <Copy className="h-4 w-4 mr-2" />
              {copyStatus}
            </Button>
            <Button onClick={handleDownload} size="sm" variant="outline">
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
          </Card>
        </>
      )}
    </div>
  );
}

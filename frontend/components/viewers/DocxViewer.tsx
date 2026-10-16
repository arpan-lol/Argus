'use client';

import { useState, useEffect } from 'react';
import mammoth from 'mammoth';
import DOMPurify from 'dompurify';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Download, Loader2 } from 'lucide-react';

interface DocxViewerProps {
  fileUrl: string;
  filename: string;
}

export default function DocxViewer({ fileUrl, filename }: DocxViewerProps) {
  const [htmlContent, setHtmlContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadDocx = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(fileUrl, { credentials: 'omit' });
        if (!response.ok) throw new Error('Failed to load document');
        
        const arrayBuffer = await response.arrayBuffer();
        const result = await mammoth.convertToHtml({ arrayBuffer });
        setHtmlContent(DOMPurify.sanitize(result.value, { USE_PROFILES: { html: true } }));

        if (result.messages.length > 0) {
          console.warn('[DocxViewer] Conversion warnings:', result.messages);
        }
      } catch (err) {
        console.error('[DocxViewer] Error:', err);
        setError(err instanceof Error ? err.message : 'Failed to load document');
      } finally {
        setLoading(false);
      }
    };

    loadDocx();
  }, [fileUrl]);

  const handleDownload = () => {
    const link = document.createElement('a');
    link.href = fileUrl;
    link.download = filename;
    link.click();
  };

  return (
    <div className="flex flex-col h-full relative">
      {loading && (
        <div className="flex items-center justify-center h-full">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      )}
      {error && (
        <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
          <p className="mb-4">{error}</p>
          <Button onClick={handleDownload} variant="outline">
            <Download className="h-4 w-4 mr-2" />
            Download to view
          </Button>
        </div>
      )}
      {!loading && !error && (
        <>
          <div className="flex-1 overflow-auto bg-white dark:bg-muted/30 rounded-lg p-6">
            <div 
              className="prose prose-sm dark:prose-invert max-w-none"
              style={{
                fontFamily: 'system-ui, -apple-system, sans-serif',
                lineHeight: '1.6',
                color: 'inherit'
              }}
              dangerouslySetInnerHTML={{ __html: htmlContent }}
            />
            <style jsx global>{`
              .prose p { margin-bottom: 1em; }
              .prose h1 { font-size: 2em; font-weight: bold; margin: 0.67em 0; }
              .prose h2 { font-size: 1.5em; font-weight: bold; margin: 0.75em 0; }
              .prose h3 { font-size: 1.17em; font-weight: bold; margin: 0.83em 0; }
              .prose ul, .prose ol { margin: 1em 0; padding-left: 2em; }
              .prose li { margin: 0.5em 0; }
              .prose strong { font-weight: bold; }
              .prose em { font-style: italic; }
              .prose a { color: #0066cc; text-decoration: underline; }
              .prose table { border-collapse: collapse; width: 100%; margin: 1em 0; }
              .prose td, .prose th { border: 1px solid #ddd; padding: 8px; }
              .prose th { background-color: #f5f5f5; font-weight: bold; }
            `}</style>
          </div>
          <Card className="absolute bottom-4 left-1/2 transform -translate-x-1/2 p-3 flex items-center gap-2 z-10">
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

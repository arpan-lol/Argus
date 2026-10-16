'use client';

import { useState, useEffect } from 'react';
import * as XLSX from 'xlsx';
import DOMPurify from 'dompurify';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Download, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

interface SpreadsheetViewerProps {
  fileUrl: string;
  filename: string;
}

export default function SpreadsheetViewer({ fileUrl, filename }: SpreadsheetViewerProps) {
  const [workbook, setWorkbook] = useState<XLSX.WorkBook | null>(null);
  const [currentSheetIndex, setCurrentSheetIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadSpreadsheet = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(fileUrl, { credentials: 'omit' });
        if (!response.ok) throw new Error('Failed to load spreadsheet');
        
        const arrayBuffer = await response.arrayBuffer();
        const workbook = XLSX.read(arrayBuffer, { type: 'array' });
        setWorkbook(workbook);
      } catch (err) {
        console.error('[SpreadsheetViewer] Error:', err);
        setError(err instanceof Error ? err.message : 'Failed to load spreadsheet');
      } finally {
        setLoading(false);
      }
    };

    loadSpreadsheet();
  }, [fileUrl]);

  const handleDownload = () => {
    const link = document.createElement('a');
    link.href = fileUrl;
    link.download = filename;
    link.click();
  };

  const nextSheet = () => {
    if (workbook && currentSheetIndex < workbook.SheetNames.length - 1) {
      setCurrentSheetIndex(currentSheetIndex + 1);
    }
  };

  const prevSheet = () => {
    if (currentSheetIndex > 0) {
      setCurrentSheetIndex(currentSheetIndex - 1);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (error || !workbook) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <p className="mb-4">{error || 'Failed to load spreadsheet'}</p>
        <Button onClick={handleDownload} variant="outline">
          <Download className="h-4 w-4 mr-2" />
          Download to view
        </Button>
      </div>
    );
  }

  const currentSheet = workbook.Sheets[workbook.SheetNames[currentSheetIndex]];
  const htmlTable = DOMPurify.sanitize(XLSX.utils.sheet_to_html(currentSheet, { header: '', footer: '' }), { USE_PROFILES: { html: true } });

  return (
    <div className="flex flex-col h-full relative">
      <ScrollArea className="flex-1 bg-white dark:bg-muted/30 rounded-lg p-4">
        <div className="mb-4 flex items-center gap-2">
          <Badge variant="secondary">{workbook.SheetNames[currentSheetIndex]}</Badge>
          {workbook.SheetNames.length > 1 && (
            <span className="text-xs text-muted-foreground">
              Sheet {currentSheetIndex + 1} of {workbook.SheetNames.length}
            </span>
          )}
        </div>
        <div 
          className="overflow-auto"
          dangerouslySetInnerHTML={{ __html: htmlTable }}
          style={{
            '--table-border': '1px solid hsl(var(--border))',
            '--table-bg': 'hsl(var(--background))',
          } as React.CSSProperties}
        />
        <style jsx>{`
          :global(table) {
            border-collapse: collapse;
            width: 100%;
            font-size: 0.875rem;
          }
          :global(table td, table th) {
            border: var(--table-border);
            padding: 0.5rem;
            text-align: left;
          }
          :global(table th) {
            background-color: hsl(var(--muted));
            font-weight: 600;
          }
          :global(table tr:nth-child(even)) {
            background-color: hsl(var(--muted) / 0.3);
          }
        `}</style>
      </ScrollArea>
      <Card className="absolute bottom-4 left-1/2 transform -translate-x-1/2 p-3 flex items-center gap-2 z-10">
        {workbook.SheetNames.length > 1 && (
          <>
            <Button 
              onClick={prevSheet} 
              disabled={currentSheetIndex === 0}
              size="sm" 
              variant="outline"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm min-w-[80px] text-center">
              {currentSheetIndex + 1} / {workbook.SheetNames.length}
            </span>
            <Button 
              onClick={nextSheet} 
              disabled={currentSheetIndex === workbook.SheetNames.length - 1}
              size="sm" 
              variant="outline"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </>
        )}
        <Button onClick={handleDownload} size="sm" variant="outline">
          <Download className="h-4 w-4 mr-2" />
          Download
        </Button>
      </Card>
    </div>
  );
}

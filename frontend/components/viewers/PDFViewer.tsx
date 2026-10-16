'use client';

import { useState, useEffect, useMemo } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Loader2 } from 'lucide-react';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdf.worker.min.mjs';

const SCALE_MIN = 0.5;
const SCALE_MAX = 3.0;
const SCALE_STEP = 0.2;
const SCALE_DEFAULT = 1.0;

interface PDFViewerProps {
  fileUrl: string;
  currentPage: number;
  onPageChange: (pageNumber: number) => void;
}

async function loadPDFWithCredentials(url: string) {
  const response = await fetch(url, {
    credentials: 'omit',
  });
  
  if (!response.ok) {
    throw new Error(`Failed to load PDF: ${response.status} ${response.statusText}`);
  }
  
  return response.arrayBuffer();
}

export default function PDFViewer({ fileUrl, currentPage, onPageChange }: PDFViewerProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [scale, setScale] = useState<number>(SCALE_DEFAULT);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfData, setPdfData] = useState<Uint8Array | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setNumPages(0);
    setPdfData(null);
    
    loadPDFWithCredentials(fileUrl)
      .then((arrayBuffer) => {
        const uint8Array = new Uint8Array(arrayBuffer);
        setPdfData(uint8Array);
      })
      .catch((err) => {
        console.error('[PDFViewer] Failed to load PDF:', err);
        setError(err.message || 'Failed to load PDF');
        setLoading(false);
      });
  }, [fileUrl]);

  useEffect(() => {
    if (numPages > 0 && currentPage > numPages) {
      onPageChange(numPages);
    } else if (numPages > 0 && currentPage < 1) {
      onPageChange(1);
    }
  }, [numPages, currentPage, onPageChange]);

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages);
    setLoading(false);
    setError(null);
  }

  function onDocumentLoadError(err: Error) {
    console.error('[PDFViewer] Load error:', err);
    setError(err.message || 'Failed to load PDF');
    setLoading(false);
  }

  function previousPage() {
    if (currentPage > 1) {
      onPageChange(currentPage - 1);
    }
  }

  function nextPage() {
    if (currentPage < numPages) {
      onPageChange(currentPage + 1);
    }
  }

  function zoomIn() {
    setScale((prev) => Math.min(prev + SCALE_STEP, SCALE_MAX));
  }

  function zoomOut() {
    setScale((prev) => Math.max(prev - SCALE_STEP, SCALE_MIN));
  }

  const fileObject = useMemo(() => pdfData ? { data: pdfData } : null, [pdfData]);

  return (
    <div className="flex flex-col h-full relative">
      <div className="flex-1 overflow-auto bg-muted/30 rounded-lg p-4 flex items-center justify-center">
        {loading && !error && (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        )}
        {error && (
          <div className="flex flex-col items-center justify-center h-full text-destructive">
            <p className="text-sm mb-4">{error}</p>
            <Button onClick={() => window.location.reload()} variant="outline" size="sm">
              Retry
            </Button>
          </div>
        )}
        {!error && fileObject && (
          <Document
            file={fileObject}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
          >
            <Page
              pageNumber={Math.max(1, Math.min(currentPage, numPages || 1))}
              scale={scale}
              renderTextLayer={true}
              renderAnnotationLayer={true}
              className="shadow-lg"
              width={520}
            />
          </Document>
        )}
      </div>
      <Card className="absolute bottom-4 left-1/2 transform -translate-x-1/2 p-3 flex items-center justify-between w-auto z-20">
        <div className="flex items-center gap-2">
          <Button
            onClick={previousPage}
            disabled={currentPage <= 1}
            size="sm"
            variant="outline"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm">
            Page {currentPage} of {numPages || '...'}
          </span>
          <Button
            onClick={nextPage}
            disabled={currentPage >= numPages}
            size="sm"
            variant="outline"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={zoomOut} size="sm" variant="outline">
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="text-sm min-w-[60px] text-center">
            {Math.round(scale * 100)}%
          </span>
          <Button onClick={zoomIn} size="sm" variant="outline">
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </Card>
    </div>
  );
}

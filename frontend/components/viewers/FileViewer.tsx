'use client';

import dynamic from 'next/dynamic';
import { Button } from '@/components/ui/button';
import { Download, FileX } from 'lucide-react';

const PDFViewer = dynamic(() => import('./PDFViewer'), {
  ssr: false,
  loading: () => <div>Loading PDF...</div>,
});

const ImageViewer = dynamic(() => import('./ImageViewer'), {
  ssr: false,
  loading: () => <div>Loading image...</div>,
});

const TextViewer = dynamic(() => import('./TextViewer'), {
  ssr: false,
  loading: () => <div>Loading text...</div>,
});

const DocxViewer = dynamic(() => import('./DocxViewer'), {
  ssr: false,
  loading: () => <div>Loading document...</div>,
});

const SpreadsheetViewer = dynamic(() => import('./SpreadsheetViewer'), {
  ssr: false,
  loading: () => <div>Loading spreadsheet...</div>,
});

const PresentationViewer = dynamic(() => import('./PresentationViewer'), {
  ssr: false,
  loading: () => <div>Loading presentation...</div>,
});

interface FileViewerProps {
  fileUrl: string;
  filename: string;
  fileType: string;
  currentPage?: number;
  onPageChange?: (page: number) => void;
}

function getFileTypeFromFilename(filename: string): string {
  const ext = filename.toLowerCase().split('.').pop() || '';
  
  if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return 'image';
  if (ext === 'pdf') return 'pdf';
  if (ext === 'docx') return 'document';
  if (['xls', 'xlsx', 'csv'].includes(ext)) return 'spreadsheet';
  if (['ppt', 'pptx'].includes(ext)) return 'presentation';
  if (['txt', 'json', 'jsonl', 'md', 'mdx', 'xml', 'html', 'log', 'py', 'pyi', 'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'css', 'scss', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'sql', 'sh', 'go', 'rs', 'java', 'kt', 'c', 'h', 'cpp', 'hpp', 'cs', 'rb', 'php', 'swift', 'r', 'ipynb'].includes(ext)) return 'text';
  
  return 'unknown';
}

export default function FileViewer({ fileUrl, filename, fileType, currentPage = 1, onPageChange }: FileViewerProps) {
  const detectedType = getFileTypeFromFilename(filename);
  const type = detectedType !== 'unknown' ? detectedType : fileType;

  const handleDownload = () => {
    const link = document.createElement('a');
    link.href = fileUrl;
    link.download = filename;
    link.click();
  };

  if (type === 'pdf') {
    return (
      <PDFViewer
        fileUrl={fileUrl}
        currentPage={currentPage}
        onPageChange={onPageChange || (() => {})}
      />
    );
  }

  if (type === 'image') {
    return <ImageViewer fileUrl={fileUrl} filename={filename} />;
  }

  if (type === 'text') {
    return <TextViewer fileUrl={fileUrl} filename={filename} />;
  }

  if (type === 'document') {
    return <DocxViewer fileUrl={fileUrl} filename={filename} />;
  }

  if (type === 'spreadsheet') {
    return <SpreadsheetViewer fileUrl={fileUrl} filename={filename} />;
  }

  if (type === 'presentation') {
    return <PresentationViewer fileUrl={fileUrl} filename={filename} />;
  }

  return (
    <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
      <FileX className="h-16 w-16 mb-4 opacity-50" />
      <p className="text-sm mb-4">This file type cannot be previewed</p>
      <Button onClick={handleDownload} variant="outline">
        <Download className="h-4 w-4 mr-2" />
        Download file
      </Button>
    </div>
  );
}

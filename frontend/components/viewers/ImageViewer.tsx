'use client';

import { useState, useEffect } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ZoomIn, ZoomOut, Maximize2, Loader2 } from 'lucide-react';
import Image from 'next/image';

interface ImageViewerProps {
  fileUrl: string;
  filename: string;
}

export default function ImageViewer({ fileUrl, filename }: ImageViewerProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let objectUrl: string | null = null;

    const loadImage = async () => {
      try {
        const response = await fetch(fileUrl, { credentials: 'omit' });
        if (!response.ok) throw new Error('Failed to load image');
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      } catch (err) {
        console.error('[ImageViewer] Error:', err);
      } finally {
        setLoading(false);
      }
    };
    loadImage();
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [fileUrl]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (!blobUrl) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        Failed to load image
      </div>
    );
  }
  return (
    <div className="flex flex-col h-full relative">
      <TransformWrapper
        initialScale={1}
        minScale={0.5}
        maxScale={4}
        centerOnInit
      >
        {({ zoomIn, zoomOut, resetTransform }) => (
          <>
            <div className="flex-1 overflow-hidden bg-muted/30 rounded-lg flex items-center justify-center">
              <TransformComponent
                wrapperClass="w-full h-full flex items-center justify-center"
                contentClass="w-full h-full flex items-center justify-center"
              >
                <div className="relative w-full h-full min-h-[320px]">
                  <Image
                    src={blobUrl}
                    alt={filename}
                    fill
                    unoptimized
                    sizes="100vw"
                    className="object-contain"
                    priority
                  />
                </div>
              </TransformComponent>
            </div>
            <Card className="absolute bottom-4 left-1/2 transform -translate-x-1/2 p-3 flex flex-row items-center gap-2 z-10">
              <Button onClick={() => zoomOut()} size="sm" variant="outline">
                <ZoomOut className="h-4 w-4" />
              </Button>
              <Button onClick={() => zoomIn()} size="sm" variant="outline">
                <ZoomIn className="h-4 w-4" />
              </Button>
              <Button onClick={() => resetTransform()} size="sm" variant="outline">
                <Maximize2 className="h-4 w-4" />
              </Button>
            </Card>
          </>
        )}
      </TransformWrapper>
    </div>
  );
}

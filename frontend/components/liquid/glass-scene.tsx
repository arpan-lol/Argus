'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { GlassConfig, LiquidGlass } from '@ybouane/liquidglass';
import './glass-scene.css';

type SceneVariant = 'workspace' | 'projects';

interface Surface {
  key: string;
  left: number;
  top: number;
  width: number;
  height: number;
  radius: number;
}

const BACKDROP_FPS = 20;
const BACKDROP_AREA = 1_400_000;
const DEFAULT_RADIUS: Record<SceneVariant, number> = { workspace: 20, projects: 30 };

const VARIANT_DEFAULTS: Record<SceneVariant, Partial<GlassConfig>> = {
  workspace: {
    cornerRadius: 20,
    zRadius: 30,
    refraction: 0.78,
    chromAberration: 0.045,
    edgeHighlight: 0.09,
    blurAmount: 0.3,
    saturation: 0.06,
    tintStrength: 0.1,
    brightness: 0.01,
    specular: 0.12,
    fresnel: 0.9,
    shadowOpacity: 0.3,
    shadowSpread: 16,
    shadowOffsetY: 6,
  },
  projects: {
    cornerRadius: 30,
    zRadius: 34,
    refraction: 0.82,
    chromAberration: 0.05,
    edgeHighlight: 0.1,
    blurAmount: 0.18,
    saturation: 0.08,
    tintStrength: 0.08,
    brightness: 0.01,
    specular: 0.14,
    fresnel: 1,
    shadowOpacity: 0.26,
    shadowSpread: 18,
    shadowOffsetY: 8,
  },
};

const BACKDROP_PALETTES = {
  light: { base: '#eceee7', blobs: [[255, 208, 97], [169, 196, 221], [233, 194, 184], [188, 215, 198]] },
  dark: { base: '#141619', blobs: [[125, 95, 32], [46, 74, 99], [90, 63, 75], [47, 82, 69]] },
};

function paintBackdrop(canvas: HTMLCanvasElement, width: number, height: number, time: number, dark: boolean) {
  const context = canvas.getContext('2d');
  if (!context || width < 2 || height < 2) return;
  const scale = Math.min(window.devicePixelRatio || 1, 1.5) * Math.min(1, Math.sqrt(BACKDROP_AREA / (width * height)));
  const pixelWidth = Math.max(2, Math.round(width * scale));
  const pixelHeight = Math.max(2, Math.round(height * scale));
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  context.setTransform(pixelWidth / width, 0, 0, pixelHeight / height, 0, 0);
  const palette = dark ? BACKDROP_PALETTES.dark : BACKDROP_PALETTES.light;
  context.fillStyle = palette.base;
  context.fillRect(0, 0, width, height);
  const reach = Math.max(width, height);
  palette.blobs.forEach((rgb, index) => {
    const speed = 0.02 + index * 0.006;
    const phase = index * 1.9;
    const drift = 0.5 + Math.cos(time * speed + phase) * 0.3 + Math.sin(time * speed * 0.7 + phase * 1.3) * 0.08;
    const lift = 0.5 + Math.sin(time * speed * 0.8 + phase) * 0.3;
    const centerX = width * (index % 2 ? drift : 1 - drift);
    const centerY = height * lift;
    const radius = reach * (0.34 + (index % 3) * 0.05);
    const gradient = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);
    gradient.addColorStop(0, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${dark ? 0.6 : 0.48})`);
    gradient.addColorStop(1, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0)`);
    context.fillStyle = gradient;
    context.beginPath();
    context.arc(centerX, centerY, radius, 0, Math.PI * 2);
    context.fill();
  });
}

function sameSurfaces(previous: Surface[], next: Surface[]): boolean {
  if (previous.length !== next.length) return false;
  return previous.every((surface, index) => {
    const other = next[index];
    return surface.key === other.key && surface.left === other.left && surface.top === other.top && surface.width === other.width && surface.height === other.height;
  });
}

export function GlassScene({ variant }: { variant: SceneVariant }) {
  const sceneRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const instanceRef = useRef<LiquidGlass | null>(null);
  const [surfaces, setSurfaces] = useState<Surface[]>([]);

  const measure = useCallback(() => {
    const scene = sceneRef.current;
    const scope = scene?.parentElement;
    if (!scene || !scope) return;
    const sceneRect = scene.getBoundingClientRect();
    const found: Surface[] = [];
    scope.querySelectorAll<HTMLElement>('[data-glass-anchor]').forEach(element => {
      const rect = element.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) return;
      found.push({
        key: element.dataset.glassAnchor || 'surface',
        left: Math.round(rect.left - sceneRect.left),
        top: Math.round(rect.top - sceneRect.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        radius: Number(element.dataset.glassRadius) || DEFAULT_RADIUS[variant],
      });
    });
    setSurfaces(previous => (sameSurfaces(previous, found) ? previous : found));
  }, [variant]);

  useEffect(() => {
    const scene = sceneRef.current;
    const scope = scene?.parentElement;
    if (!scene || !scope) return;
    let frame = 0;
    const observer = new ResizeObserver(() => schedule());
    const run = () => {
      observer.disconnect();
      observer.observe(scene);
      scope.querySelectorAll<HTMLElement>('[data-glass-anchor]').forEach(element => observer.observe(element));
      measure();
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(run);
    };
    const mutations = new MutationObserver(schedule);
    mutations.observe(scope, { childList: true, subtree: true, attributeFilter: ['data-glass-anchor', 'data-glass-radius'] });
    window.addEventListener('resize', schedule);
    void document.fonts.ready.then(schedule);
    schedule();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      mutations.disconnect();
      window.removeEventListener('resize', schedule);
    };
  }, [measure]);

  const surfaceKey = surfaces.map(surface => surface.key).sort().join('|');

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !surfaces.length) return;
    let cancelled = false;
    let instance: LiquidGlass | null = null;
    void (async () => {
      try {
        const { LiquidGlass: LiquidGlassClass } = await import('@ybouane/liquidglass');
        if (cancelled) return;
        const elements = Array.from(scene.querySelectorAll<HTMLElement>(':scope > .lg-surface'));
        instance = await LiquidGlassClass.init({ root: scene, glassElements: elements, defaults: VARIANT_DEFAULTS[variant] });
        if (cancelled) { instance.destroy(); return; }
        instanceRef.current = instance;
        scene.classList.add('lg-live');
        scene.classList.remove('lg-fallback');
        if (canvasRef.current) instance.markChanged(canvasRef.current);
      } catch (error) {
        console.warn('Argus: liquid glass unavailable, using CSS fallback.', error);
        scene.classList.add('lg-fallback');
        scene.classList.remove('lg-live');
      }
    })();
    return () => {
      cancelled = true;
      instance?.destroy();
      if (instanceRef.current === instance) instanceRef.current = null;
      scene.classList.remove('lg-live');
    };
  }, [variant, surfaceKey, surfaces.length]);

  useEffect(() => {
    const scene = sceneRef.current;
    const canvas = canvasRef.current;
    if (!scene || !canvas) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let dark = document.documentElement.classList.contains('dark');
    let raf = 0;
    let lastPaint = 0;
    const render = (time: number) => {
      paintBackdrop(canvas, scene.clientWidth, scene.clientHeight, time, dark);
      instanceRef.current?.markChanged(canvas);
    };
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (document.hidden) return;
      if (now - lastPaint < 1000 / BACKDROP_FPS) return;
      lastPaint = now;
      render(now / 1000);
    };
    const sync = () => {
      if (motion.matches) {
        cancelAnimationFrame(raf);
        raf = 0;
        render(0);
      } else if (!raf) {
        raf = requestAnimationFrame(loop);
      }
    };
    const themeObserver = new MutationObserver(() => {
      dark = document.documentElement.classList.contains('dark');
      if (motion.matches) render(0);
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    const resizeObserver = new ResizeObserver(() => { if (motion.matches) render(0); });
    resizeObserver.observe(scene);
    motion.addEventListener('change', sync);
    render(0);
    sync();
    return () => {
      cancelAnimationFrame(raf);
      themeObserver.disconnect();
      resizeObserver.disconnect();
      motion.removeEventListener('change', sync);
    };
  }, []);

  return <div ref={sceneRef} className={`lg-scene lg-scene-${variant}`} aria-hidden="true">
    <canvas ref={canvasRef} className="lg-backdrop" />
    {surfaces.map(surface => <div
      key={surface.key}
      className="lg-surface"
      data-config={JSON.stringify({ cornerRadius: surface.radius })}
      style={{ left: surface.left, top: surface.top, width: surface.width, height: surface.height, borderRadius: surface.radius }}
    />)}
  </div>;
}

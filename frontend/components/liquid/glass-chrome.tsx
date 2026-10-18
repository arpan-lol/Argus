"use client";

import { type ComponentProps, type PointerEvent as ReactPointerEvent, type ReactNode, useRef } from "react";
import { GlassSurface, type GlassSurfaceHandle } from "@/components/ui/glass";
import { Track, glide, easeGel, easeSoft, PRESS, RELEASE } from "@/components/ui/glass-motion";
import { cn } from "@/lib/utils";
import "./glass-chrome.css";

export const GLASS_MATERIAL = { blur: 10, saturation: 1.25 };
export const GLASS_TINT = 0.26;
export const GLASS_TINT_LIFT = -0.1;

interface Press {
  surface: React.RefObject<GlassSurfaceHandle | null>;
  scaler: React.RefObject<HTMLSpanElement | null>;
  handlers: {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerLeave: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerCancel: (event: ReactPointerEvent<HTMLElement>) => void;
  };
}

function useGelPress(lift = GLASS_TINT_LIFT, scaleTo = 0.93): Press {
  const surface = useRef<GlassSurfaceHandle | null>(null);
  const scaler = useRef<HTMLSpanElement | null>(null);
  const scale = useRef(new Track(1));
  const down = (event: ReactPointerEvent<HTMLElement>) => {
    const track = scale.current;
    track.watch((value) => {
      if (scaler.current) scaler.current.style.scale = String(value);
    });
    surface.current?.setTintLift(lift);
    glide(track, scaleTo, PRESS, easeGel);
  };
  const up = () => {
    surface.current?.setTintLift(0);
    glide(scale.current, 1, RELEASE, easeSoft);
  };
  return { surface, scaler, handlers: { onPointerDown: down, onPointerUp: up, onPointerLeave: up, onPointerCancel: up } };
}

interface GlassIconButtonProps extends Omit<ComponentProps<"button">, "children"> {
  size?: number;
  tone?: "plain" | "accent";
  children?: ReactNode;
}

export function GlassIconButton({ size = 32, tone = "plain", className, children, ...props }: GlassIconButtonProps) {
  const press = useGelPress(tone === "accent" ? -0.06 : GLASS_TINT_LIFT);
  return (
    <button
      type="button"
      className={cn("argus-gl-icon relative select-none outline-none", className)}
      style={{ width: size, height: size }}
      {...press.handlers}
      {...props}
    >
      <span ref={press.scaler} className="block size-full origin-center" style={{ scale: "1" }}>
        <GlassSurface
          handleRef={press.surface}
          tint={GLASS_TINT}
          radius={999}
          blur={GLASS_MATERIAL.blur}
          saturation={GLASS_MATERIAL.saturation}
          className="size-full overflow-hidden"
          contentClassName="flex items-center justify-center"
        >
          {tone === "accent" && <span aria-hidden className="argus-gl-accent" />}
          <span className="relative z-10 flex items-center justify-center">{children}</span>
        </GlassSurface>
      </span>
    </button>
  );
}

interface GlassChipProps extends Omit<ComponentProps<"button">, "children"> {
  children?: ReactNode;
}

export function GlassChip({ className, children, ...props }: GlassChipProps) {
  const press = useGelPress();
  return (
    <button
      type="button"
      className={cn("argus-gl-chip relative select-none outline-none", className)}
      {...press.handlers}
      {...props}
    >
      <span ref={press.scaler} className="block origin-center" style={{ scale: "1" }}>
        <GlassSurface
          handleRef={press.surface}
          tint={GLASS_TINT}
          radius={10}
          blur={GLASS_MATERIAL.blur}
          saturation={GLASS_MATERIAL.saturation}
          className="overflow-hidden"
          contentClassName="flex items-center justify-between gap-3 px-3.5 py-2.5"
        >
          <span className="relative z-10 flex items-center justify-between gap-3 text-[11px]">{children}</span>
        </GlassSurface>
      </span>
    </button>
  );
}

export function GlassHandle({ className }: { className?: string }) {
  return (
    <div className={cn("flex h-full w-full items-center justify-center", className)}>
      <GlassSurface
        tint={GLASS_TINT}
        radius={999}
        blur={GLASS_MATERIAL.blur}
        saturation={GLASS_MATERIAL.saturation}
        className="argus-grip"
        style={{ width: 11, height: 38 }}
        contentClassName="flex items-center justify-center"
      >
        <span className="argus-grip-dots" aria-hidden>
          <i />
          <i />
          <i />
        </span>
      </GlassSurface>
    </div>
  );
}

"use client";

import { type ComponentProps, type ReactNode, useRef } from "react";
import { GlassSurface, type GlassSurfaceHandle } from "@/components/ui/glass";
import { Track, glide, easeGel, easeSoft, PRESS, RELEASE } from "@/components/ui/glass-motion";
import { cn } from "@/lib/utils";

interface GlassButtonProps extends ComponentProps<"button"> {
  /** Frosted tint 0–1. */
  tint?: number;
  /** "icon" = circular disc, "capsule" = text pill. */
  variant?: "icon" | "capsule";
  children?: ReactNode;
}

export function GlassButton({
  tint = 0.32,
  variant = "icon",
  children,
  className,
  onPointerDown,
  onPointerUp,
  onPointerLeave,
  onPointerCancel,
  ...props
}: GlassButtonProps) {
  const surface = useRef<GlassSurfaceHandle | null>(null);
  const scaleEl = useRef<HTMLSpanElement | null>(null);
  const scale = useRef(new Track(1));
  const isIcon = variant === "icon";

  const press = () => {
    scale.current.watch((v) => {
      if (scaleEl.current) scaleEl.current.style.scale = String(v);
    });
    surface.current?.setTintLift(-0.14);
    glide(scale.current, 0.92, PRESS, easeGel);
  };

  const release = () => {
    surface.current?.setTintLift(0);
    glide(scale.current, 1, RELEASE, easeSoft);
  };

  return (
    <button
      type="button"
      className={cn(
        "relative select-none outline-none transition-[filter] focus-visible:brightness-110",
        isIcon ? "rounded-full" : "rounded-2xl",
        className,
      )}
      onPointerDown={(e) => { press(); onPointerDown?.(e); }}
      onPointerUp={(e) => { release(); onPointerUp?.(e); }}
      onPointerLeave={(e) => { release(); onPointerLeave?.(e); }}
      onPointerCancel={(e) => { release(); onPointerCancel?.(e); }}
      {...props}
    >
      <span ref={scaleEl} className="block origin-center" style={{ scale: "1" }}>
        <GlassSurface
          handleRef={surface}
          tint={tint}
          radius={isIcon ? 999 : 16}
          className={cn("text-foreground", isIcon ? "size-12" : "h-12 px-6")}
          contentClassName="flex items-center justify-center"
        >
          <span className="relative z-10 text-sm font-medium">{children}</span>
        </GlassSurface>
      </span>
    </button>
  );
}

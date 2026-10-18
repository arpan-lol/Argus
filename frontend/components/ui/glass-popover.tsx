"use client";

import {
  type ComponentProps,
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { GlassSurface } from "@/components/ui/glass";
import { cn } from "@/lib/utils";

// ─── Context ──────────────────────────────────────────────────────────────────

interface PopoverCtx {
  open: boolean;
  setOpen: (v: boolean) => void;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
}
const PopoverContext = createContext<PopoverCtx>({
  open: false,
  setOpen: () => undefined,
  triggerRef: { current: null },
});

// ─── Root ─────────────────────────────────────────────────────────────────────

interface PopoverProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (v: boolean) => void;
  children?: ReactNode;
}

export function Popover({ open: controlled, defaultOpen = false, onOpenChange, children }: PopoverProps) {
  const [internal, setInternal] = useState(defaultOpen);
  const open = controlled !== undefined ? controlled : internal;
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  const setOpen = useCallback(
    (v: boolean) => {
      if (controlled === undefined) setInternal(v);
      onOpenChange?.(v);
    },
    [controlled, onOpenChange],
  );

  return (
    <PopoverContext.Provider value={{ open, setOpen, triggerRef }}>
      <div className="relative inline-flex">{children}</div>
    </PopoverContext.Provider>
  );
}

// ─── Trigger ──────────────────────────────────────────────────────────────────

export function PopoverTrigger({ children, className, ...props }: ComponentProps<"button">) {
  const { setOpen, open, triggerRef } = useContext(PopoverContext);
  return (
    <button
      ref={triggerRef}
      type="button"
      aria-expanded={open}
      className={cn("outline-none", className)}
      onClick={() => setOpen(!open)}
      {...props}
    >
      {children}
    </button>
  );
}

// ─── Content ──────────────────────────────────────────────────────────────────

interface PopoverContentProps extends ComponentProps<"div"> {
  tint?: number;
  side?: "top" | "bottom" | "left" | "right";
  sideOffset?: number;
  align?: "start" | "center" | "end";
}

export function PopoverContent({
  tint = 0.42,
  side = "bottom",
  sideOffset = 8,
  align = "center",
  children,
  className,
  ...props
}: PopoverContentProps) {
  const { open, setOpen, triggerRef } = useContext(PopoverContext);
  const ref = useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; tx: string }>({
    top: 0,
    left: 0,
    tx: "translate(-50%, 0)",
  });

  useEffect(() => setMounted(true), []);

  // Position relative to the trigger, in fixed (viewport) coordinates, so no
  // ancestor's overflow:hidden can clip it. Re-place on scroll / resize.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const t = triggerRef.current?.getBoundingClientRect();
      if (!t) return;
      let top = 0;
      let left = 0;
      let tx = "";
      if (side === "bottom" || side === "top") {
        top = side === "bottom" ? t.bottom + sideOffset : t.top - sideOffset;
        const ty = side === "bottom" ? "0" : "-100%";
        if (align === "center") { left = t.left + t.width / 2; tx = `translate(-50%, ${ty})`; }
        else if (align === "start") { left = t.left; tx = `translate(0, ${ty})`; }
        else { left = t.right; tx = `translate(-100%, ${ty})`; }
      } else {
        left = side === "right" ? t.right + sideOffset : t.left - sideOffset;
        const txx = side === "right" ? "0" : "-100%";
        top = t.top;
        tx = `translate(${txx}, 0)`;
      }
      setPos({ top, left, tx });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, side, align, sideOffset, triggerRef]);

  // Outside-click (ignore the trigger) + Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (ref.current && !ref.current.contains(t) && !triggerRef.current?.contains(t)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, setOpen, triggerRef]);

  if (!mounted) return null;

  const originY = side === "bottom" ? "top" : side === "top" ? "bottom" : "center";

  return createPortal(
    <div
      ref={ref}
      role="dialog"
      style={{
        position: "fixed",
        top: pos.top,
        left: pos.left,
        transform: `${pos.tx} scale(${open ? 1 : 0.92})`,
        opacity: open ? 1 : 0,
        pointerEvents: open ? "auto" : "none",
        zIndex: 1000,
        transformOrigin: `${originY} center`,
        transition: "opacity 0.18s, transform 0.2s cubic-bezier(0.22,1.15,0.36,1.06)",
      }}
      className={cn("min-w-[200px]", className)}
      {...props}
    >
      <GlassSurface tint={tint} radius={20} className="overflow-hidden py-2">
        {children}
      </GlassSurface>
    </div>,
    document.body,
  );
}

// ─── Menu items ───────────────────────────────────────────────────────────────

export function PopoverItem({ children, className, ...props }: ComponentProps<"button">) {
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-3 px-4 py-2.5 text-sm text-foreground/80 outline-none transition-colors hover:bg-foreground/5 focus-visible:bg-foreground/5",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function PopoverSeparator({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn("my-1 mx-4 h-px bg-foreground/10", className)}
    />
  );
}

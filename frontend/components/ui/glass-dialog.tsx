"use client";

import {
  type ComponentProps,
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { GlassSurface } from "@/components/ui/glass";
import { cn } from "@/lib/utils";

interface DialogCtx {
  open: boolean;
  setOpen: (v: boolean) => void;
}
const DialogContext = createContext<DialogCtx>({ open: false, setOpen: () => undefined });

interface DialogProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (v: boolean) => void;
  children?: ReactNode;
}

export function Dialog({ open: controlled, defaultOpen = false, onOpenChange, children }: DialogProps) {
  const [internal, setInternal] = useState(defaultOpen);
  const open = controlled !== undefined ? controlled : internal;
  const setOpen = useCallback(
    (v: boolean) => {
      if (controlled === undefined) setInternal(v);
      onOpenChange?.(v);
    },
    [controlled, onOpenChange],
  );
  return <DialogContext.Provider value={{ open, setOpen }}>{children}</DialogContext.Provider>;
}

export function DialogTrigger({ children, className, ...props }: ComponentProps<"button">) {
  const { setOpen } = useContext(DialogContext);
  return (
    <button type="button" className={cn("outline-none", className)} onClick={() => setOpen(true)} {...props}>
      {children}
    </button>
  );
}

interface DialogContentProps extends ComponentProps<"div"> {
  tint?: number;
}

/** Renders the scrim + panel in a portal on <body>; closes on scrim / Escape. */
export function DialogContent({ tint = 0.42, children, className, ...props }: DialogContentProps) {
  const { open, setOpen } = useContext(DialogContext);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, setOpen]);

  if (!mounted || !open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px] animate-in fade-in-0 duration-200"
        onClick={() => setOpen(false)}
      />
      <GlassSurface
        role="dialog"
        aria-modal="true"
        tint={tint}
        radius={24}
        className={cn("relative z-10 w-full max-w-md p-6 animate-in fade-in-0 zoom-in-95 duration-200", className)}
        {...props}
      >
        {children}
      </GlassSurface>
    </div>,
    document.body,
  );
}

export function DialogTitle({ children, className, ...props }: ComponentProps<"h2">) {
  return <h2 className={cn("text-lg font-semibold text-foreground", className)} {...props}>{children}</h2>;
}

export function DialogDescription({ children, className, ...props }: ComponentProps<"p">) {
  return <p className={cn("mt-1.5 text-sm text-muted-foreground", className)} {...props}>{children}</p>;
}

export function DialogFooter({ children, className, ...props }: ComponentProps<"div">) {
  return <div className={cn("mt-6 flex justify-end gap-2", className)} {...props}>{children}</div>;
}

export function DialogClose({ children, className, ...props }: ComponentProps<"button">) {
  const { setOpen } = useContext(DialogContext);
  return (
    <button type="button" className={cn("outline-none", className)} onClick={() => setOpen(false)} {...props}>
      {children}
    </button>
  );
}

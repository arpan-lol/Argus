"use client";

import {
  type ComponentProps,
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { GlassSurface, useGlassDark } from "@/components/ui/glass";
import { Track, spring, reduceMotion } from "@/components/ui/glass-motion";
import { cn } from "@/lib/utils";

interface TabsCtx {
  value: string;
  setValue: (v: string) => void;
}
const TabsContext = createContext<TabsCtx>({ value: "", setValue: () => undefined });

interface TabsProps extends ComponentProps<"div"> {
  value?: string;
  defaultValue?: string;
  onValueChange?: (v: string) => void;
}

export function Tabs({ value: controlled, defaultValue = "", onValueChange, children, className, ...props }: TabsProps) {
  const [internal, setInternal] = useState(defaultValue);
  const active = controlled !== undefined ? controlled : internal;
  const setValue = useCallback(
    (v: string) => {
      if (controlled === undefined) setInternal(v);
      onValueChange?.(v);
    },
    [controlled, onValueChange],
  );
  const ctx = useMemo(() => ({ value: active, setValue }), [active, setValue]);
  return (
    <TabsContext.Provider value={ctx}>
      <div className={cn("flex flex-col", className)} {...props}>{children}</div>
    </TabsContext.Provider>
  );
}

interface TabsListProps extends ComponentProps<"div"> {
  tint?: number;
  children?: ReactNode;
}

export function TabsList({ tint = 0.3, children, className, ...props }: TabsListProps) {
  const { value } = useContext(TabsContext);
  const dark = useGlassDark();
  const listRef = useRef<HTMLDivElement | null>(null);
  const pill = useRef<HTMLDivElement | null>(null);
  const xT = useRef(new Track(0));
  const wT = useRef(new Track(0));
  const dT = useRef(new Track(0)); // droplet deform driven by travel velocity
  const ready = useRef(false);

  useEffect(() => {
    const paint = () => {
      const el = pill.current;
      if (!el) return;
      const x = xT.current.get();
      const w = wT.current.get();
      const q = dT.current.get();
      el.style.width = `${w}px`;
      // stretch along travel, thin slightly across — a gliding droplet
      el.style.transform = `translateX(${x}px) scale(${1 + 0.5 * q}, ${1 - 0.28 * q})`;
    };
    const subs = [xT.current.watch(paint), wT.current.watch(paint), dT.current.watch(paint)];
    return () => subs.forEach((o) => o());
  }, []);

  const move = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    const el = list.querySelector<HTMLElement>(`[data-tab][data-value="${CSS.escape(value)}"]`);
    if (!el) return;
    const lr = list.getBoundingClientRect();
    const er = el.getBoundingClientRect();
    const x = er.left - lr.left;
    const w = er.width;
    if (!ready.current || reduceMotion()) {
      xT.current.snap(x); wT.current.snap(w); ready.current = true; return;
    }
    spring(xT.current, () => x, { tension: 380, friction: 30 });
    spring(wT.current, () => w, { tension: 380, friction: 30 });
    // droplet: chase the indicator's own travel velocity, settle back to round
    let done = false;
    spring(
      dT.current,
      () => {
        const v = Math.abs(xT.current.velocity());
        return Math.min(0.3, 0.0022 * v ** 0.7);
      },
      { tension: 200, friction: 13, canRest: () => done && Math.abs(xT.current.velocity()) < 0.02 },
    );
    // allow the deform spring to rest once the pill has essentially arrived
    setTimeout(() => { done = true; }, 60);
  }, [value]);

  useLayoutEffect(() => { move(); }, [move]);

  // Mount-once ResizeObserver. We keep the latest `move` in a ref so the
  // observer never re-subscribes on tab change (re-subscribing would fire the
  // observer's synchronous initial callback, reset `ready`, and snap the pill
  // instead of springing it). The first, initial observation is ignored;
  // genuine resizes re-place the pill via the ref.
  const moveRef = useRef(move);
  moveRef.current = move;
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    let first = true;
    const ro = new ResizeObserver(() => {
      if (first) { first = false; return; }
      ready.current = false;
      moveRef.current();
    });
    ro.observe(list);
    return () => ro.disconnect();
  }, []);

  return (
    <GlassSurface tint={tint} radius={9999} className={cn("relative inline-flex p-1", className)} {...props}>
      <div
        ref={pill}
        aria-hidden
        className="pointer-events-none absolute bottom-1 top-1 left-0 rounded-full"
        style={{
          width: 0,
          background: dark ? "rgba(255,255,255,0.16)" : "rgba(0,0,0,0.08)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.3), 0 2px 10px rgba(0,0,0,0.18)",
        }}
      />
      <div ref={listRef} className="relative flex items-center gap-1">{children}</div>
    </GlassSurface>
  );
}

interface TabsTriggerProps extends ComponentProps<"button"> {
  value: string;
}
export function TabsTrigger({ value, children, className, ...props }: TabsTriggerProps) {
  const { value: active, setValue } = useContext(TabsContext);
  const on = active === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={on}
      data-tab
      data-value={value}
      className={cn(
        "relative z-10 flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium outline-none transition-colors duration-200",
        on ? "text-foreground" : "text-muted-foreground hover:text-foreground/75",
        className,
      )}
      onClick={() => setValue(value)}
      {...props}
    >
      {children}
    </button>
  );
}

interface TabsContentProps extends ComponentProps<"div"> {
  value: string;
}
export function TabsContent({ value, children, className, ...props }: TabsContentProps) {
  const { value: active } = useContext(TabsContext);
  if (active !== value) return null;
  return <div role="tabpanel" className={cn("mt-3", className)} {...props}>{children}</div>;
}

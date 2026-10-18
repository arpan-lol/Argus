"use client";

import { type ComponentProps, useEffect, useRef, useState } from "react";
import { GlassLens, useGlassDark } from "@/components/ui/glass";
import { Track, spring, glide, easeGel, easeSoft, overdrag, clamp, reduceMotion } from "@/components/ui/glass-motion";
import { cn } from "@/lib/utils";

const TRACK_W = 56;
const TRACK_H = 32;
const THUMB = 26;
const PAD = (TRACK_H - THUMB) / 2;
const TRAVEL = TRACK_W - THUMB - PAD * 2;

// gel deformation tuning
const DEFORM_GAIN = 0.0026;   // velocity → deform
const DEFORM_EXP = 0.7;
const DEFORM_CAP = 0.34;
const HOLD_BOOST = 0.14;      // slight squish while held even when still

interface GlassSwitchProps extends Omit<ComponentProps<"button">, "onChange"> {
  checked?: boolean;
  defaultChecked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  ariaLabel?: string;
}

export function GlassSwitch({
  checked: controlled,
  defaultChecked = false,
  onCheckedChange,
  ariaLabel = "Toggle",
  className,
  ...props
}: GlassSwitchProps) {
  const dark = useGlassDark();
  const isControlled = controlled !== undefined;
  const [internal, setInternal] = useState(defaultChecked);
  const on = isControlled ? controlled : internal;

  // animated values
  const pos = useRef(new Track(on ? TRAVEL : 0));   // thumb x
  const lift = useRef(new Track(0));                // press progress 0..1
  const deform = useRef(new Track(0));              // gel squish 0..~0.34

  // dom
  const thumb = useRef<HTMLSpanElement | null>(null);
  const solid = useRef<HTMLSpanElement | null>(null);
  const glass = useRef<HTMLSpanElement | null>(null);

  const pressed = useRef(false);
  const drag = useRef<{ startX: number; from: number; moved: boolean } | null>(null);

  // Single paint reading all three tracks; runs whenever any of them updates.
  useEffect(() => {
    const paint = () => {
      const x = pos.current.get();
      const l = lift.current.get();
      const q = deform.current.get();
      const el = thumb.current;
      if (el) {
        const grow = 1 + 0.16 * l;
        const sx = grow * (1 + 0.62 * q);   // stretch along travel
        const sy = grow * (1 - 0.42 * q);   // squish across
        el.style.transform = `translateX(${x}px) scale(${sx}, ${sy})`;
      }
      if (solid.current) solid.current.style.opacity = String(1 - l);
      if (glass.current) glass.current.style.opacity = String(l);
    };
    const subs = [pos.current.watch(paint), lift.current.watch(paint), deform.current.watch(paint)];
    return () => { subs.forEach((o) => o()); };
  }, []);

  // Keep the gel spring chasing the thumb's velocity while interacting.
  const runDeform = () => {
    if (reduceMotion()) return;
    spring(
      deform.current,
      () => {
        const v = Math.abs(pos.current.velocity());
        const fromVel = DEFORM_GAIN * v ** DEFORM_EXP;
        const boost = pressed.current ? HOLD_BOOST : 0;
        return clamp(Math.max(fromVel, boost), 0, DEFORM_CAP);
      },
      {
        tension: 210,
        friction: 12,
        canRest: () => !pressed.current && Math.abs(pos.current.velocity()) < 0.01,
      },
    );
  };

  // sync to external state when idle
  useEffect(() => {
    if (!pressed.current) {
      if (reduceMotion()) pos.current.snap(on ? TRAVEL : 0);
      else spring(pos.current, () => (on ? TRAVEL : 0), { tension: 340, friction: 24 });
      runDeform();
    }
  }, [on]);

  const onDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    pressed.current = true;
    drag.current = { startX: e.clientX, from: pos.current.get(), moved: false };
    pos.current.halt();
    glide(lift.current, 1, 0.26, easeGel);   // grow + clear tint into a lens
    runDeform();
  };

  const onMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!pressed.current || !drag.current) return;
    const dx = e.clientX - drag.current.startX;
    if (Math.abs(dx) > 3) drag.current.moved = true;
    const raw = drag.current.from + dx;
    const c = clamp(raw, 0, TRAVEL);
    pos.current.push(c + overdrag(raw - c, 26));  // velocity sampled here → feeds gel
  };

  const settle = (next: boolean) => {
    onCheckedChange?.(next);
    glide(lift.current, 0, 0.42, easeSoft);
    if (isControlled) {
      spring(pos.current, () => (on ? TRAVEL : 0), { tension: 320, friction: 22 });
    } else {
      setInternal(next);
      spring(pos.current, () => (next ? TRAVEL : 0), { tension: 320, friction: 22 });
    }
    runDeform();
  };

  const onUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!pressed.current) return;
    pressed.current = false;
    const d = drag.current;
    drag.current = null;
    void e;
    const next = d?.moved ? pos.current.get() > TRAVEL / 2 : !on;
    settle(next);
  };

  const onCancel = () => {
    if (!pressed.current) return;
    pressed.current = false;
    drag.current = null;
    glide(lift.current, 0, 0.42, easeSoft);
    spring(pos.current, () => (on ? TRAVEL : 0), { tension: 320, friction: 24 });
    runDeform();
  };

  const onKey = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); settle(!on); }
  };

  const trackOn = dark ? "#30d158" : "#34c759";
  const trackOff = dark ? "rgba(120,122,130,0.36)" : "rgba(120,122,130,0.22)";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={ariaLabel}
      className={cn("relative touch-none select-none rounded-full outline-none focus-visible:ring-2 focus-visible:ring-sky-400/50", className)}
      style={{ width: TRACK_W, height: TRACK_H }}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onCancel}
      onKeyDown={onKey}
      {...props}
    >
      <span
        aria-hidden
        className="absolute inset-0 rounded-full transition-colors duration-300"
        style={{ background: on ? trackOn : trackOff }}
      />
      <span
        ref={thumb}
        aria-hidden
        className="absolute rounded-full will-change-transform"
        style={{
          top: PAD,
          left: PAD,
          width: THUMB,
          height: THUMB,
          transformOrigin: "center",
          transform: `translateX(${on ? TRAVEL : 0}px)`,
        }}
      >
        <span
          ref={solid}
          className="absolute inset-0 rounded-full"
          style={{ background: "white", boxShadow: "0 2px 6px rgba(0,0,0,0.28), 0 0 0 0.5px rgba(0,0,0,0.04)" }}
        />
        <span ref={glass} className="absolute inset-0 rounded-full" style={{ opacity: 0 }}>
          <GlassLens width={THUMB} height={THUMB} radius={999} strength={0.7} blur={1} dome={0.35} />
        </span>
      </span>
    </button>
  );
}

export type Watcher = (value: number) => void;
export type Stop = () => void;

// How stale a sample can be before we treat velocity as zero (ms).
const VELOCITY_TIMEOUT = 90;

/** A single animated scalar with velocity tracking and frame subscribers. */
export class Track {
  private value: number;
  private watchers = new Set<Watcher>();
  private active: Stop | null = null;

  // velocity sampling
  private lastStamp = 0;
  private lastValue = 0;
  private speed = 0;

  constructor(initial: number) {
    this.value = initial;
    this.lastValue = initial;
  }

  get(): number {
    return this.value;
  }

  /** px per second, decayed to 0 once samples go stale. */
  velocity(): number {
    return now() - this.lastStamp > VELOCITY_TIMEOUT ? 0 : this.speed;
  }

  /** Update the value and notify watchers, sampling velocity from the delta. */
  push(next: number, stamp = now()): void {
    const dt = stamp - this.lastStamp;
    if (dt > VELOCITY_TIMEOUT) {
      this.speed = 0;
    } else if (dt > 0) {
      // clamp dt into a sane frame window so a stutter doesn't spike velocity
      const clamped = Math.min(Math.max(dt, 8), 32);
      this.speed = ((next - this.value) / clamped) * 1000;
    }
    this.lastStamp = stamp;
    this.lastValue = this.value;
    this.value = next;
    for (const w of this.watchers) w(next);
  }

  /** Snap to a value, cancelling any running driver and clearing velocity. */
  snap(next: number): void {
    this.halt();
    this.speed = 0;
    this.lastStamp = now();
    this.value = next;
    for (const w of this.watchers) w(next);
  }

  watch(fn: Watcher): Stop {
    this.watchers.add(fn);
    fn(this.value);
    return () => this.watchers.delete(fn);
  }




  /** Register the running driver's cancel fn so a new driver can pre-empt it. */
  claim(stop: Stop | null): void {
    this.active = stop;
  }

  halt(): void {
    this.active?.();
    this.active = null;
  }
}

function now(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

/**
 * easeOutBack — closed-form ease with a configurable overshoot tail.
 * `pull` of 0 is a plain ease-out; higher values overshoot past 1 and settle.
 */
export function easeOutBack(pull = 1.4) {
  const c = pull;
  return (t: number): number => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    const u = t - 1;
    return 1 + (c + 1) * u * u * u + c * u * u;
  };
}

/** Gentle ease with a hint of overshoot, used for presses and pops. */
export const easeGel = easeOutBack(1.3);
/** Plain smooth ease for fades and settles. */
export const easeSoft = (t: number): number =>
  t <= 0 ? 0 : t >= 1 ? 1 : 1 - (1 - t) ** 3;

// Default timings (seconds).
export const PRESS = 0.3;
export const RELEASE = 0.5;
export const TRAVEL = 0.55;

/** Tween a Track to `to` over `seconds` with the given easing. */
export function glide(
  track: Track,
  to: number,
  seconds: number,
  ease: (t: number) => number = easeSoft,
  onDone?: () => void,
): Stop {
  track.halt();
  if (seconds <= 0 || reduceMotion()) {
    track.snap(to);
    onDone?.();
    return () => undefined;
  }
  const from = track.get();
  const start = now();
  let raf = 0;
  let stopped = false;
  const tick = (t: number) => {
    if (stopped) return;
    const p = Math.min((t - start) / (seconds * 1000), 1);
    track.push(from + (to - from) * ease(p), t);
    if (p < 1) {
      raf = requestAnimationFrame(tick);
    } else {
      track.claim(null);
      onDone?.();
    }
  };
  raf = requestAnimationFrame(tick);
  const stop = () => {
    stopped = true;
    cancelAnimationFrame(raf);
  };
  track.claim(stop);
  return stop;
}

export interface SpringConfig {
  /** restoring force toward the target */
  tension?: number;
  /** velocity damping */
  friction?: number;
  /** distance below which the spring may rest */
  epsilon?: number;
  /**
   * Gate for resting. When it returns false the spring keeps running even if
   * it has momentarily settled — needed for springs that chase a live value
   * (e.g. a deform driven by another Track's velocity while a drag is active).
   */
  canRest?: () => boolean;
  onRest?: () => void;
}

/**
 * Drive a Track toward a (possibly changing) target with a damped spring,
 * integrated with semi-implicit Euler. Returns a stop fn. `target` is read
 * each frame so the spring can chase a moving goal.
 */
export function spring(
  track: Track,
  target: () => number,
  config: SpringConfig = {},
): Stop {
  const tension = config.tension ?? 320;
  const friction = config.friction ?? 28;
  const epsilon = config.epsilon ?? 0.001;
  const canRest = config.canRest ?? (() => true);

  if (reduceMotion()) {
    track.snap(target());
    config.onRest?.();
    return () => undefined;
  }

  track.halt();
  let vel = track.velocity() / 1000; // px/s → px per integration unit
  let raf = 0;
  let last = now();
  let stopped = false;

  const stop = () => {
    stopped = true;
    cancelAnimationFrame(raf);
  };
  track.claim(stop);

  const tick = (t: number) => {
    if (stopped) return;
    const dt = Math.min((t - last) / 1000, 0.032);
    last = t;
    const goal = target();
    const x = track.get();
    const accel = -tension * (x - goal) - friction * vel;
    vel += accel * dt;
    const next = x + vel * dt;
    track.push(next, t);
    if (Math.abs(next - goal) < epsilon && Math.abs(vel) < epsilon * 50 && canRest()) {
      track.push(goal, t);
      track.claim(null);
      config.onRest?.();
      return;
    }
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return stop;
}

/**
 * Rubber-band resistance for dragging past a boundary. `over` is how far past
 * the edge the pointer is; the returned offset grows ever more slowly, so the
 * element follows the finger but resists. `give` scales the maximum stretch.
 */
export function overdrag(over: number, give = 80): number {
  if (over === 0) return 0;
  const sign = Math.sign(over);
  const d = Math.abs(over);
  return sign * (1 - 1 / (d / give + 1)) * give;
}

export function reduceMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}

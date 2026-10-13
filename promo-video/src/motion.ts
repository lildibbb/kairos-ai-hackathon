import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import timeline from "./timeline.json";

export const FPS = timeline.fps;
export const sec = (s: number) => Math.round(s * FPS);

export const EASE = {
  out: Easing.bezier(0.16, 1, 0.3, 1),
  inOut: Easing.bezier(0.65, 0, 0.35, 1),
  in: Easing.bezier(0.7, 0, 0.84, 0),
  soft: Easing.bezier(0.33, 1, 0.68, 1),
};

/** Seconds elapsed inside the current Sequence. */
export const useSeconds = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return frame / fps;
};

/** Clamp-interpolate a value between two times (seconds). */
export const tween = (
  t: number,
  start: number,
  end: number,
  from = 0,
  to = 1,
  easing: (n: number) => number = EASE.out,
) =>
  interpolate(t, [start, end], [from, to], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing,
  });

/** Fade/blur-in reveal used for most text: returns style props. */
export const reveal = (t: number, at: number, dur = 0.9, rise = 24, blur = 14) => {
  const p = tween(t, at, at + dur);
  return {
    opacity: p,
    translate: `0px ${(1 - p) * rise}px`,
    filter: `blur(${(1 - p) * blur}px)`,
  } as const;
};

/** Reveal then exit, for one-idea-per-shot text. */
export const inOut = (t: number, at: number, until: number, dur = 0.8) => {
  const a = tween(t, at, at + dur);
  const b = tween(t, until - 0.5, until, 0, 1, EASE.in);
  return {
    opacity: a * (1 - b),
    translate: `0px ${(1 - a) * 26 - b * 10}px`,
    filter: `blur(${(1 - a) * 16 + b * 10}px)`,
    scale: String(1 + (1 - a) * 0.04),
  } as const;
};

type Key = { t: number; v: number };
/** Piecewise keyframes with ease-in-out between each pair. */
export const keys = (t: number, k: Key[], easing = EASE.inOut) => {
  if (t <= k[0].t) return k[0].v;
  for (let i = 0; i < k.length - 1; i++) {
    if (t <= k[i + 1].t) return tween(t, k[i].t, k[i + 1].t, k[i].v, k[i + 1].v, easing);
  }
  return k[k.length - 1].v;
};

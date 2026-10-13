import type React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { C } from "../theme";

const GRAIN = `url("data:image/svg+xml;utf8,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.55 0"/></filter><rect width="100%" height="100%" filter="url(#n)"/></svg>',
)}")`;

type Props = {
  /** 0..1 strength of the cobalt glow. */
  glow?: number;
  /** Glow centre, in % of the frame. */
  x?: number;
  y?: number;
  /** Orange accent glow strength. */
  warm?: number;
  black?: boolean;
};

export const Backdrop: React.FC<Props> = ({ glow = 1, x = 50, y = 45, warm = 0, black = false }) => {
  const frame = useCurrentFrame();
  const drift = Math.sin(frame / 90) * 4;
  return (
    <AbsoluteFill style={{ background: black ? "#000" : `radial-gradient(120% 90% at 50% 40%, ${C.ink} 0%, ${C.inkDeep} 70%, #000 100%)` }}>
      <AbsoluteFill
        style={{
          opacity: glow,
          background: `radial-gradient(42% 46% at ${x + drift}% ${y}%, rgba(74,59,255,0.55) 0%, rgba(26,0,230,0.22) 40%, transparent 72%)`,
        }}
      />
      <AbsoluteFill
        style={{
          opacity: warm,
          background: `radial-gradient(30% 30% at ${80 - drift}% 85%, rgba(255,98,0,0.35) 0%, transparent 70%)`,
        }}
      />
      <AbsoluteFill style={{ background: "radial-gradient(80% 80% at 50% 50%, transparent 55%, rgba(0,0,0,0.65) 100%)" }} />
    </AbsoluteFill>
  );
};

/** Animated film grain + vignette, laid over everything. */
export const Grain: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        backgroundImage: GRAIN,
        backgroundPosition: `${(frame * 37) % 240}px ${(frame * 53) % 240}px`,
        opacity: 0.055,
        mixBlendMode: "overlay",
        pointerEvents: "none",
      }}
    />
  );
};

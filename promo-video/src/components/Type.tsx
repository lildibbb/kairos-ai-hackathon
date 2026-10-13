import type React from "react";
import { AbsoluteFill } from "remotion";
import { C, F } from "../theme";
import { tween } from "../motion";
import timeline from "../timeline.json";
import durations from "../vo-durations.json";
import { VO_TEXT } from "../script";

export const Eyebrow: React.FC<{ children: React.ReactNode; style?: React.CSSProperties; color?: string }> = ({ children, style, color = C.orange }) => (
  <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 30, letterSpacing: "0.32em", textTransform: "uppercase", color, ...style }}>{children}</div>
);

/** Big centred display line with a metallic white-to-periwinkle fill. */
export const BigLine: React.FC<{ children: React.ReactNode; size?: number; style?: React.CSSProperties; accent?: boolean }> = ({ children, size = 150, style, accent }) => (
  <div
    style={{
      fontFamily: F.display,
      fontWeight: 800,
      fontSize: size,
      lineHeight: 1,
      letterSpacing: "-0.035em",
      textAlign: "center",
      color: accent ? C.orange : "#fff",
      backgroundImage: accent ? `linear-gradient(180deg, #FFB27A 0%, ${C.orange} 60%, #E04E00 100%)` : `linear-gradient(180deg, #FFFFFF 0%, #FFFFFF 45%, ${C.peri} 120%)`,
      WebkitBackgroundClip: "text",
      backgroundClip: "text",
      WebkitTextFillColor: "transparent",
      ...style,
    }}
  >
    {children}
  </div>
);

export const Center: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", ...style }}>{children}</AbsoluteFill>
);

// Lines whose words are not already on screen as big type get a caption.
const CAPTIONED = new Set(["vo03", "vo06", "vo07", "vo09", "vo10", "vo16"]);

/** Burned-in captions driven by the voiceover schedule; t is global seconds. */
export const Captions: React.FC<{ t: number }> = ({ t }) => {
  const vo = timeline.vo as Record<string, number>;
  const dur = durations as Record<string, number>;
  const active = Object.keys(vo).find((k) => CAPTIONED.has(k) && t >= vo[k] - 0.05 && t <= vo[k] + dur[k] + 0.35);
  if (!active) return null;
  const start = vo[active];
  const end = start + dur[active] + 0.35;
  const o = Math.min(tween(t, start - 0.05, start + 0.2), 1 - tween(t, end - 0.25, end));
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 54, pointerEvents: "none" }}>
      <div
        style={{
          opacity: o,
          maxWidth: 1400,
          textAlign: "center",
          fontFamily: F.ui,
          fontWeight: 500,
          fontSize: 34,
          lineHeight: 1.3,
          color: "rgba(255,255,255,0.94)",
          padding: "10px 22px",
          borderRadius: 14,
          background: "rgba(3,0,32,0.55)",
          backdropFilter: "blur(12px)",
        }}
      >
        {VO_TEXT[active]}
      </div>
    </AbsoluteFill>
  );
};

export const LowerThird: React.FC<{ t: number; from: number; to: number }> = ({ t, from, to }) => {
  const o = Math.min(tween(t, from, from + 0.6), 1 - tween(t, to - 0.5, to));
  if (o <= 0) return null;
  return (
    <div
      style={{
        position: "absolute",
        left: 80,
        top: 64,
        zIndex: 20,
        padding: "10px 18px",
        borderRadius: 12,
        background: "rgba(3,0,32,0.6)",
        backdropFilter: "blur(10px)",
        opacity: o,
        translate: `${(1 - o) * -20}px 0px`,
        display: "flex",
        alignItems: "center",
        gap: 14,
        fontFamily: F.ui,
        fontWeight: 700,
        fontSize: 20,
        letterSpacing: "0.2em",
        color: "#fff",
      }}
    >
      <div style={{ width: 12, height: 12, borderRadius: 6, background: C.orange, boxShadow: `0 0 18px ${C.orange}` }} />
      PRODUCT UI <span style={{ color: C.peri }}>·</span> SAMPLE TICKET DATA
    </div>
  );
};

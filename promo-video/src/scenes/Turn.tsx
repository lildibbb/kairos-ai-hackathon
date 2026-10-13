import type React from "react";
import { AbsoluteFill } from "remotion";
import { Backdrop } from "../components/Backdrop";
import { BigLine, Center } from "../components/Type";
import { KairosMark } from "../components/KairosUi";
import { C, F } from "../theme";
import { EASE, tween, useSeconds } from "../motion";

const WORDS_1 = ["What", "if", "every", "technician", "knew", "the", "next", "move…"];
const WORDS_2 = ["before", "they", "even", "arrived?"];

/** Act 2 (0:25–0:35): silence, one question, the name. Local 0–10 s. */
export const Turn: React.FC = () => {
  const t = useSeconds();
  const questionOut = tween(t, 7.0, 7.6, 0, 1, EASE.in);
  const mark = tween(t, 7.7, 9.0);
  const sweep = tween(t, 8.1, 9.6, 0, 1, EASE.inOut);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <AbsoluteFill style={{ opacity: tween(t, 7.4, 9.5) }}>
        <Backdrop glow={0.7} />
      </AbsoluteFill>
      <Center style={{ opacity: 1 - questionOut, filter: `blur(${questionOut * 12}px)`, gap: 18 }}>
        <div style={{ display: "flex", gap: 22, flexWrap: "wrap", justifyContent: "center", maxWidth: 1500 }}>
          {WORDS_1.map((w, i) => {
            const p = tween(t, 3.35 + i * 0.16, 4.1 + i * 0.16);
            return (
              <span key={w + i} style={{ fontFamily: F.display, fontWeight: 600, fontSize: 78, letterSpacing: "-0.02em", color: "#fff", opacity: p, filter: `blur(${(1 - p) * 10}px)`, translate: `0px ${(1 - p) * 18}px` }}>
                {w}
              </span>
            );
          })}
        </div>
        <div style={{ display: "flex", gap: 22 }}>
          {WORDS_2.map((w, i) => {
            const p = tween(t, 5.05 + i * 0.16, 5.8 + i * 0.16);
            return (
              <span key={w} style={{ fontFamily: F.display, fontWeight: 600, fontSize: 78, letterSpacing: "-0.02em", color: C.peri, opacity: p, filter: `blur(${(1 - p) * 10}px)`, translate: `0px ${(1 - p) * 18}px` }}>
                {w}
              </span>
            );
          })}
        </div>
      </Center>
      <Center style={{ opacity: mark, scale: String(1.08 - 0.08 * mark), gap: 34 }}>
        <div style={{ filter: `drop-shadow(0 0 ${40 * mark}px rgba(74,59,255,0.8))` }}>
          <KairosMark size={150} ring={C.blue} />
        </div>
        <div style={{ position: "relative" }}>
          <BigLine size={170} style={{ letterSpacing: "0.28em", fontWeight: 700, marginRight: "-0.28em" }}>
            KAIROS
          </BigLine>
          {/* light sweep across the wordmark */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              fontFamily: F.display,
              fontWeight: 700,
              fontSize: 170,
              lineHeight: 1,
              letterSpacing: "0.28em",
              marginRight: "-0.28em",
              textAlign: "center",
              backgroundImage: `linear-gradient(100deg, transparent ${sweep * 160 - 40}%, rgba(255,255,255,1) ${sweep * 160 - 25}%, rgba(255,160,90,0.9) ${sweep * 160 - 18}%, transparent ${sweep * 160 - 5}%)`,
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
              WebkitTextFillColor: "transparent",
              filter: "blur(1px)",
            }}
          >
            KAIROS
          </div>
        </div>
      </Center>
    </AbsoluteFill>
  );
};

import type React from "react";
import { AbsoluteFill } from "remotion";
import { Check } from "lucide-react";
import { Backdrop } from "../components/Backdrop";
import { BigLine, Center, Eyebrow } from "../components/Type";
import { C, F } from "../theme";
import { EASE, tween, useSeconds } from "../motion";

/** Wraps one stat: punch-in on its hit, blur-out before the next. */
const Beat: React.FC<{ t: number; from: number; to: number; children: React.ReactNode }> = ({ t, from, to, children }) => {
  if (t < from || t >= to) return null;
  const a = tween(t, from, from + 0.5);
  const b = tween(t, to - 0.35, to, 0, 1, EASE.in);
  return <Center style={{ opacity: a * (1 - b), scale: String(1.1 - 0.1 * a + 0.04 * b), filter: `blur(${(1 - a) * 12 + b * 14}px)` }}>{children}</Center>;
};

const Est: React.FC = () => (
  <span style={{ marginLeft: 22, padding: "6px 16px", border: `2px dashed ${C.peri}`, borderRadius: 12, fontFamily: F.ui, fontWeight: 700, fontSize: 24, letterSpacing: "0.18em", color: C.peri, verticalAlign: "middle" }}>EST.</span>
);

/** Act 5 (2:10–2:30): the numbers. Local 0–20 s. */
export const Impact: React.FC = () => {
  const t = useSeconds();
  const ring = tween(t, 4.2, 5.6, 0, 0.9, EASE.out);
  const rm62 = Math.round(tween(t, 8.1, 9.0, 0, 62, EASE.out));
  const rm51 = Math.round(tween(t, 14.1, 15.1, 0, 51, EASE.out));
  return (
    <AbsoluteFill>
      <Backdrop glow={0.8} warm={0.4} />

      <Beat t={t} from={0} to={4}>
        <Eyebrow>Time back</Eyebrow>
        <BigLine size={250} accent style={{ marginTop: 10 }}>
          ~2 hours
        </BigLine>
        <div style={{ fontFamily: F.display, fontSize: 48, fontWeight: 600, color: "#fff", marginTop: 14 }}>per field team, every day.</div>
        <div style={{ display: "flex", gap: 16, marginTop: 50 }}>
          {[0, 1, 2, 3, 4, 5].map((i) => {
            const show = tween(t, 0.2 + i * 0.09, 0.6 + i * 0.09);
            const done = tween(t, 1.7 + i * 0.16, 2.0 + i * 0.16);
            return (
              <div
                key={i}
                style={{
                  width: 170,
                  height: 92,
                  borderRadius: 18,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 10,
                  background: done > 0.5 ? "rgba(255,98,0,0.16)" : C.blue,
                  border: `2px solid ${done > 0.5 ? C.orange : "transparent"}`,
                  opacity: show,
                  translate: `0px ${(1 - show) * 20}px`,
                  fontFamily: F.display,
                  fontWeight: 700,
                  fontSize: 26,
                  color: "#fff",
                }}
              >
                {done > 0.5 ? (
                  <>
                    <Check size={30} color={C.orange} strokeWidth={3} /> saved
                  </>
                ) : (
                  <span style={{ opacity: 1 - done }}>20–25 min</span>
                )}
              </div>
            );
          })}
        </div>
      </Beat>

      <Beat t={t} from={4} to={8}>
        <div style={{ display: "flex", alignItems: "center", gap: 90 }}>
          <div style={{ position: "relative", width: 480, height: 480 }}>
            <svg width={480} height={480} viewBox="0 0 480 480" style={{ rotate: "-90deg" }}>
              <circle cx={240} cy={240} r={200} stroke={C.indigo} strokeWidth={44} fill="none" />
              <circle cx={240} cy={240} r={200} stroke={C.orange} strokeWidth={44} fill="none" strokeLinecap="round" strokeDasharray={`${2 * Math.PI * 200 * ring} ${2 * Math.PI * 200}`} style={{ filter: "drop-shadow(0 0 20px rgba(255,98,0,0.6))" }} />
            </svg>
            <Center>
              <BigLine size={112}>&gt;{Math.round(ring * 100)}%</BigLine>
              <div style={{ fontFamily: F.ui, fontWeight: 700, fontSize: 24, letterSpacing: "0.22em", color: C.peri, marginTop: 10 }}>FFR TARGET</div>
            </Center>
          </div>
          <div>
            <Eyebrow color={C.peri} style={{ fontSize: 26 }}>KPI target</Eyebrow>
            <div style={{ fontFamily: F.display, fontWeight: 800, fontSize: 84, color: "#fff", letterSpacing: "-0.03em", marginTop: 12, lineHeight: 1.02 }}>
              First Fix
              <br />
              Right.
            </div>
            <div style={{ fontFamily: F.ui, fontSize: 32, color: C.peri, marginTop: 18 }}>Fixed correctly on the first visit.</div>
          </div>
        </div>
      </Beat>

      <Beat t={t} from={8} to={14}>
        <Eyebrow color={C.peri}>Cost reduced</Eyebrow>
        <div style={{ display: "flex", alignItems: "center", marginTop: 10 }}>
          <BigLine size={300} accent style={{ fontVariantNumeric: "tabular-nums" }}>
            RM{rm62}
          </BigLine>
          <Est />
        </div>
        <div style={{ fontFamily: F.display, fontSize: 50, fontWeight: 600, color: "#fff", marginTop: 8 }}>saved per repeat visit avoided.</div>
        <div style={{ fontFamily: F.ui, fontSize: 26, color: C.peri, marginTop: 22, opacity: tween(t, 9.4, 10) }}>Travel + salary for one truck roll</div>
      </Beat>

      <Beat t={t} from={14} to={20}>
        <Eyebrow color={C.peri}>Revenue increased</Eyebrow>
        <div style={{ display: "flex", alignItems: "center", marginTop: 10 }}>
          <BigLine size={300} accent style={{ fontVariantNumeric: "tabular-nums" }}>
            RM{rm51}M
          </BigLine>
          <Est />
        </div>
        <div style={{ fontFamily: F.display, fontSize: 50, fontWeight: 600, color: "#fff", marginTop: 8 }}>a year, for every +1% ARPU.</div>
        <div style={{ fontFamily: F.ui, fontSize: 26, color: C.peri, marginTop: 22, opacity: tween(t, 15.4, 16) }}>3.23M customers × RM132 × 12 months × 1%</div>
      </Beat>
    </AbsoluteFill>
  );
};

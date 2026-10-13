import type React from "react";
import { AbsoluteFill } from "remotion";
import { Cpu, Gauge, Radio, Smartphone, Wifi } from "lucide-react";
import { Backdrop } from "../components/Backdrop";
import { Laptop, Phone } from "../components/Devices";
import { PhoneTicket, Workspace } from "../components/KairosUi";
import { BigLine, Center, Eyebrow } from "../components/Type";
import { C, F } from "../theme";
import { EASE, inOut, keys, tween, useSeconds } from "../motion";

const DONE_STATE = { checksT: 99, timer: 12, rootCause: 1, nba: 1, reboot: 0, upsell: 1, verified: 0 };

const CHIPS = [
  { icon: Cpu, label: "Router CPU", at: 12.6 },
  { icon: Wifi, label: "Wi-Fi signal", at: 13.15 },
  { icon: Radio, label: "Fibre signal", at: 13.9 },
  { icon: Smartphone, label: "Devices", at: 14.5 },
  { icon: Gauge, label: "Data usage", at: 15.28 },
];

/** Act 3 (0:35–1:00): Apple-style reveal. Local 0–25 s. */
export const Reveal: React.FC = () => {
  const t = useSeconds();

  // Devices shot (0–12.4)
  const open = tween(t, 0.3, 3.4, 0, 1, EASE.inOut);
  const power = tween(t, 2.6, 3.6);
  const laptopScale = keys(t, [
    { t: 0, v: 0.5 },
    { t: 6, v: 0.6 },
    { t: 7.5, v: 0.54 },
    { t: 12.4, v: 0.56 },
  ]);
  const laptopX = keys(t, [
    { t: 6, v: 0 },
    { t: 7.6, v: -170 },
  ]);
  const laptopY = keys(t, [
    { t: 0, v: 170 },
    { t: 6, v: 90 },
    { t: 7.6, v: 110 },
  ]);
  const phoneIn = tween(t, 6.0, 7.9, 0, 1, EASE.out);
  const devicesOut = tween(t, 11.9, 12.5, 0, 1, EASE.in);

  return (
    <AbsoluteFill>
      <Backdrop glow={0.55 + 0.45 * power} y={55} />

      {/* Devices */}
      <AbsoluteFill style={{ opacity: 1 - devicesOut, filter: `blur(${devicesOut * 18}px)`, scale: String(1 + devicesOut * 0.06) }}>
        <div style={{ position: "absolute", left: 960 + laptopX, top: 540 + laptopY, scale: String(laptopScale) }}>
          <Laptop open={open} power={power} sweep={tween(t, 3.4, 5.4)} tilt={7}>
            <Workspace s={DONE_STATE} />
          </Laptop>
        </div>
        <div
          style={{
            position: "absolute",
            left: 1440 + (1 - phoneIn) * 300,
            top: 580,
            scale: String(0.62),
            opacity: phoneIn,
            transform: `perspective(2000px) rotateY(${-55 * (1 - phoneIn) - 14}deg) rotateZ(${(1 - phoneIn) * 6}deg)`,
          }}
        >
          <Phone sweep={tween(t, 8.2, 9.8)}>
            <PhoneTicket />
          </Phone>
        </div>
        <Center style={{ justifyContent: "flex-start", paddingTop: 96 }}>
          <div style={inOut(t, 1.2, 5.9)}>
            <Eyebrow style={{ textAlign: "center" }}>Meet Kairos</Eyebrow>
            <BigLine size={76} style={{ marginTop: 18, fontWeight: 700 }}>
              Next Best Action.
            </BigLine>
          </div>
        </Center>
        <Center style={{ justifyContent: "flex-start", paddingTop: 120 }}>
          <div style={inOut(t, 6.6, 12.0)}>
            <BigLine size={80} style={{ fontWeight: 700 }}>
              One view. <span style={{ color: C.peri, WebkitTextFillColor: C.peri }}>Every signal.</span>
            </BigLine>
          </div>
        </Center>
      </AbsoluteFill>

      {/* Signal chips (12.4–18.2) */}
      <Center style={{ opacity: tween(t, 12.2, 12.6) * (1 - tween(t, 17.8, 18.25, 0, 1, EASE.in)), gap: 56 }}>
        <div style={{ display: "flex", gap: 26 }}>
          {CHIPS.map((c) => {
            const on = tween(t, c.at, c.at + 0.35);
            const Icon = c.icon;
            return (
              <div
                key={c.label}
                style={{
                  width: 272,
                  height: 250,
                  borderRadius: 36,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 26,
                  background: `linear-gradient(160deg, rgba(74,59,255,${0.12 + 0.5 * on}) 0%, rgba(19,0,154,${0.2 + 0.4 * on}) 100%)`,
                  border: `2px solid rgba(157,180,247,${0.18 + 0.5 * on})`,
                  boxShadow: `0 0 ${80 * on}px rgba(74,59,255,${0.55 * on}), inset 0 1px 0 rgba(255,255,255,${0.25 * on})`,
                  scale: String(0.92 + 0.08 * on + 0.04 * Math.sin(on * Math.PI)),
                  opacity: 0.35 + 0.65 * on,
                }}
              >
                <div style={{ width: 92, height: 92, borderRadius: 28, display: "grid", placeItems: "center", background: on > 0.5 ? C.orange : "rgba(255,255,255,0.08)", boxShadow: on > 0.5 ? `0 0 40px rgba(255,98,0,${0.6 * on})` : undefined }}>
                  <Icon size={48} color="#fff" strokeWidth={1.8} />
                </div>
                <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 30, color: "#fff", letterSpacing: "-0.01em" }}>{c.label}</div>
              </div>
            );
          })}
        </div>
        <div style={{ ...inOut(t, 15.9, 17.9), fontFamily: F.display, fontWeight: 600, fontSize: 52, color: C.peri, letterSpacing: "-0.01em" }}>All checked at once.</div>
      </Center>

      {/* Three big-type cuts (18.3–25) */}
      {t >= 18.3 && t < 19.76 && (
        <Center style={{ scale: String(1.06 - 0.06 * tween(t, 18.3, 18.9)) }}>
          <BigLine size={190}>Root cause.</BigLine>
        </Center>
      )}
      {t >= 19.76 && t < 20.99 && (
        <Center style={{ scale: String(1.06 - 0.06 * tween(t, 19.76, 20.3)) }}>
          <BigLine size={190}>Next best action.</BigLine>
        </Center>
      )}
      {t >= 20.99 && (
        <Center
          style={{
            scale: String(1.06 - 0.06 * tween(t, 20.99, 21.6) + 0.12 * tween(t, 23.4, 25, 0, 1, EASE.in)),
            opacity: 1 - tween(t, 24.2, 25, 0, 1, EASE.in),
            filter: `blur(${tween(t, 24.2, 25, 0, 14, EASE.in)}px)`,
          }}
        >
          <BigLine size={190} accent>
            Right upgrade.
          </BigLine>
        </Center>
      )}
    </AbsoluteFill>
  );
};

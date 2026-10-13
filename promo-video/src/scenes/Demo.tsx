import type React from "react";
import { AbsoluteFill } from "remotion";
import { Backdrop } from "../components/Backdrop";
import { Laptop, Phone } from "../components/Devices";
import { focus, PhoneLock, PhoneUpsell, QueueScreen, Workspace } from "../components/KairosUi";
import { BigLine, Center, LowerThird } from "../components/Type";
import { C, F } from "../theme";
import { EASE, keys, tween, useSeconds } from "../motion";

const L = 0.92; // laptop base scale in this act

type Cam = { t: number; s: number; x: number; y: number };
const cam = (t: number, x: number, y: number, s: number): Cam => ({ t, ...focus(x, y, s, L) });

const SHOTS: Cam[] = [
  cam(2.6, 720, 450, 1),
  cam(3.6, 720, 450, 1),
  cam(5.4, 640, 430, 1.18),
  cam(7.4, 640, 430, 1.22),
  cam(8.1, 720, 450, 1),
  cam(9.0, 720, 450, 1),
  cam(10.6, 1196, 340, 1.68),
  cam(21.6, 1196, 350, 1.74),
  cam(23.2, 1196, 560, 1.95),
  cam(28.2, 1196, 565, 2.0),
  cam(30.0, 720, 450, 1),
  cam(34.8, 720, 430, 1.06),
  cam(36.4, 492, 752, 1.62),
  cam(48.6, 520, 752, 1.66),
  cam(50.2, 1010, 450, 0.78),
  cam(61.6, 1010, 450, 0.8),
  cam(63.0, 640, 330, 1.42),
  cam(70, 640, 330, 1.5),
];

const camAt = (t: number) => ({
  s: keys(t, SHOTS.map((k) => ({ t: k.t, v: k.s }))),
  x: keys(t, SHOTS.map((k) => ({ t: k.t, v: k.x }))),
  y: keys(t, SHOTS.map((k) => ({ t: k.t, v: k.y }))),
});

/** Act 4 (1:00–2:10): one real ticket, start to finish. Local 0–70 s. */
export const Demo: React.FC<{ rootCauseSeconds: number }> = ({ rootCauseSeconds }) => {
  const t = useSeconds();
  const c = camAt(t);

  // Phone notification shot
  const buzz = (at: number) => (t >= at && t < at + 0.42 ? Math.sin((t - at) * 120) * 3 * (1 - (t - at) / 0.42) : 0);
  const phoneExit = tween(t, 2.4, 3.2, 0, 1, EASE.in);
  const laptopIn = tween(t, 2.6, 3.6, 0, 1, EASE.out);

  const checksT = t >= 8 ? t - 8 : -1;
  const timer = t < 8 ? 0 : Math.min(t - 8, 14) * (rootCauseSeconds / 14);
  const state = {
    checksT,
    timer,
    rootCause: tween(t, 22.0, 22.6),
    nba: tween(t, 35.6, 37.8, 0, 1, EASE.soft),
    reboot: t < 40.4 ? 0 : t < 43.2 ? (t - 40.4) / 2.8 : 1,
    upsell: tween(t, 50.4, 51.2),
    verified: tween(t, 62.4, 63.0),
  };
  const workspaceIn = tween(t, 7.6, 8.1);

  const upsellPhone = tween(t, 50.2, 51.8, 0, 1, EASE.out) * (1 - tween(t, 61.4, 62.2, 0, 1, EASE.in));
  const rcOverlay = tween(t, 23.0, 23.5) * (1 - tween(t, 27.9, 28.4, 0, 1, EASE.in));
  const fixed = tween(t, 63.4, 64.0);
  const end = tween(t, 69.3, 70, 0, 1, EASE.in);
  const mm = Math.floor(rootCauseSeconds / 60);
  const ss = String(Math.round(rootCauseSeconds % 60)).padStart(2, "0");

  return (
    <AbsoluteFill>
      <Backdrop glow={0.75} warm={upsellPhone * 0.8} y={50} />

      {/* Laptop with camera */}
      <AbsoluteFill style={{ opacity: laptopIn * (1 - end), filter: `blur(${Math.max(rcOverlay * 12, fixed * 16)}px) brightness(${1 - Math.max(rcOverlay, fixed) * 0.72})` }}>
        <div style={{ position: "absolute", left: 960, top: 540 + (1 - laptopIn) * 300, translate: `${c.x}px ${c.y}px`, scale: String(c.s) }}>
          <div style={{ scale: String(L) }}>
            <Laptop open={1} tilt={4}>
              <QueueScreen rowIn={tween(t, 3.0, 3.9, 0, 1, EASE.out)} press={tween(t, 6.1, 6.4) * (1 - tween(t, 7.4, 7.7))} />
              {/* cursor */}
              {t < 7.8 && (
                <svg
                  width={28}
                  height={36}
                  viewBox="0 0 28 36"
                  style={{
                    position: "absolute",
                    left: keys(t, [{ t: 4.6, v: 1100 }, { t: 5.9, v: 560 }]),
                    top: keys(t, [{ t: 4.6, v: 760 }, { t: 5.9, v: 412 }]),
                    scale: String(t > 6.05 && t < 6.35 ? 0.85 : 1),
                    opacity: tween(t, 4.4, 4.7),
                    filter: "drop-shadow(0 4px 6px rgba(0,0,0,0.3))",
                  }}
                >
                  <path d="M2 2 L2 28 L9 21 L14 33 L19 31 L14 19 L24 19 Z" fill="#111" stroke="#fff" strokeWidth={2} strokeLinejoin="round" />
                </svg>
              )}
              <div style={{ position: "absolute", inset: 0, opacity: workspaceIn }}>
                {workspaceIn > 0 && <Workspace s={state} />}
              </div>
            </Laptop>
          </div>
        </div>
      </AbsoluteFill>

      {/* Upsell phone */}
      {upsellPhone > 0 && (
        <div
          style={{
            position: "absolute",
            left: 1530 + (1 - upsellPhone) * 320,
            top: 560,
            scale: String(0.78),
            opacity: upsellPhone,
            transform: `perspective(2000px) rotateY(${-40 * (1 - upsellPhone) - 10}deg)`,
          }}
        >
          <Phone sweep={tween(t, 52.0, 53.6)}>
            <PhoneUpsell t={t} />
          </Phone>
        </div>
      )}

      {/* Phone notification */}
      {phoneExit < 1 && (
        <div
          style={{
            position: "absolute",
            left: 960 - phoneExit * 760,
            top: 560,
            scale: String(1.08 - phoneExit * 0.4),
            rotate: `${buzz(0) + buzz(0.55)}deg`,
            opacity: tween(t, 0, 0.25) * (1 - phoneExit),
            filter: `blur(${phoneExit * 16}px)`,
          }}
        >
          <Phone>
            <PhoneLock notif={tween(t, 0.15, 0.75)} />
          </Phone>
        </div>
      )}

      <AbsoluteFill style={{ background: C.inkDeep, opacity: Math.max(rcOverlay, fixed * (1 - end)) * 0.35, pointerEvents: "none" }} />
      {rcOverlay > 0 && (
        <Center style={{ opacity: rcOverlay, gap: 26 }}>
          <div style={{ fontFamily: F.display, fontSize: 40, fontWeight: 700, letterSpacing: "0.3em", color: C.orange, opacity: tween(t, 23.0, 23.5) }}>ROOT CAUSE FOUND</div>
          <div style={{ position: "relative", opacity: tween(t, 24.2, 24.6), fontFamily: F.display, fontWeight: 600, fontSize: 64, color: C.peri }}>
            Not 20–25 minutes.
            <div style={{ position: "absolute", left: -10, top: "52%", height: 6, borderRadius: 3, background: C.orange, width: `${tween(t, 24.8, 25.3, 0, 104, EASE.inOut)}%` }} />
          </div>
          <div style={{ opacity: tween(t, 25.6, 25.9), scale: String(1.15 - 0.15 * tween(t, 25.6, 26.2)) }}>
            <BigLine size={260} accent style={{ fontVariantNumeric: "tabular-nums" }}>
              {mm}:{ss}
            </BigLine>
          </div>
        </Center>
      )}

      {/* Fixed. First visit. */}
      {fixed > 0 && (
        <Center style={{ opacity: 1 - end, gap: 10 }}>
          <div style={{ opacity: fixed, scale: String(1.08 - 0.08 * fixed) }}>
            <BigLine size={200}>Fixed.</BigLine>
          </div>
          <div style={{ opacity: tween(t, 64.3, 64.9), scale: String(1.08 - 0.08 * tween(t, 64.3, 64.9)) }}>
            <BigLine size={120} accent>
              First visit.
            </BigLine>
          </div>
        </Center>
      )}

      <LowerThird t={t} from={0.6} to={30} />
    </AbsoluteFill>
  );
};

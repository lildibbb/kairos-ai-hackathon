import type React from "react";
import { C } from "../theme";

export const SCREEN_W = 1440;
export const SCREEN_H = 900;
const BEZEL = 18;
const LID_W = SCREEN_W + BEZEL * 2;
const LID_H = SCREEN_H + BEZEL * 2;

type LaptopProps = {
  /** 0 = closed, 1 = fully open. */
  open: number;
  /** 0..1 screen brightness (power-on). */
  power?: number;
  /** Extra light sweep position across the lid edge, 0..1 (outside range hides it). */
  sweep?: number;
  tilt?: number;
  children: React.ReactNode;
};

/**
 * CSS-3D laptop. The lid's screen centre sits at the component's origin, so
 * content point (x, y) maps to ((x - 720) * scale, (y - 450) * scale).
 */
export const Laptop: React.FC<LaptopProps> = ({ open, power = 1, sweep = -1, tilt = 6, children }) => {
  const lidAngle = -92 * (1 - open);
  const deckW = LID_W * 1.1;
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: 0, height: 0 }}>
      <div style={{ position: "absolute", left: 0, top: 0, translate: `0px ${-tilt}px` }}>
        {/* Keyboard deck, drawn flat in 2D so it can never sort in front of the screen */}
        <div
          style={{
            position: "absolute",
            left: -deckW / 2,
            top: LID_H / 2 - 6,
            width: deckW,
            height: 70,
            clipPath: "polygon(4.5% 0, 95.5% 0, 100% 100%, 0 100%)",
            background: "linear-gradient(180deg, #1a1b25 0%, #2b2d3b 70%, #3a3c4c 100%)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: "12%",
              right: "12%",
              top: 10,
              height: 40,
              backgroundImage: "linear-gradient(90deg, rgba(0,0,0,0.5) 2px, transparent 2px), linear-gradient(0deg, rgba(0,0,0,0.5) 2px, transparent 2px)",
              backgroundSize: "60px 9px",
              opacity: 0.7,
            }}
          />
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: `radial-gradient(60% 140% at 50% 0%, rgba(140,150,255,${0.55 * open * power}) 0%, rgba(26,0,230,${0.2 * open * power}) 45%, transparent 80%)`,
              mixBlendMode: "screen",
            }}
          />
        </div>
        {/* Front lip of the base */}
        <div
          style={{
            position: "absolute",
            left: -deckW / 2,
            top: LID_H / 2 + 62,
            width: deckW,
            height: 20,
            borderRadius: "0 0 26px 26px",
            background: "linear-gradient(180deg, #5a5d6e 0%, #23242e 100%)",
            boxShadow: "0 30px 60px rgba(0,0,0,0.5)",
          }}
        />
        {/* Lid */}
        <div
          style={{
            position: "absolute",
            left: -LID_W / 2,
            top: -LID_H / 2,
            width: LID_W,
            height: LID_H,
            transformOrigin: "50% 100%",
            transform: `perspective(3200px) rotateX(${lidAngle}deg)`,
            transformStyle: "preserve-3d",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: 34,
              background: "#0a0a10",
              boxShadow: "0 0 0 3px #3b3d4a, 0 40px 120px rgba(0,0,0,0.55)",
              backfaceVisibility: "hidden",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                left: BEZEL,
                top: BEZEL,
                width: SCREEN_W,
                height: SCREEN_H,
                borderRadius: 12,
                overflow: "hidden",
                background: "#000",
              }}
            >
              <div style={{ position: "absolute", inset: 0, opacity: power }}>{children}</div>
              {/* Glass reflection */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background: "linear-gradient(115deg, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.02) 28%, transparent 40%)",
                  pointerEvents: "none",
                }}
              />
            </div>
            {/* Camera notch */}
            <div style={{ position: "absolute", left: "50%", top: 0, width: 180, height: 26, marginLeft: -90, borderRadius: "0 0 14px 14px", background: "#0a0a10" }} />
            {sweep >= 0 && sweep <= 1 && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background: `linear-gradient(105deg, transparent ${sweep * 140 - 30}%, rgba(255,255,255,0.35) ${sweep * 140 - 20}%, transparent ${sweep * 140 - 10}%)`,
                  mixBlendMode: "screen",
                }}
              />
            )}
          </div>
          {/* Lid back (visible while closed) */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: 34,
              transform: "rotateY(180deg)",
              backfaceVisibility: "hidden",
              background: "linear-gradient(160deg, #5b5e6e, #2a2b36)",
            }}
          />
        </div>
      </div>
    </div>
  );
};

export const PHONE_W = 400;
export const PHONE_H = 866;

type PhoneProps = {
  children: React.ReactNode;
  sweep?: number;
  style?: React.CSSProperties;
};

/** iPhone-style frame. Screen content is authored at 400 x 866. Centred on its origin. */
export const Phone: React.FC<PhoneProps> = ({ children, sweep = -1, style }) => {
  const frame = 16;
  return (
    <div
      style={{
        position: "absolute",
        left: -(PHONE_W / 2 + frame),
        top: -(PHONE_H / 2 + frame),
        width: PHONE_W + frame * 2,
        height: PHONE_H + frame * 2,
        borderRadius: 78,
        background: "linear-gradient(145deg, #8d90a0 0%, #3b3d48 30%, #1d1e26 60%, #6d7080 100%)",
        padding: 3,
        boxShadow: "0 60px 140px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.08)",
        ...style,
      }}
    >
      <div style={{ position: "absolute", inset: 3, borderRadius: 75, background: "#050508" }} />
      <div
        style={{
          position: "absolute",
          left: frame,
          top: frame,
          width: PHONE_W,
          height: PHONE_H,
          borderRadius: 62,
          overflow: "hidden",
          background: C.paper,
        }}
      >
        {children}
        {/* Dynamic island */}
        <div style={{ position: "absolute", left: "50%", top: 14, width: 124, height: 36, marginLeft: -62, borderRadius: 20, background: "#000" }} />
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(120deg, rgba(255,255,255,0.14) 0%, transparent 35%)" }} />
      </div>
      {sweep >= 0 && sweep <= 1 && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: 78,
            background: `linear-gradient(110deg, transparent ${sweep * 140 - 30}%, rgba(255,255,255,0.5) ${sweep * 140 - 22}%, transparent ${sweep * 140 - 14}%)`,
            mixBlendMode: "screen",
          }}
        />
      )}
    </div>
  );
};

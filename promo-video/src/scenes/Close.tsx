import type React from "react";
import { AbsoluteFill } from "remotion";
import { Database, Home, MessageCircle, Star, Users } from "lucide-react";
import { Backdrop } from "../components/Backdrop";
import { KairosMark } from "../components/KairosUi";
import { BigLine, Center, Eyebrow } from "../components/Type";
import { C, F } from "../theme";
import { EASE, inOut, tween, useSeconds } from "../motion";

const TILES = [
  { icon: Home, channel: "MyUnifi App", title: "EasyFix: guided self-repair", body: "Customers fix common faults in the app first.", ux: "Fix in minutes", cost: "Fewer calls", at: 2.6 },
  { icon: Users, channel: "Call Center", title: "Next best action on the call", body: "Agents see the root cause on answer.", ux: "Shorter calls", cost: "Fewer truck rolls", at: 3.0 },
  { icon: MessageCircle, channel: "FB Live Chat", title: "AI first response, 24/7", body: "AI and agents reply instantly, any hour.", ux: "No waiting", cost: "Fewer agent hours", at: 3.4 },
  { icon: Star, channel: "Unifi Store", title: "The right offer, right moment", body: "Upgrade advice based on the real fault.", ux: "Right advice", cost: "Fewer revisits", at: 3.8 },
];

const TEAM = ["Adib", "Afif", "Jason", "Irwan"];

/** Act 6 (2:30–2:55): every channel, end card, team. Local 0–25 s. */
export const Close: React.FC = () => {
  const t = useSeconds();
  const channelsOut = tween(t, 11.4, 12, 0, 1, EASE.in);
  const card = tween(t, 12.0, 13.0);
  const sweep = tween(t, 12.4, 14.2, 0, 1, EASE.inOut);
  const lift = tween(t, 19.8, 21.0, 0, 1, EASE.inOut);
  const black = tween(t, 23.6, 25, 0, 1, EASE.in);
  return (
    <AbsoluteFill>
      <Backdrop glow={0.6 + card * 0.5} warm={card * 0.5} />

      {t < 12 && (
        <AbsoluteFill style={{ opacity: 1 - channelsOut, filter: `blur(${channelsOut * 14}px)` }}>
          <div style={{ position: "absolute", left: 140, top: 96, ...inOut(t, 0.2, 99) }}>
            <Eyebrow style={{ fontSize: 24 }}>Future implementation</Eyebrow>
            <div style={{ fontFamily: F.display, fontWeight: 800, fontSize: 76, color: "#fff", letterSpacing: "-0.03em", marginTop: 12 }}>One engine. Every channel.</div>
          </div>
          {/* Engine bar */}
          <div
            style={{
              position: "absolute",
              left: 140,
              right: 140,
              top: 330,
              height: 104,
              borderRadius: 26,
              background: `linear-gradient(100deg, ${C.blue}, ${C.glow})`,
              boxShadow: `0 0 ${60 + 20 * Math.sin(t * 3)}px rgba(74,59,255,0.7)`,
              display: "flex",
              alignItems: "center",
              padding: "0 38px",
              gap: 20,
              opacity: tween(t, 0.6, 1.2),
              scale: `${0.92 + 0.08 * tween(t, 0.6, 1.4)} 1`,
            }}
          >
            <Database size={42} color={C.orange} />
            <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 38, color: "#fff" }}>NBA database + AI engine</div>
            <div style={{ flex: 1 }} />
            <div style={{ fontFamily: F.ui, fontSize: 24, color: C.peri }}>Built for the field team. Ready for every channel.</div>
          </div>
          {TILES.map((tile, i) => {
            const d = tween(t, tile.at, tile.at + 0.55, 0, 1, EASE.out);
            const Icon = tile.icon;
            const x = 140 + i * 418;
            return (
              <div key={tile.channel}>
                <div style={{ position: "absolute", left: x + 195, top: 434, width: 4, height: 70 * tween(t, tile.at - 0.3, tile.at), background: C.orange, borderRadius: 2 }} />
                <div
                  style={{
                    position: "absolute",
                    left: x,
                    top: 504,
                    width: 390,
                    height: 372,
                    borderRadius: 28,
                    background: i === 0 ? "rgba(255,98,0,0.12)" : "rgba(255,255,255,0.06)",
                    border: `2px solid ${i === 0 ? C.orange : "rgba(157,180,247,0.3)"}`,
                    padding: 32,
                    boxSizing: "border-box",
                    opacity: d,
                    translate: `0px ${(1 - d) * -90}px`,
                    backdropFilter: "blur(10px)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <Icon size={30} color={C.peri} />
                    <div style={{ fontFamily: F.ui, fontWeight: 700, fontSize: 24, color: C.peri }}>{tile.channel}</div>
                  </div>
                  <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 36, color: "#fff", marginTop: 22, lineHeight: 1.12 }}>{tile.title}</div>
                  <div style={{ fontFamily: F.ui, fontSize: 22, color: "rgba(255,255,255,0.75)", marginTop: 14, lineHeight: 1.4 }}>{tile.body}</div>
                  <div style={{ position: "absolute", left: 32, bottom: 30, display: "flex", flexDirection: "column", gap: 10 }}>
                    {[
                      ["UX", tile.ux, C.blue],
                      ["COST", tile.cost, C.orange],
                    ].map(([k, v, bg]) => (
                      <div key={k} style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: F.ui, fontSize: 21, color: "#fff", fontWeight: 600 }}>
                        <span style={{ background: bg, borderRadius: 8, padding: "4px 10px", fontSize: 16, fontWeight: 800, letterSpacing: "0.06em" }}>{k}</span>
                        {v}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </AbsoluteFill>
      )}

      {t >= 12 && (
        <Center style={{ opacity: card * (1 - black), translate: `0px ${-150 * lift}px`, scale: String(1.06 - 0.06 * card - 0.12 * lift), gap: 30 }}>
          <div style={{ filter: `drop-shadow(0 0 60px rgba(74,59,255,0.9))` }}>
            <KairosMark size={170} ring={C.blue} />
          </div>
          <div style={{ position: "relative" }}>
            <Eyebrow style={{ fontSize: 40, letterSpacing: "0.5em", marginRight: "-0.5em", textAlign: "center" }}>Kairos</Eyebrow>
          </div>
          <div style={{ position: "relative" }}>
            <BigLine size={140} style={{ letterSpacing: "0.08em", fontWeight: 800 }}>
              NEXT BEST ACTION
            </BigLine>
            <div
              style={{
                position: "absolute",
                inset: 0,
                fontFamily: F.display,
                fontWeight: 800,
                fontSize: 140,
                lineHeight: 1,
                letterSpacing: "0.08em",
                textAlign: "center",
                backgroundImage: `linear-gradient(100deg, transparent ${sweep * 160 - 40}%, #fff ${sweep * 160 - 25}%, rgba(255,160,90,0.95) ${sweep * 160 - 18}%, transparent ${sweep * 160 - 5}%)`,
                WebkitBackgroundClip: "text",
                backgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              NEXT BEST ACTION
            </div>
          </div>
          <div style={{ ...inOut(t, 13.4, 99), fontFamily: F.display, fontStyle: "italic", fontWeight: 600, fontSize: 50, color: C.orange }}>Know the next move, even before you arrive.</div>
        </Center>
      )}

      {t >= 19.8 && (
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 190, opacity: 1 - black }}>
          <div style={{ display: "flex", alignItems: "center", gap: 64 }}>
            <div style={{ ...inOut(t, 20.0, 99), fontFamily: F.ui, fontWeight: 700, fontSize: 24, letterSpacing: "0.3em", color: C.orange }}>TEAM</div>
            {TEAM.map((name, i) => (
              <div key={name} style={{ ...inOut(t, 20.4 + i * 0.35, 99), fontFamily: F.display, fontWeight: 700, fontSize: 52, color: "#fff" }}>
                {name}
              </div>
            ))}
          </div>
        </AbsoluteFill>
      )}

      <AbsoluteFill style={{ background: "#000", opacity: black }} />
    </AbsoluteFill>
  );
};

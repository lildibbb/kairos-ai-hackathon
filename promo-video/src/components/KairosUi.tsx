/**
 * Kairos-themed rebuild of the field app screens (frontend/src/features/work):
 * AssignedWorkList (queue), TicketHeader, IncidentTrace, topology panel,
 * assistant investigation drawer and NextBestActionPanel.
 *
 * Values come from one real seeded customer (backend/app/*.csv, login
 * gohsoonhua567@unifi) with personal details masked: router CPU 86 %, memory
 * 85 %, 41 C, ZTE AX3000, optical RX -20.2 dBm, 704 GB/month, 500 Mbps plan,
 * 8 client devices of which 2 are below -80 dBm (worst Pixel-7 at -84 dBm).
 */
import type React from "react";
import { Check, ChevronRight, Cpu, Gauge, Radio, Router, Search, SlidersHorizontal, Smartphone, Wifi, Zap } from "lucide-react";
import { C, F } from "../theme";

export const TICKET = {
  no: "INC-0912",
  summary: "Internet slow, Wi-Fi keeps dropping",
  customer: "Sample household",
  login: "g••••••567@unifi",
  area: "Selangor",
  received: "09:12",
  visit: "13 Oct, 10:30–12:30",
  plan: "Unifi 500Mbps",
  router: "ZTE AX3000",
};

export const CHECKS = [
  { icon: Cpu, name: "Router health", detail: "CPU 86% · memory 85% · 41°C", status: "High", bad: true },
  { icon: Wifi, name: "Wi-Fi signal", detail: "2 of 8 devices below −80 dBm · worst −84", status: "Weak", bad: true },
  { icon: Radio, name: "Fibre signal", detail: "Optical RX −20.2 dBm", status: "Normal", bad: false },
  { icon: Smartphone, name: "Connected devices", detail: "8 clients · 4 IoT", status: "OK", bad: false },
  { icon: Gauge, name: "Data usage", detail: "704 GB this month · 500 Mbps plan", status: "Normal", bad: false },
];

// ---------- primitives ----------

export const KairosMark: React.FC<{ size?: number; ring?: string }> = ({ size = 40, ring = C.indigo }) => (
  <svg width={size} height={size} viewBox="0 0 100 100">
    <circle cx="50" cy="50" r="50" fill={ring} />
    <path d="M24 40 a36 36 0 0 1 52 0" stroke={C.orange} strokeWidth="7" fill="none" strokeLinecap="round" />
    <path d="M33 49 a24 24 0 0 1 34 0" stroke={C.peri} strokeWidth="7" fill="none" strokeLinecap="round" />
    <path d="M42 57 a11 11 0 0 1 16 0" stroke="#fff" strokeWidth="7" fill="none" strokeLinecap="round" />
    <path d="M50 92 C 40 80 34 74 34 67 a16 16 0 0 1 32 0 c0 7 -6 13 -16 25z" fill={C.orange} />
    <path d="M43 67 l5 5 l9 -9" stroke="#fff" strokeWidth="5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const Label: React.FC<{ children: React.ReactNode; color?: string; style?: React.CSSProperties }> = ({ children, color = C.orange, style }) => (
  <div style={{ fontFamily: F.ui, fontSize: 12, fontWeight: 700, letterSpacing: "0.16em", textTransform: "uppercase", color, ...style }}>{children}</div>
);

type Tone = "high" | "open" | "progress" | "resolved" | "medium" | "low" | "remote" | "site" | "new";
const TONES: Record<Tone, [string, string]> = {
  high: ["#FFE7E2", "#C2321B"],
  medium: [C.amberSoft, C.amber],
  low: ["#EEF1FA", C.muted],
  open: ["#E8ECFF", C.blue],
  progress: [C.amberSoft, C.amber],
  resolved: [C.greenSoft, C.green],
  remote: ["#E8ECFF", C.blue],
  site: [C.amberSoft, C.amber],
  new: [C.orange, "#fff"],
};

export const Pill: React.FC<{ tone: Tone; children: React.ReactNode; style?: React.CSSProperties }> = ({ tone, children, style }) => (
  <span
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "5px 11px",
      borderRadius: 999,
      fontFamily: F.ui,
      fontSize: 12.5,
      fontWeight: 650,
      background: TONES[tone][0],
      color: TONES[tone][1],
      whiteSpace: "nowrap",
      ...style,
    }}
  >
    {children}
  </span>
);

const Card: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ position: "absolute", background: "#fff", borderRadius: 18, boxShadow: "0 1px 0 rgba(11,10,46,0.04), 0 10px 30px rgba(19,0,154,0.06)", border: `1px solid ${C.line}`, ...style }}>
    {children}
  </div>
);

const Spinner: React.FC<{ t: number; size?: number; color?: string }> = ({ t, size = 22, color = C.blue }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" style={{ rotate: `${t * 400}deg` }}>
    <circle cx="12" cy="12" r="9" stroke="#E3E8F8" strokeWidth="3" fill="none" />
    <path d="M12 3 a9 9 0 0 1 9 9" stroke={color} strokeWidth="3" fill="none" strokeLinecap="round" />
  </svg>
);

const AppNav: React.FC<{ section: string }> = ({ section }) => (
  <div style={{ position: "absolute", left: 0, top: 0, right: 0, height: 60, background: C.ink, display: "flex", alignItems: "center", padding: "0 28px", gap: 14 }}>
    <KairosMark size={34} ring={C.blue} />
    <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 19, color: "#fff", letterSpacing: "0.12em" }}>KAIROS</div>
    <div style={{ width: 1, height: 22, background: "rgba(255,255,255,0.2)", margin: "0 6px" }} />
    <div style={{ fontFamily: F.ui, fontSize: 14, color: C.peri }}>{section}</div>
    <div style={{ flex: 1 }} />
    <div style={{ fontFamily: F.ui, fontSize: 13, color: C.peri }}>Demo Technician</div>
    <div style={{ width: 32, height: 32, borderRadius: 16, background: C.orange, color: "#fff", fontFamily: F.ui, fontWeight: 700, fontSize: 13, display: "grid", placeItems: "center" }}>DT</div>
  </div>
);

// ---------- Queue (AssignedWorkList) ----------

const ROWS: Array<{ no: string; summary: string; who: string; visit: string; status: Tone; statusText: string; sev: Tone; sevText: string }> = [
  { no: "INC-0907", summary: "No internet, LOS light red", who: "Sample customer B", visit: "13 Oct, 09:00–11:00", status: "progress", statusText: "In progress", sev: "high", sevText: "High" },
  { no: "INC-0901", summary: "IPTV buffering at night", who: "Sample customer C", visit: "13 Oct, 14:00–16:00", status: "open", statusText: "Open", sev: "medium", sevText: "Medium" },
  { no: "INC-0894", summary: "Voice line has no dial tone", who: "Sample customer D", visit: "No visit booked", status: "open", statusText: "Open", sev: "medium", sevText: "Medium" },
  { no: "INC-0889", summary: "Slow speed on 5 GHz only", who: "Sample customer E", visit: "14 Oct, 10:00–12:00", status: "open", statusText: "Open", sev: "low", sevText: "Low" },
  { no: "INC-0876", summary: "Router restarts on its own", who: "Sample customer F", visit: "14 Oct, 15:00–17:00", status: "open", statusText: "Open", sev: "medium", sevText: "Medium" },
];

const Row: React.FC<{ r: (typeof ROWS)[number] & { isNew?: boolean }; y: number; highlight?: number; opacity?: number }> = ({ r, y, highlight = 0, opacity = 1 }) => (
  <div
    style={{
      position: "absolute",
      left: 0,
      right: 0,
      top: y,
      height: 74,
      display: "grid",
      gridTemplateColumns: "8px 1.6fr 1fr 1fr 130px 110px 70px",
      alignItems: "center",
      gap: 18,
      padding: "0 22px 0 0",
      borderTop: `1px solid ${C.line}`,
      background: `rgba(255,98,0,${0.07 * highlight})`,
      boxShadow: highlight > 0 ? `inset 0 0 0 ${2 * highlight}px rgba(255,98,0,${0.6 * highlight})` : undefined,
      borderRadius: highlight > 0 ? 12 : 0,
      opacity,
      fontFamily: F.ui,
    }}
  >
    <div style={{ height: 44, borderRadius: 4, background: r.sev === "high" ? C.orange : r.sev === "medium" ? "#F5B67A" : C.line }} />
    <div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <span style={{ fontSize: 12.5, color: C.muted, fontVariantNumeric: "tabular-nums" }}>{r.no}</span>
        {r.isNew && <Pill tone="new" style={{ padding: "2px 8px", fontSize: 10.5, letterSpacing: "0.08em" }}>NEW</Pill>}
      </div>
      <div style={{ fontSize: 16, fontWeight: 650, color: C.text, marginTop: 3 }}>{r.summary}</div>
    </div>
    <div>
      <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{r.who}</div>
      <div style={{ fontSize: 12.5, color: C.muted }}>{r.isNew ? TICKET.login : "s••••@unifi"}</div>
    </div>
    <div style={{ fontSize: 13, color: C.muted }}>
      <div style={{ fontWeight: 600, color: C.text }}>{r.visit.startsWith("No") ? "" : "Visit"}</div>
      {r.visit}
    </div>
    <Pill tone={r.status}>{r.statusText}</Pill>
    <Pill tone={r.sev}>{r.sevText}</Pill>
    <div style={{ fontSize: 13, fontWeight: 600, color: C.blue, display: "flex", alignItems: "center" }}>
      View <ChevronRight size={15} />
    </div>
  </div>
);

/** rowIn 0..1 slides the new ticket in; press 0..1 shows the click highlight. */
export const QueueScreen: React.FC<{ rowIn: number; press?: number }> = ({ rowIn, press = 0 }) => {
  const count = rowIn > 0.5 ? 6 : 5;
  return (
    <div style={{ position: "absolute", inset: 0, background: C.paper, fontFamily: F.ui }}>
      <AppNav section="Field operations / My queue" />
      <div style={{ position: "absolute", left: 48, top: 92 }}>
        <Label>My queue</Label>
        <div style={{ fontFamily: F.display, fontSize: 44, fontWeight: 700, color: C.text, letterSpacing: "-0.02em", marginTop: 8 }}>Assigned tickets</div>
        <div style={{ fontSize: 16, color: C.muted, marginTop: 6 }}>Your next fix starts here. Pick an incident to investigate.</div>
      </div>
      {[
        ["Assigned now", String(count), true],
        ["High severity", rowIn > 0.5 ? "2" : "1", false],
        ["In progress", "1", false],
      ].map(([label, value, primary], i) => (
        <div
          key={label as string}
          style={{
            position: "absolute",
            top: 98,
            left: 860 + i * 186,
            width: 170,
            height: 104,
            borderRadius: 18,
            background: primary ? C.blue : "#fff",
            border: primary ? "none" : `1px solid ${C.line}`,
            padding: "16px 18px",
            boxSizing: "border-box",
          }}
        >
          <div style={{ fontFamily: F.display, fontSize: 40, fontWeight: 700, color: primary ? "#fff" : C.text, lineHeight: 1 }}>{value}</div>
          <div style={{ fontSize: 13, color: primary ? C.peri : C.muted, marginTop: 10 }}>{label}</div>
        </div>
      ))}
      <div style={{ position: "absolute", left: 48, top: 236, right: 48, display: "flex", alignItems: "center", gap: 10 }}>
        <SlidersHorizontal size={17} color={C.muted} />
        {["All tickets", "High severity", "Open", "In progress"].map((f, i) => (
          <div key={f} style={{ padding: "8px 14px", borderRadius: 999, fontSize: 13.5, fontWeight: 600, background: i === 0 ? C.ink : "#fff", color: i === 0 ? "#fff" : C.text, border: i === 0 ? "none" : `1px solid ${C.line}` }}>
            {f}
          </div>
        ))}
        <div style={{ flex: 1 }} />
        <div style={{ width: 300, height: 40, borderRadius: 12, background: "#fff", border: `1px solid ${C.line}`, display: "flex", alignItems: "center", gap: 8, padding: "0 14px", color: C.muted, fontSize: 14 }}>
          <Search size={16} /> Search tickets
        </div>
      </div>
      <Card style={{ left: 48, right: 48, top: 296, height: 560, overflow: "hidden" }}>
        <div style={{ position: "absolute", left: 24, top: 18 }}>
          <Label color={C.muted}>Work items</Label>
          <div style={{ fontFamily: F.display, fontSize: 21, fontWeight: 700, color: C.text, marginTop: 4 }}>
            Your incidents <span style={{ fontSize: 14, color: C.muted, fontWeight: 500 }}>{count} shown</span>
          </div>
        </div>
        <div style={{ position: "absolute", left: 18, right: 0, top: 84, bottom: 0 }}>
          <div style={{ position: "absolute", left: 0, right: 0, top: 0, translate: `0px ${-74 * (1 - rowIn)}px`, opacity: rowIn }}>
            <Row
              r={{ no: TICKET.no, summary: TICKET.summary, who: TICKET.customer, visit: TICKET.visit, status: "open", statusText: "Open", sev: "high", sevText: "High", isNew: true }}
              y={0}
              highlight={Math.max(rowIn > 0.9 ? 0.5 : 0, press)}
            />
          </div>
          {ROWS.map((r, i) => (
            <Row key={r.no} r={r} y={74 * (i + rowIn)} />
          ))}
        </div>
      </Card>
    </div>
  );
};

// ---------- Workspace (TicketPage) ----------

export type WorkspaceState = {
  /** Seconds since the investigation started (<0 = not started). */
  checksT: number;
  /** Seconds shown on the investigation timer. */
  timer: number;
  rootCause: number;
  nba: number;
  /** 0 idle, 0..1 rebooting, >=1 done. */
  reboot: number;
  upsell: number;
  verified: number;
};

export const checkStart = (i: number) => 0.3 + i * 0.35;
export const checkDone = (i: number) => 2.6 + i * 2.0;

const TraceStep: React.FC<{ n: number; label: string; state: "done" | "current" | "todo"; detail: string; x: number }> = ({ n, label, state, detail, x }) => (
  <div style={{ position: "absolute", left: x, top: 22, width: 170 }}>
    <div
      style={{
        width: 30,
        height: 30,
        borderRadius: 10,
        display: "grid",
        placeItems: "center",
        background: state === "done" ? C.blue : state === "current" ? C.orange : "#fff",
        border: state === "todo" ? `2px dashed ${C.line}` : "none",
        color: state === "todo" ? C.muted : "#fff",
        fontFamily: F.ui,
        fontWeight: 700,
        fontSize: 14,
      }}
    >
      {state === "done" ? <Check size={17} strokeWidth={3} /> : n}
    </div>
    <div style={{ fontFamily: F.ui, fontWeight: 700, fontSize: 15, color: C.text, marginTop: 10 }}>{label}</div>
    <div style={{ fontFamily: F.ui, fontSize: 12.5, color: state === "current" ? C.orange : C.muted, marginTop: 2 }}>{detail}</div>
  </div>
);

const TopoNode: React.FC<{ x: number; y: number; title: string; sub: string; warn?: boolean; icon: React.ReactNode; badge: string }> = ({ x, y, title, sub, warn, icon, badge }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: 190,
      height: 112,
      borderRadius: 16,
      background: warn ? "rgba(255,98,0,0.12)" : "rgba(255,255,255,0.05)",
      border: `1.5px solid ${warn ? C.orange : "rgba(157,180,247,0.35)"}`,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 5,
      fontFamily: F.ui,
      color: "#fff",
    }}
  >
    {icon}
    <div style={{ fontSize: 14, fontWeight: 650 }}>{title}</div>
    <div style={{ fontSize: 11.5, color: C.peri }}>{sub}</div>
    <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: warn ? C.orange : "#7CE3B0" }}>{badge}</div>
  </div>
);

export const Workspace: React.FC<{ s: WorkspaceState }> = ({ s }) => {
  const evidenceDone = s.rootCause > 0.5;
  const actionDone = s.verified > 0.3;
  const routerWarn = s.checksT >= checkDone(0) && !actionDone;
  const mm = Math.floor(s.timer / 60);
  const ss = Math.floor(s.timer % 60);
  return (
    <div style={{ position: "absolute", inset: 0, background: C.paper, fontFamily: F.ui }}>
      <AppNav section="Incident workspace" />

      {/* TicketHeader */}
      <Card style={{ left: 24, top: 80, width: 936, height: 168 }}>
        <div style={{ position: "absolute", left: 26, top: 22, display: "flex", gap: 10, alignItems: "center" }}>
          <Label>Incident workspace</Label>
          <span style={{ fontSize: 12.5, color: C.muted, letterSpacing: "0.08em" }}>/ {TICKET.no}</span>
        </div>
        <div style={{ position: "absolute", right: 24, top: 18, display: "flex", gap: 8 }}>
          <Pill tone={actionDone ? "resolved" : "progress"}>{actionDone ? "Resolved" : "In progress"}</Pill>
          <Pill tone="high">High severity</Pill>
        </div>
        <div style={{ position: "absolute", left: 26, top: 48, fontFamily: F.display, fontSize: 32, fontWeight: 700, color: C.text, letterSpacing: "-0.02em" }}>{TICKET.summary}</div>
        <div style={{ position: "absolute", left: 26, top: 112, display: "flex", gap: 44 }}>
          {[
            ["Customer", `${TICKET.customer} · ${TICKET.login}`],
            ["Received", `Today, ${TICKET.received}`],
            ["Service", TICKET.plan],
            ["Router", TICKET.router],
          ].map(([k, v]) => (
            <div key={k}>
              <div style={{ fontSize: 11.5, fontWeight: 700, color: C.muted, letterSpacing: "0.04em" }}>{k}</div>
              <div style={{ fontSize: 14.5, color: C.text, marginTop: 3 }}>{v}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* IncidentTrace */}
      <Card style={{ left: 24, top: 262, width: 936, height: 116 }}>
        <div style={{ position: "absolute", left: 40, right: 170, top: 37, height: 2, background: C.line }} />
        <TraceStep x={26} n={1} label="Event" state="done" detail="Customer report" />
        <TraceStep x={210} n={2} label="Ticket" state="done" detail="Context loaded" />
        <TraceStep x={394} n={3} label="Topology" state="done" detail="Service path loaded" />
        <TraceStep x={578} n={4} label="Evidence" state={evidenceDone ? "done" : s.checksT >= 0 ? "current" : "todo"} detail={evidenceDone ? "Root cause confirmed" : s.checksT >= 0 ? "Checking 5 signals" : "Not yet confirmed"} />
        <TraceStep x={762} n={5} label="Action" state={actionDone ? "done" : s.nba > 0.5 ? "current" : "todo"} detail={actionDone ? "Fixed, first visit" : s.nba > 0.5 ? "Next best action ready" : "No outcome yet"} />
      </Card>

      {/* Topology */}
      <div style={{ position: "absolute", left: 24, top: 392, width: 936, height: 214, borderRadius: 18, background: `linear-gradient(140deg, ${C.ink}, #0d0660)`, overflow: "hidden" }}>
        <Label color={C.peri} style={{ position: "absolute", left: 26, top: 20 }}>Service path</Label>
        <div style={{ position: "absolute", right: 24, top: 18, fontSize: 12.5, color: C.peri }}>3 devices · 8 clients</div>
        <svg style={{ position: "absolute", left: 0, top: 0 }} width={936} height={214}>
          <line x1={250} y1={128} x2={372} y2={128} stroke={C.peri} strokeOpacity={0.5} strokeWidth={2} strokeDasharray="6 6" strokeDashoffset={-s.checksT * 30} />
          <line x1={562} y1={128} x2={684} y2={128} stroke={routerWarn ? C.orange : C.peri} strokeOpacity={0.7} strokeWidth={2} strokeDasharray="6 6" strokeDashoffset={-s.checksT * 30} />
        </svg>
        <TopoNode x={60} y={72} title="Access node" sub="OLT · Selangor" badge="ONLINE" icon={<Zap size={22} color={C.peri} />} />
        <TopoNode x={372} y={72} title="Fibre ONU" sub="RX −20.2 dBm" badge="ONLINE" icon={<Radio size={22} color={C.peri} />} />
        <TopoNode x={684} y={72} title={TICKET.router} sub={routerWarn ? "CPU 86% · 2 weak clients" : "Home router"} badge={routerWarn ? "DEGRADED" : "ONLINE"} warn={routerWarn} icon={<Router size={22} color={routerWarn ? C.orange : C.peri} />} />
      </div>

      {/* NextBestActionPanel */}
      <Card style={{ left: 24, top: 620, width: 936, height: 260, overflow: "hidden" }}>
        <div style={{ position: "absolute", left: 26, top: 22 }}>
          <Label>Next best action</Label>
          <div style={{ fontSize: 14, color: C.muted, marginTop: 6 }}>
            {s.nba > 0.1 ? "Start remotely. Go on site only if it is still needed." : "Waiting for evidence…"}
          </div>
        </div>
        {[
          { n: 1, title: "Reboot the router", tag: "remote" as Tone, tagText: "Remote", body: "Clears the high CPU load. If it stays high, replace the router." },
          { n: 2, title: "Add a mesh node", tag: "site" as Tone, tagText: "On site", body: "Only if Wi-Fi is still weak after the reboot. Fixes the far rooms." },
        ].map((step, i) => {
          const p = Math.min(1, Math.max(0, (s.nba - i * 0.3) / 0.7));
          return (
            <div
              key={step.n}
              style={{
                position: "absolute",
                left: 26 + i * 452,
                top: 92,
                width: 430,
                height: 146,
                borderRadius: 16,
                border: `1.5px solid ${i === 0 ? C.blue : C.line}`,
                background: i === 0 ? "#F4F5FF" : "#fff",
                padding: 18,
                boxSizing: "border-box",
                opacity: p,
                translate: `0px ${(1 - p) * 20}px`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ width: 30, height: 30, borderRadius: 15, background: i === 0 ? C.blue : C.ink, color: "#fff", display: "grid", placeItems: "center", fontWeight: 700, fontSize: 14 }}>{step.n}</div>
                <div style={{ fontFamily: F.display, fontSize: 20, fontWeight: 700, color: C.text }}>{step.title}</div>
                <Pill tone={step.tag}>{step.tagText}</Pill>
              </div>
              <div style={{ fontSize: 14, color: C.muted, marginTop: 12, lineHeight: 1.45 }}>{step.body}</div>
              {i === 0 && (
                <div
                  style={{
                    position: "absolute",
                    right: 16,
                    bottom: 14,
                    padding: "8px 14px",
                    borderRadius: 10,
                    fontSize: 13.5,
                    fontWeight: 650,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    background: s.reboot >= 1 ? C.greenSoft : C.blue,
                    color: s.reboot >= 1 ? C.green : "#fff",
                  }}
                >
                  {s.reboot <= 0 && "Run remotely"}
                  {s.reboot > 0 && s.reboot < 1 && (
                    <>
                      <Spinner t={s.reboot * 3} size={16} color="#fff" /> Rebooting…
                    </>
                  )}
                  {s.reboot >= 1 && (
                    <>
                      <Check size={16} strokeWidth={3} /> Reboot complete
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </Card>

      {/* Assistant investigation drawer */}
      <div style={{ position: "absolute", left: 976, top: 80, width: 440, height: 800, borderRadius: 18, background: "#fff", border: `1px solid ${C.line}`, boxShadow: "0 20px 60px rgba(19,0,154,0.12)", overflow: "hidden" }}>
        <div style={{ position: "absolute", left: 22, top: 20 }}>
          <Label color={C.muted}>Kairos / Investigation</Label>
          <div style={{ fontFamily: F.display, fontSize: 21, fontWeight: 700, color: C.text, marginTop: 5 }}>Investigate this incident</div>
        </div>
        <div
          style={{
            position: "absolute",
            right: 18,
            top: 22,
            padding: "7px 12px",
            borderRadius: 10,
            background: s.rootCause > 0.5 ? C.orange : C.ink,
            color: "#fff",
            fontFamily: F.display,
            fontWeight: 700,
            fontSize: 18,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {mm}:{String(ss).padStart(2, "0")}
        </div>
        {CHECKS.map((c, i) => {
          const started = s.checksT >= checkStart(i);
          const done = s.checksT >= checkDone(i);
          const pop = Math.min(1, Math.max(0, (s.checksT - checkDone(i)) / 0.35));
          const Icon = c.icon;
          return (
            <div
              key={c.name}
              style={{
                position: "absolute",
                left: 16,
                right: 16,
                top: 92 + i * 74,
                height: 64,
                borderRadius: 14,
                background: done ? (c.bad ? "#FFF4EC" : "#F3FBF7") : "#F6F7FC",
                border: `1px solid ${done ? (c.bad ? "#FFD2B3" : "#C9EEDB") : "#EBEEF8"}`,
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "0 14px",
                opacity: started ? 1 : 0.45,
              }}
            >
              <div style={{ width: 36, height: 36, borderRadius: 10, background: done ? (c.bad ? C.orange : C.green) : C.blue, display: "grid", placeItems: "center", scale: String(1 + 0.15 * Math.sin(pop * Math.PI)) }}>
                <Icon size={19} color="#fff" />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14.5, fontWeight: 650, color: C.text }}>{c.name}</div>
                <div style={{ fontSize: 12, color: C.muted, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{done ? c.detail : started ? "Reading live data…" : "Queued"}</div>
              </div>
              {done ? (
                <span style={{ fontSize: 12, fontWeight: 700, color: c.bad ? C.orange : C.green, opacity: pop }}>{c.status.toUpperCase()}</span>
              ) : started ? (
                <Spinner t={s.checksT} />
              ) : null}
            </div>
          );
        })}
        {/* Root cause */}
        <div
          style={{
            position: "absolute",
            left: 16,
            right: 16,
            top: 470,
            height: 186,
            borderRadius: 16,
            background: C.ink,
            padding: 18,
            boxSizing: "border-box",
            opacity: s.rootCause,
            translate: `0px ${(1 - s.rootCause) * 24}px`,
            boxShadow: `0 0 0 ${3 * s.rootCause}px rgba(255,98,0,0.35)`,
          }}
        >
          <Label>Root cause</Label>
          <div style={{ fontFamily: F.display, fontSize: 22, fontWeight: 700, color: "#fff", marginTop: 8, lineHeight: 1.2 }}>Router overloaded + weak Wi-Fi coverage</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
            {["CPU 86% (limit 65%)", "Pixel-7 at −84 dBm", "2 of 8 devices weak"].map((e) => (
              <span key={e} style={{ fontSize: 12, fontWeight: 600, color: C.peri, background: "rgba(157,180,247,0.14)", padding: "5px 10px", borderRadius: 8 }}>
                {e}
              </span>
            ))}
          </div>
        </div>
        {/* Service suggestion */}
        <div
          style={{
            position: "absolute",
            left: 16,
            right: 16,
            top: 670,
            height: 114,
            borderRadius: 16,
            border: `1.5px solid ${C.orange}`,
            background: "#FFF6EF",
            padding: 16,
            boxSizing: "border-box",
            opacity: s.upsell,
            translate: `0px ${(1 - s.upsell) * 20}px`,
          }}
        >
          <Label>Service suggestion</Label>
          <div style={{ fontFamily: F.display, fontSize: 19, fontWeight: 700, color: C.text, marginTop: 6 }}>Unifi Mesh WiFi</div>
          <div style={{ fontSize: 12.5, color: C.muted, marginTop: 3 }}>Fixes the weak signal. Based on 2 of 8 devices below −80 dBm.</div>
        </div>
      </div>
    </div>
  );
};

/** Focus helper: content point -> stage translation for a camera zoom. */
export const focus = (x: number, y: number, zoom: number, laptopScale: number) => ({
  s: zoom,
  x: -(x - 720) * laptopScale * zoom,
  y: -(y - 450) * laptopScale * zoom,
});

// ---------- Phone screens ----------

export const PhoneLock: React.FC<{ notif: number }> = ({ notif }) => (
  <div style={{ position: "absolute", inset: 0, background: `radial-gradient(120% 80% at 30% 10%, ${C.glow} 0%, ${C.blue} 35%, ${C.ink} 80%)`, fontFamily: F.ui, color: "#fff" }}>
    <div style={{ position: "absolute", top: 120, width: "100%", textAlign: "center", fontSize: 19, fontWeight: 600, opacity: 0.85 }}>Tuesday 13 October</div>
    <div style={{ position: "absolute", top: 142, width: "100%", textAlign: "center", fontFamily: F.display, fontSize: 104, fontWeight: 600, letterSpacing: "-0.02em" }}>09:12</div>
    <div
      style={{
        position: "absolute",
        left: 16,
        right: 16,
        top: 330,
        borderRadius: 26,
        background: "rgba(255,255,255,0.82)",
        backdropFilter: "blur(20px)",
        padding: 16,
        color: C.text,
        opacity: notif,
        translate: `0px ${(1 - notif) * -40}px`,
        scale: String(0.94 + 0.06 * notif),
        boxShadow: "0 20px 50px rgba(0,0,0,0.25)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <KairosMark size={30} ring={C.blue} />
        <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.1em" }}>KAIROS</div>
        <div style={{ flex: 1 }} />
        <div style={{ fontSize: 12, color: C.muted }}>now</div>
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, marginTop: 10 }}>New ticket assigned · {TICKET.no}</div>
      <div style={{ fontSize: 15, marginTop: 4, lineHeight: 1.35 }}>“{TICKET.summary}”</div>
      <div style={{ fontSize: 13, color: C.muted, marginTop: 6 }}>
        {TICKET.area} · Visit {TICKET.visit.split(", ")[1]} · High severity
      </div>
    </div>
  </div>
);

/** Compact technician view used for the reveal and as the phone twin of the workspace. */
export const PhoneTicket: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, background: C.paper, fontFamily: F.ui }}>
    <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 120, background: C.ink }} />
    <div style={{ position: "absolute", left: 22, top: 66, display: "flex", alignItems: "center", gap: 10 }}>
      <KairosMark size={30} ring={C.blue} />
      <div style={{ fontFamily: F.display, fontWeight: 700, color: "#fff", letterSpacing: "0.12em" }}>KAIROS</div>
    </div>
    <div style={{ position: "absolute", left: 16, right: 16, top: 134 }}>
      <Label>{TICKET.no}</Label>
      <div style={{ fontFamily: F.display, fontSize: 25, fontWeight: 700, color: C.text, marginTop: 6, lineHeight: 1.15 }}>{TICKET.summary}</div>
      <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
        <Pill tone="progress">In progress</Pill>
        <Pill tone="high">High</Pill>
      </div>
      <div style={{ marginTop: 16, borderRadius: 18, background: C.ink, padding: 16 }}>
        <Label>Root cause</Label>
        <div style={{ fontFamily: F.display, fontSize: 19, fontWeight: 700, color: "#fff", marginTop: 6 }}>Router overloaded + weak Wi-Fi coverage</div>
        <div style={{ fontSize: 12.5, color: C.peri, marginTop: 8 }}>CPU 86% · 2 of 8 devices below −80 dBm</div>
      </div>
      {CHECKS.slice(0, 3).map((c) => (
        <div key={c.name} style={{ marginTop: 10, borderRadius: 14, background: "#fff", border: `1px solid ${C.line}`, padding: "11px 14px", display: "flex", justifyContent: "space-between" }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{c.name}</span>
          <span style={{ fontSize: 12, fontWeight: 700, color: c.bad ? C.orange : C.green }}>{c.status.toUpperCase()}</span>
        </div>
      ))}
      <div style={{ marginTop: 14, borderRadius: 18, background: "#fff", border: `1.5px solid ${C.blue}`, padding: 14 }}>
        <Label color={C.blue}>Next best action</Label>
        <div style={{ fontSize: 15, fontWeight: 650, color: C.text, marginTop: 8 }}>1. Reboot the router · Remote</div>
        <div style={{ fontSize: 15, fontWeight: 650, color: C.muted, marginTop: 6 }}>2. Add a mesh node · On site</div>
      </div>
    </div>
  </div>
);

/** Customer-facing upsell card the technician shows on the phone. */
export const PhoneUpsell: React.FC<{ t: number }> = ({ t }) => (
  <div style={{ position: "absolute", inset: 0, background: "#fff", fontFamily: F.ui }}>
    <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 420, background: `radial-gradient(90% 80% at 50% 30%, ${C.glow} 0%, ${C.blue} 45%, ${C.ink} 100%)` }}>
      <svg width={400} height={420} style={{ position: "absolute", left: 0, top: 0 }}>
        {[0, 1, 2].map((i) => {
          const r = 60 + ((t * 50 + i * 60) % 180);
          return <circle key={i} cx={200} cy={230} r={r} fill="none" stroke="#fff" strokeOpacity={Math.max(0, 0.5 - r / 400)} strokeWidth={2} />;
        })}
        <rect x={150} y={196} width={100} height={68} rx={22} fill="#fff" />
        <circle cx={185} cy={230} r={6} fill={C.blue} />
        <circle cx={215} cy={230} r={6} fill={C.orange} />
      </svg>
      <div style={{ position: "absolute", left: 24, top: 70 }}>
        <Label color={C.peri}>Recommended for your home</Label>
      </div>
    </div>
    <div style={{ position: "absolute", left: 24, right: 24, top: 448 }}>
      <div style={{ fontFamily: F.display, fontSize: 34, fontWeight: 700, color: C.text, letterSpacing: "-0.02em" }}>Unifi Mesh WiFi</div>
      <div style={{ fontSize: 17, color: C.muted, marginTop: 8, lineHeight: 1.4 }}>Strong Wi-Fi in every room, not just next to the router.</div>
      <div style={{ marginTop: 18, borderRadius: 16, background: C.paper, padding: 14, fontSize: 14, color: C.text, lineHeight: 1.45 }}>
        <b>Why we suggest it:</b> 2 of your devices get a weak signal (as low as −84 dBm).
      </div>
      <div style={{ marginTop: 22, height: 54, borderRadius: 16, background: C.orange, color: "#fff", fontWeight: 700, fontSize: 17, display: "grid", placeItems: "center" }}>Add to my plan</div>
    </div>
  </div>
);

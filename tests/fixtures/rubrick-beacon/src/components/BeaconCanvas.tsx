"use client";
import { useState } from "react";
import BeaconCard from "./BeaconCard";
import DetailPanel from "./DetailPanel";

// The SPINE: a full-bleed central canvas is the stage — a radar field everything overlays.
// Cards float on it; the detail panel and rail dock over it. Central-canvas + overlaid panels.
const SIGNALS = [
  { id: "AX-01", count: 128, status: "LIVE", hue: "var(--signal-live)" },
  { id: "GR-14", count: 42, status: "WARN", hue: "var(--signal-warn)" },
  { id: "AR-09", count: 7, status: "CRIT", hue: "var(--signal-crit)" },
];

export default function BeaconCanvas() {
  const [active, setActive] = useState<typeof SIGNALS[number] | null>(null);

  return (
    <main className="canvas" style={{ position: "fixed", inset: 0 }}>
      {/* the canvas field: a rotating radar sweep over a graticule — the anchor */}
      <div aria-hidden style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0,
                      backgroundImage: "radial-gradient(circle at 50% 42%, rgba(255,255,255,0.05), transparent 60%), repeating-radial-gradient(circle at 50% 42%, rgba(255,255,255,0.03) 0 1px, transparent 1px 88px)" }} />
        <div className="sweep" style={{ position: "absolute", top: "42%", left: "50%", width: 520, height: 520,
                      marginLeft: -260, marginTop: -260, borderRadius: "50%",
                      background: "conic-gradient(from 0deg, transparent 0deg, rgba(255,255,255,0.14) 40deg, transparent 60deg)" }} />
      </div>

      {/* masthead — type as graphic, huge signal count against tiny labels */}
      <header className="hero-pad" style={{ position: "relative", zIndex: 10 }}>
        <div className="label" style={{ color: "var(--text-dim)" }}>BEACON — LIVE SIGNAL OPS</div>
        <div className="display hero-numeral" style={{ color: "var(--text-hi)" }}>177</div>
        <div className="label" style={{ color: "var(--accent)" }}>ACTIVE SIGNALS · REGION 4</div>
      </header>

      {/* floating cards overlaid on the canvas — selecting one SPOTLIGHTS it: the rest
          of the collection demotes in place (fades) rather than disappearing */}
      <section style={{ position: "absolute", right: 48, top: 120, zIndex: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        {SIGNALS.map((s) => (
          <div key={s.id} onClick={() => setActive(s)}
               style={{ opacity: !active || active.id === s.id ? 1 : 0.35,
                        transition: "opacity 300ms ease" }}>
            <BeaconCard signal={s} />
          </div>
        ))}
      </section>

      {/* a perpetual ticker drifting across the base */}
      <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, overflow: "hidden", zIndex: 5, height: 28 }}>
        <div className="ticker label" style={{ whiteSpace: "nowrap", color: "var(--text-dim)", padding: "6px 0" }}>
          AX-01 NOMINAL · GR-14 DRIFT +2 · AR-09 ESCALATED · SECTOR SYNC 99.4% · &nbsp; AX-01 NOMINAL · GR-14 DRIFT +2 ·
        </div>
      </div>

      <DetailPanel open={!!active} signal={active} onClose={() => setActive(null)} />
    </main>
  );
}

"use client";
import { useRef, useState } from "react";

type Phase = "idle" | "arming" | "committed";

const BEAT = 420;         // the product's tactical beat
const ARM = 180;          // a held grip before the move — manufactured latency

// The focal object: a lit "beacon" tile. Clicking ARMS it (a held beat), then COMMITS —
// a multi-phase ceremony with the input locked mid-transition, symmetric in and out.
export default function BeaconCard({ signal }: { signal: { id: string; count: number; status: string; hue: string } }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [open, setOpen] = useState(false);
  const timers = useRef<number[]>([]);

  const locked = phase === "arming";           // interaction-lock during the transition

  function activate() {
    if (locked) return;
    setPhase("arming");
    // phase 1: arm (held grip) -> phase 2: commit -> settle. Chained, multi-phase.
    timers.current.push(window.setTimeout(() => setPhase("committed"), ARM));
    timers.current.push(window.setTimeout(() => { setOpen(true); setPhase("idle"); }, ARM + BEAT));
  }

  function dismiss() {
    // symmetric: the exit runs the same beat as the enter
    setPhase("arming");
    timers.current.push(window.setTimeout(() => { setOpen(false); setPhase("idle"); }, BEAT));
  }

  return (
    <button
      className="beacon-material elev-float"
      onClick={open ? dismiss : activate}
      aria-expanded={open}
      style={{
        position: "relative",
        width: 320,
        borderRadius: 18,
        border: "none",
        // the lit material — all overlays NEUTRAL (white light), lighting top-keyed; base fill hued.
        background:
          "radial-gradient(120% 70% at 50% -20%, rgba(255,255,255,0.12), transparent 55%)," +  // lighting (top-key, neutral)
          "linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0) 45%)," +          // sheen (neutral)
          "repeating-linear-gradient(180deg, rgba(255,255,255,0.03) 0 1px, transparent 1px 3px)," + // texture (neutral)
          "#131826",                                                                              // base fill
        boxShadow:
          "inset 0 2px 0 rgba(255,255,255,0.12), inset 0 -1px 0 rgba(0,0,0,0.5), " +              // bevel (neutral)
          "0 48px 96px -28px rgba(0,0,0,0.7)",                                                    // dramatic float (neutral)
        cursor: locked ? "progress" : "pointer",
        pointerEvents: locked ? "none" : "auto",              // input locked mid-ceremony
        transform: phase === "arming" ? "scale(0.975)" : phase === "committed" ? "scale(1.015)" : "scale(1)",
        transition: `transform ${BEAT}ms var(--ease-signal), box-shadow ${BEAT}ms var(--ease-signal)`,
        padding: "28px 24px",
        textAlign: "left",
      }}
    >
      <span className="presence" style={{ position: "absolute", top: 18, right: 18, width: 10, height: 10, borderRadius: "50%", background: signal.hue }} />
      <div className="label" style={{ color: "var(--text-dim)" }}>{signal.id} · {signal.status}</div>
      <div className="display hero-numeral" style={{ color: "var(--text-hi)", fontSize: 96 }}>{signal.count}</div>
      <div className="label" style={{ color: signal.hue }}>{open ? "LIVE — tap to close" : "tap to open"}</div>
    </button>
  );
}

"use client";
import { useEffect, useState } from "react";

const BEAT = 420;

// A floating detail panel that opens OVER the canvas (a covering overlay), backdrop-blurred,
// sliding up. Symmetric enter/exit; rows demote (dim) rather than disappear when superseded.
export default function DetailPanel({ open, onClose, signal }:
  { open: boolean; onClose: () => void; signal: { id: string; count: number; hue: string } | null }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (open) { const t = window.setTimeout(() => setShown(true), 16); return () => window.clearTimeout(t); }
    setShown(false);
  }, [open]);

  if (!open || !signal) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="glass"
      style={{
        position: "fixed",
        left: 0, right: 0, bottom: 0,
        zIndex: 40,
        padding: "32px 40px 40px",
        borderTop: "1px solid var(--edge)",
        boxShadow: "0 -48px 96px -24px rgba(0,0,0,0.7)",
        transform: shown ? "translateY(0)" : "translateY(24px)",
        opacity: shown ? 1 : 0,
        transition: `transform ${BEAT}ms var(--ease-signal), opacity ${BEAT}ms var(--ease-signal)`,
      }}
    >
      <div className="label" style={{ color: "var(--text-dim)" }}>SIGNAL {signal.id}</div>
      <div className="display hero-title" style={{ color: signal.hue }}>{signal.count} ACTIVE</div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {["origin", "vector", "eta", "confidence"].map((k, i) => (
          <div key={k} className="data-row label"
               style={{ display: "flex", justifyContent: "space-between", padding: "4px 8px",
                        opacity: i === 0 ? 1 : 0.55 /* demote, not remove */,
                        borderBottom: "1px solid var(--edge)" }}>
            <span style={{ color: "var(--text-dim)" }}>{k}</span>
            <span style={{ color: "var(--text-mid)" }}>—</span>
          </div>
        ))}
      </div>
      <button className="label elev-inset" onClick={onClose}
              style={{ marginTop: 16, padding: "8px 16px", background: "var(--surface-2)",
                       color: "var(--text-hi)", border: "1px solid var(--edge)", borderRadius: 8, cursor: "pointer" }}>
        CLOSE
      </button>
    </div>
  );
}

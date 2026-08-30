"use client";
import { useRef, useState } from "react";
import BeaconCanvas from "../components/BeaconCanvas";

// COVERAGE FIXTURE: this identity-bearing piece deliberately lives in src/app, NOT
// src/components — the eval asserts it is captured, guarding the shared-discovery
// contract (a compile that only reads the components dir would miss it, which is the
// regression this file exists to catch).
//
// The piece itself: the sweep-history scrubber — drag the playhead to scrub the radar
// timeline. Reactive (tracks the pointer continuously), pointer-captured while held,
// and the playhead reseats with the console's overshoot settle on release.
const SETTLE_MS = 240;

export default function Page() {
  const [scrubT, setScrubT] = useState(1);
  const [held, setHeld] = useState(false);
  const track = useRef<HTMLDivElement>(null);

  const scrubTo = (clientX: number) => {
    const r = track.current?.getBoundingClientRect();
    if (r) setScrubT(Math.min(1, Math.max(0, (clientX - r.left) / r.width)));
  };

  return (
    <div style={{ position: "relative" }}>
      <BeaconCanvas />

      {/* the scrubber strip — docked over the base of the field */}
      <div style={{ position: "absolute", bottom: 40, left: 48, right: 48, zIndex: 30 }}>
        <div className="label" style={{ color: "var(--text-dim)", opacity: held ? 1 : 0.4,
                      transition: `opacity ${SETTLE_MS}ms ease` }}>
          SWEEP HISTORY — T-{Math.round((1 - scrubT) * 90)}s
        </div>
        <div
          ref={track}
          style={{ position: "relative", height: 24, marginTop: 6, touchAction: "none" }}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            setHeld(true);
            scrubTo(e.clientX);
          }}
          onPointerMove={(e) => held && scrubTo(e.clientX)}
          onPointerUp={() => setHeld(false)}
        >
          {/* graduated ticks along the track */}
          <div style={{ position: "absolute", inset: "10px 0", display: "flex", justifyContent: "space-between" }}>
            {Array.from({ length: 46 }).map((_, i) => (
              <div key={i} style={{ width: 1, background: i % 5 ? "rgba(255,255,255,0.14)" : "var(--text-dim)" }} />
            ))}
          </div>
          {/* the playhead: tracks the pointer while held, reseats with an overshoot settle */}
          <div style={{ position: "absolute", top: 0, bottom: 0, width: 2, background: "var(--accent)",
                        left: 0, transform: `translateX(${scrubT * 100}%)`,
                        transition: held ? "none" : `transform ${SETTLE_MS}ms cubic-bezier(0.2, 1.4, 0.3, 1)` }} />
        </div>
      </div>
    </div>
  );
}

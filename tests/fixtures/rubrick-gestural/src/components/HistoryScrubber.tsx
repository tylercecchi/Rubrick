import { useRef, useState } from "react";

export type Snapshot = { at: number };

export function HistoryScrubber({ snapshots, onReplay }: {
  snapshots: Snapshot[];
  onReplay: (index: number | null) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState(1);
  const [isDragging, setDragging] = useState(false);

  function seek(clientX: number) {
    const r = track.current!.getBoundingClientRect();
    const p = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
    setPos(p);
    const i = Math.round(p * (snapshots.length - 1));
    onReplay(p >= 0.999 ? null : i);
  }

  const index = Math.round(pos * (snapshots.length - 1));
  return (
    <div className="history">
      <div ref={track} className="track"
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); setDragging(true); seek(e.clientX); }}
        onPointerMove={(e) => { if (isDragging) seek(e.clientX); }}
        onPointerUp={() => setDragging(false)}>
        {snapshots.map((s, i) => (
          <span key={s.at} className="tick" style={{ left: `${(i / Math.max(1, snapshots.length - 1)) * 100}%` }} />
        ))}
        <span className="playhead" style={{ left: `${pos * 100}%` }} />
      </div>
      <span className="stamp">
        {pos >= 0.999 ? "Now" : new Date(snapshots[index].at).toLocaleString()}
      </span>
    </div>
  );
}

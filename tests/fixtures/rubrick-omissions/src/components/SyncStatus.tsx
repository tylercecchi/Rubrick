import { useEffect, useState } from "react";

function ago(t: number) {
  const s = Math.round((Date.now() - t) / 1000);
  return s < 5 ? "just now" : s < 60 ? `${s}s ago` : `${Math.round(s / 60)}m ago`;
}

export function SyncStatus({ syncing, savedAt }: { syncing: boolean; savedAt: number | null }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, []);
  if (syncing) return <span className="status pending" aria-live="polite">Syncing…</span>;
  if (savedAt) return <span className="status" aria-live="polite">Saved {ago(savedAt)}</span>;
  return <span className="status">Not saved yet</span>;
}

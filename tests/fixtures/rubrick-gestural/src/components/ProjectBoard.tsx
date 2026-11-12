import { useMemo, useState } from "react";
import { Board, type Card } from "./Board";
import { HistoryScrubber, type Snapshot } from "./HistoryScrubber";

type Entry = Snapshot & { cards: Card[] };

export function ProjectBoard({ initial }: { initial: Card[] }) {
  const [history, setHistory] = useState<Entry[]>([{ at: Date.now(), cards: initial }]);
  const [replayIndex, setReplayIndex] = useState<number | null>(null);
  const current = history[history.length - 1].cards;
  const shown = replayIndex === null ? current : history[replayIndex].cards;

  function move(id: string, column: Card["column"], index: number) {
    const rest = current.filter((c) => c.id !== id);
    const card = { ...current.find((c) => c.id === id)!, column };
    const inCol = rest.filter((c) => c.column === column);
    inCol.splice(index, 0, card);
    const next = [...rest.filter((c) => c.column !== column), ...inCol];
    setHistory((h) => [...h, { at: Date.now(), cards: next }]);
  }

  const snapshots = useMemo(() => history.map(({ at }) => ({ at })), [history]);
  return (
    <main>
      <Board cards={shown} onMove={move} replaying={replayIndex !== null} />
      <HistoryScrubber snapshots={snapshots} onReplay={setReplayIndex} />
    </main>
  );
}

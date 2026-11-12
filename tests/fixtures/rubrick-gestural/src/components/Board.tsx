import { useState } from "react";

export type Card = { id: string; title: string; column: "todo" | "doing" | "done" };
const COLUMNS: Card["column"][] = ["todo", "doing", "done"];

export function Board({ cards, onMove, replaying }: {
  cards: Card[];
  onMove: (id: string, column: Card["column"], index: number) => void;
  replaying: boolean;
}) {
  const [dragId, setDragId] = useState<string | null>(null);

  return (
    <div className={replaying ? "board replaying" : "board"}>
      {COLUMNS.map((col) => (
        <section key={col} className="column"
          onDragOver={(e) => e.preventDefault()}
          onDrop={() => { if (dragId) onMove(dragId, col, cards.filter((c) => c.column === col).length); setDragId(null); }}>
          <h2>{col}</h2>
          {cards.filter((c) => c.column === col).map((c, i) => (
            <article key={c.id} draggable={!replaying}
              className={dragId === c.id ? "card dragging" : "card"}
              onDragStart={() => setDragId(c.id)}
              onDragEnd={() => setDragId(null)}
              onDrop={(e) => { e.stopPropagation(); if (dragId) onMove(dragId, col, i); setDragId(null); }}>
              {c.title}
            </article>
          ))}
        </section>
      ))}
    </div>
  );
}

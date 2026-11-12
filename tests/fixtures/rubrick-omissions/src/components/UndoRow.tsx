export function UndoRow({ label, onUndo }: { label: string; onUndo: () => void }) {
  return (
    <div className="undo" role="status">
      <span>Deleted “{label}”</span>
      <button className="action" onClick={onUndo}>Undo</button>
    </div>
  );
}

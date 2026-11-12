import { useState } from "react";
import { Header } from "./Header";
import { TaskRow, type Task } from "./TaskRow";
import { UndoRow } from "./UndoRow";

export function TaskList({ initial, save }: {
  initial: Task[]; save: (tasks: Task[]) => Promise<void>;
}) {
  const [tasks, setTasks] = useState(initial);
  const [deleted, setDeleted] = useState<{ task: Task; index: number } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  async function commit(next: Task[]) {
    setTasks(next);
    setSyncing(true);
    await save(next);
    setSyncing(false);
    setSavedAt(Date.now());
  }

  function remove(id: string) {
    const index = tasks.findIndex((t) => t.id === id);
    setDeleted({ task: tasks[index], index });
    commit(tasks.filter((t) => t.id !== id));
  }

  function undo() {
    if (!deleted) return;
    const next = [...tasks];
    next.splice(deleted.index, 0, deleted.task);
    setDeleted(null);
    commit(next);
  }

  function add() {
    if (!draft.trim()) return;
    commit([...tasks, { id: crypto.randomUUID(), label: draft.trim(), done: false }]);
    setDraft("");
  }

  const open = tasks.filter((t) => !t.done).length;
  return (
    <main>
      <Header open={open} total={tasks.length} syncing={syncing} savedAt={savedAt} />
      {deleted && <UndoRow label={deleted.task.label} onUndo={undo} />}
      <ul className="list">
        {tasks.map((t) => (
          <TaskRow key={t.id} task={t}
            onToggle={(id) => commit(tasks.map((x) => (x.id === id ? { ...x, done: !x.done } : x)))}
            onArchive={(id) => commit(tasks.filter((x) => x.id !== id))}
            onDelete={remove} />
        ))}
      </ul>
      <form className="row" onSubmit={(e) => { e.preventDefault(); add(); }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Add a task" />
        <button className="action primary" type="submit">Add</button>
      </form>
    </main>
  );
}

export type Task = { id: string; label: string; done: boolean; due?: string };

export function TaskRow({ task, onToggle, onArchive, onDelete }: {
  task: Task;
  onToggle: (id: string) => void;
  onArchive: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <li className={task.done ? "row done" : "row"}>
      <label className="label">
        <input type="checkbox" checked={task.done} onChange={() => onToggle(task.id)} />{" "}
        {task.label}
        {task.due && <span className="count"> · due {task.due}</span>}
      </label>
      <button className="action" onClick={() => onArchive(task.id)}>Archive</button>
      <button className="action" onClick={() => onDelete(task.id)}>Delete</button>
    </li>
  );
}

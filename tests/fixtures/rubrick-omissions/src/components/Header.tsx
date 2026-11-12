import { SyncStatus } from "./SyncStatus";

export function Header({ open, total, syncing, savedAt }: {
  open: number; total: number; syncing: boolean; savedAt: number | null;
}) {
  return (
    <header className="header">
      <div>
        <span className="title">Ledger</span>{" "}
        <span className="count">({open} open / {total})</span>
      </div>
      <SyncStatus syncing={syncing} savedAt={savedAt} />
    </header>
  );
}

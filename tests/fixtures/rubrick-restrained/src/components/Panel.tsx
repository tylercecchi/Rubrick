// Restrained component — the strict scale + coherent ramp applied consistently.
export function Panel({ title }: { title: string }) {
  return (
    <div style={{ padding: 16, gap: 12, border: "1px solid #26282d", background: "#131417", borderRadius: 8 }}>
      <h2 style={{ fontSize: 21, fontWeight: 590, color: "#f4f5f6" }}>{title}</h2>
      <div style={{ padding: "8px 12px", gap: 8, display: "flex", alignItems: "center" }}>
        <span style={{ fontSize: 13, fontWeight: 500, color: "#6b6f76" }}>Status</span>
        <span style={{ fontSize: 13, color: "#5e6ad2" }}>Active</span>
      </div>
      <div style={{ padding: "8px 12px", gap: 8, marginTop: 4, color: "#9ca1a8", fontSize: 14 }}>
        Restraint is the identity.
      </div>
    </div>
  );
}

// Generic app component — ad-hoc inline styles, unrelated colors, odd spacing.
export function Card({ title }: { title: string }) {
  return (
    <div style={{ padding: "13px 17px", margin: 22, border: "1px solid #cccccc", background: "#f8f9fa" }}>
      <h2 style={{ fontSize: 19, fontWeight: 700, color: "#333333" }}>{title}</h2>
      <p style={{ marginTop: 9, fontSize: 15, color: "#007bff" }}>An undesigned card.</p>
      <span style={{ padding: "5px 11px", background: "#28a745", color: "#fff", fontSize: 13 }}>OK</span>
    </div>
  );
}

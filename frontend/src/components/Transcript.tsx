export function Transcript({ lines }: { lines: { speaker: string; text: string }[] }) {
  if (lines.length === 0) return <p className="panel-body muted">No transcript for this call.</p>;
  return (
    <div className="transcript">
      {lines.map((line, index) => (
        <p key={index}><b>{line.speaker === "agent" ? "Line" : "Caller"}:</b> {line.text}</p>
      ))}
    </div>
  );
}

import { EVENT_LABELS, formatDateTime, sentence } from "../format";
import type { AuditEvent } from "../types";

export function AuditLogView({ events }: { events: AuditEvent[] }) {
  const newest = [...events].sort((a, b) => b.at.localeCompare(a.at));
  return (
    <section className="panel">
      <div className="panel-head"><h2>Audit log</h2><span className="muted">{events.length}</span></div>
      <div className="tablewrap">
        <table className="grid">
          <thead><tr><th>Time</th><th>Actor</th><th>Event</th><th>Detail</th></tr></thead>
          <tbody>
            {newest.map((event) => (
              <tr key={event.id}>
                <td className="nowrap">{formatDateTime(event.at)}</td>
                <td className="nowrap">{event.actor}</td>
                <td className="nowrap">{EVENT_LABELS[event.type] ?? sentence(event.type)}</td>
                <td>{event.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

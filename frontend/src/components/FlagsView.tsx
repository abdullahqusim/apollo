import { FLAG_TYPES, sentence } from "../format";
import type { FlagItem } from "../types";

const RANK: Record<string, number> = { red_flag: 0, got_worse: 1, too_severe: 1, no_reply: 1 };
const DECISIONS = ["too_severe", "symptoms_unclear", "low_confidence", "borderline_complexity"];
const WAITING = ["awaiting_tutor", "intake_done"];

export const needsDecision = (item: FlagItem) =>
  DECISIONS.includes(item.reason) && WAITING.includes(item.case?.status ?? "");

export function FlagsView({ items, onAccept, onDeny, onOpenPatient }: {
  items: FlagItem[];
  onAccept: (item: FlagItem) => void;
  onDeny: (item: FlagItem) => void;
  onOpenPatient: (id: string) => void;
}) {
  const open = items
    .filter((item) => item.status === "open")
    .sort((a, b) => (RANK[a.reason] ?? 2) - (RANK[b.reason] ?? 2));

  return (
    <section className="panel">
      <div className="panel-head"><h2>Flags</h2><span className="muted">{open.length}</span></div>
      {open.length === 0 ? <p className="empty">Nothing is flagged. Calls are being matched automatically.</p> : (
        <div className="tablewrap">
          <table className="grid">
            <thead><tr><th>Type</th><th>Patient</th><th>Why it was flagged</th><th /></tr></thead>
            <tbody>
              {open.map((item) => {
                const patient = item.patient;
                return (
                  <tr
                    key={item.id}
                    className={patient ? "clickable" : undefined}
                    onClick={patient ? () => onOpenPatient(patient.id) : undefined}
                  >
                    <td>
                      <span className={`tag ${item.reason in RANK ? "red" : "amber"}`}>
                        {FLAG_TYPES[item.reason] ?? sentence(item.reason)}
                      </span>
                    </td>
                    <td className="nowrap">
                      {patient
                        ? <button className="link" onClick={() => onOpenPatient(patient.id)}>{patient.name}</button>
                        : <span className="muted">Unknown caller</span>}
                    </td>
                    <td>
                      {item.summary}
                      <div className="muted small">{item.suggested_action}</div>
                    </td>
                    <td className="actions" onClick={(e) => e.stopPropagation()}>
                      <button className="btn small" onClick={() => onAccept(item)}>{needsDecision(item) ? "Accept" : "Done"}</button>
                      {needsDecision(item) && <button className="btn small" onClick={() => onDeny(item)}>Deny</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

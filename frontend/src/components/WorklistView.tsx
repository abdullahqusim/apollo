import { Fragment, useState } from "react";
import { CALL_OUTCOMES, formatTime, sentence, urgencyTone, WORKLIST_TYPES } from "../format";
import type { Call, WorklistItem } from "../types";

const RANK: Record<string, number> = { red_flag: 0, offers_exhausted: 1, no_backfill_candidate: 1 };

export function WorklistView({ items, calls, onClose, onOpenPatient, onOpenSlot }: {
  items: WorklistItem[];
  calls: Call[];
  onClose: (id: string, action: "resolve" | "dismiss") => void;
  onOpenPatient: (id: string) => void;
  onOpenSlot: (date: string, slotId: string) => void;
}) {
  const [openCall, setOpenCall] = useState<string | null>(null);
  const open = items
    .filter((item) => item.status === "open")
    .sort((a, b) => (RANK[a.reason] ?? 2) - (RANK[b.reason] ?? 2));

  return (
    <>
      <section className="panel">
        <div className="panel-head"><h2>Needs attention</h2><span className="muted">{open.length}</span></div>
        {open.length === 0 ? <p className="empty">Nothing needs attention.</p> : (
          <div className="tablewrap">
            <table className="grid">
              <thead><tr><th>Type</th><th>Patient</th><th>Summary</th><th>Next step</th><th /></tr></thead>
              <tbody>
                {open.map((item) => {
                  const red = item.reason in RANK;
                  return (
                    <tr key={item.id}>
                      <td><span className={`tag ${red ? "red" : "amber"}`}>{WORKLIST_TYPES[item.reason] ?? sentence(item.reason)}</span></td>
                      <td className="nowrap">
                        {item.patient
                          ? <button className="link" onClick={() => onOpenPatient(item.patient!.id)}>{item.patient.name}</button>
                          : <span className="muted">None</span>}
                      </td>
                      <td>{item.summary}</td>
                      <td>{item.suggested_action}</td>
                      <td className="actions">
                        {item.slot && <button className="btn small" onClick={() => onOpenSlot(item.slot!.date, item.slot!.id)}>Open chair</button>}
                        <button className="btn small" onClick={() => onClose(item.id, "resolve")}>Approve</button>
                        <button className="btn small" onClick={() => onClose(item.id, "dismiss")}>Dismiss</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head"><h2>Calls</h2><span className="muted">{calls.length}</span></div>
        <div className="tablewrap">
          <table className="grid">
            <thead><tr><th>Time</th><th>Caller</th><th>Outcome</th><th>Urgency</th><th>Summary</th></tr></thead>
            <tbody>
              {calls.map((call) => {
                const expanded = openCall === call.call_id;
                return (
                  <Fragment key={call.call_id}>
                    <tr
                      className={`clickable ${expanded ? "selected" : ""}`}
                      aria-expanded={expanded}
                      onClick={() => setOpenCall(expanded ? null : call.call_id)}
                    >
                      <td className="nowrap">{formatTime(call.started_at)}</td>
                      <td className="nowrap">
                        {call.patient_id
                          ? (
                            <button className="link" onClick={(e) => { e.stopPropagation(); onOpenPatient(call.patient_id!); }}>
                              {call.patient_name}
                            </button>
                          )
                          : call.patient_name}
                      </td>
                      <td className="nowrap">{CALL_OUTCOMES[call.outcome] ?? sentence(call.outcome)}</td>
                      <td>{call.case && <span className={`tag ${urgencyTone(call.case.urgency)}`}>{sentence(call.case.urgency)}</span>}</td>
                      <td>{call.summary}</td>
                    </tr>
                    {expanded && (
                      <tr className="detail">
                        <td colSpan={5}>
                          <dl className="facts">
                            {call.transcript.map((line, i) => (
                              <Fragment key={i}>
                                <dt>{line.speaker === "agent" ? "Automated line" : "Caller"}</dt>
                                <dd>{line.text}</dd>
                              </Fragment>
                            ))}
                          </dl>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

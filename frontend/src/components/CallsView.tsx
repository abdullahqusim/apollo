import { Fragment, useState } from "react";
import { CALL_OUTCOMES, formatCallTime, sentence, urgencyTone } from "../format";
import type { Call } from "../types";
import { Transcript } from "./Transcript";

/** A row opens the patient's record. Callers with no record show their transcript here instead. */
export function CallsView({ calls, onOpenPatient }: { calls: Call[]; onOpenPatient: (id: string) => void }) {
  const [openCall, setOpenCall] = useState<string | null>(null);

  return (
    <section className="panel">
      <div className="panel-head"><h2>Calls</h2><span className="muted">{calls.length}</span></div>
      <div className="tablewrap">
        <table className="grid">
          <thead><tr><th>Time</th><th>Caller</th><th>Outcome</th><th>Urgency</th><th>Summary</th></tr></thead>
          <tbody>
            {calls.map((call) => {
              const expanded = openCall === call.call_id;
              const patientId = call.patient_id;
              return (
                <Fragment key={call.call_id}>
                  <tr
                    className={`clickable ${expanded ? "selected" : ""}`}
                    onClick={() => (patientId ? onOpenPatient(patientId) : setOpenCall(expanded ? null : call.call_id))}
                  >
                    <td className="nowrap">{formatCallTime(call.started_at)}</td>
                    <td className="nowrap">
                      {patientId ? <button className="link">{call.patient_name}</button> : call.patient_name}
                    </td>
                    <td className="nowrap">{CALL_OUTCOMES[call.outcome] ?? sentence(call.outcome)}</td>
                    <td>{call.case && <span className={`tag ${urgencyTone(call.case.urgency)}`}>{sentence(call.case.urgency)}</span>}</td>
                    <td>{call.summary}</td>
                  </tr>
                  {expanded && (
                    <tr className="detail"><td colSpan={5}><Transcript lines={call.transcript} /></td></tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

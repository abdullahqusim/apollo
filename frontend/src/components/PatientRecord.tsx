import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { CALL_OUTCOMES, formatBirthDate, formatDate, formatTime, sentence } from "../format";
import type { PatientRecordData, Role } from "../types";
import { Transcript } from "./Transcript";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

const listed = (items: string[], declined: boolean) =>
  items.join(", ") || (declined ? "Would rather not say" : "None reported");

export function PatientRecord({ patientId, role, panelRight, onClose, onChanged, onOpenPhone, onLoaded }: {
  patientId: string;
  role: Role;
  panelRight: number;
  onClose: () => void;
  onChanged: () => void;
  onOpenPhone: (token: string) => void;
  onLoaded: (token: string) => void;
}) {
  const [record, setRecord] = useState<PatientRecordData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api.getPatient(patientId, role).then(setRecord).catch((e: Error) => setError(e.message));
  }, [patientId, role]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const review = async (decision: "agree" | "override" | "reject") => {
    if (!record?.case) return;
    setSaving(true);
    try {
      await api.reviewTriage({ case_id: record.case.id, decision, notes: notes || undefined });
      setNotes("");
      load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const token = record?.patient.contact_token;
  useEffect(() => {
    if (token) onLoaded(token);
  }, [token, onLoaded]);

  const panel = record?.case?.clinical_panel;
  const history = panel?.medical_history;
  const grid = record?.patient.availability.grid;
  const appointment = record?.appointment;

  return (
    <aside className="record" style={{ right: panelRight }} aria-label="Patient record">
      <div className="winbar">
        <span>{record?.patient.name ?? "Patient record"}</span>
        {record && <button className="btn small" onClick={() => onOpenPhone(record.patient.contact_token)}>Open phone</button>}
        <button className="close" onClick={onClose} aria-label="Close record">×</button>
      </div>
      {error && <p className="form-error">{error}</p>}
      {record && (
        <div className="scroll">
          <dl className="facts">
            <dt>Phone</dt><dd>{record.patient.phone}</dd>
            {record.patient.date_of_birth && <><dt>Date of birth</dt><dd>{formatBirthDate(record.patient.date_of_birth)}</dd></>}
            {record.case && <><dt>Came in by</dt><dd>{record.case.channel === "online" ? "Online form" : "Phone call"}</dd></>}
            <dt>Short notice</dt><dd>{record.patient.short_notice_ok ? "Yes, on standby" : "No"}</dd>
            {record.patient.flags.length > 0 && <><dt>Flags</dt><dd>{sentence(record.patient.flags.join(", "))}</dd></>}
            {record.patient.dna_count > 0 && <><dt>Missed visits</dt><dd>{record.patient.dna_count}</dd></>}
          </dl>

          {appointment && (
            <>
              <p className="section-title">{appointment.state === "offered" ? "Appointment offered" : "Appointment booked"}</p>
              <dl className="facts">
                <dt>When</dt><dd>{formatDate(appointment.date)} at {appointment.start}, {appointment.bay}</dd>
                <dt>Clinician</dt><dd>{appointment.clinician_name}</dd>
              </dl>
              <ul className="reasons">{appointment.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
            </>
          )}

          {record.case && (
            <>
              <p className="section-title">Triage</p>
              <dl className="facts">
                <dt>Summary</dt><dd>{record.case.summary_plain}</dd>
                <dt>Urgency</dt><dd>{sentence(record.case.urgency)}</dd>
                {record.case.agent_urgency && record.case.agent_urgency !== record.case.urgency && (
                  <><dt>Line said</dt><dd>{sentence(record.case.agent_urgency)}</dd></>
                )}
                <dt>Complexity</dt><dd>{record.case.complexity}</dd>
                <dt>Confidence</dt><dd>{sentence(record.case.confidence)}</dd>
              </dl>
            </>
          )}

          {panel && (
            <>
              <p className="section-title">Medical history</p>
              {history ? (
                <dl className="facts">
                  <dt>Conditions</dt><dd>{listed(history.conditions, history.declined)}</dd>
                  <dt>Allergies</dt><dd>{listed(history.allergies, history.declined)}</dd>
                  <dt>Medications</dt><dd>{listed(history.medications, history.declined)}</dd>
                </dl>
              ) : <p className="panel-body muted">Not asked</p>}
              <p className="section-title">Possible issues for clinical review</p>
              <p className="panel-body">“{panel.complaint_quote}”</p>
              <dl className="facts">
                <dt>Most likely first</dt>
                <dd><ol>{panel.possible_issues.map((issue) => <li key={issue}>{issue}</li>)}</ol></dd>
                {panel.not_ruled_out.length > 0 && <><dt>Not ruled out</dt><dd>{panel.not_ruled_out.join(", ")}</dd></>}
                <dt>Likely procedures</dt><dd>{panel.likely_procedures.join(", ")}</dd>
                {panel.tutor_review && <><dt>Reviewed</dt><dd>{sentence(panel.tutor_review.decision)}, {panel.tutor_review.by}</dd></>}
              </dl>
              {!panel.tutor_review && (
                <div className="panel-body">
                  <textarea className="field" aria-label="Review notes" placeholder="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
                  <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                    <button className="btn" disabled={saving} onClick={() => review("agree")}>Agree</button>
                    <button className="btn" disabled={saving} onClick={() => review("override")}>Edit</button>
                    <button className="btn" disabled={saving} onClick={() => review("reject")}>Reject</button>
                  </div>
                </div>
              )}
            </>
          )}

          <p className="section-title">Availability</p>
          <table className="grid">
            <thead><tr><th>Day</th><th>Morning</th><th>Afternoon</th></tr></thead>
            <tbody>
              {DAYS.map((day) => {
                const value = grid?.[day.toLowerCase()];
                return (
                  <tr key={day}>
                    <td>{day}</td>
                    <td>{value?.am ? "Yes" : <span className="muted">No</span>}</td>
                    <td>{value?.pm ? "Yes" : <span className="muted">No</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {record.call_history.length > 0 && (
            <>
              <p className="section-title">Calls</p>
              {record.call_history.map((call) => (
                <div key={call.id}>
                  <dl className="facts">
                    <dt>{formatTime(call.started_at)}</dt>
                    <dd>{CALL_OUTCOMES[call.outcome] ?? sentence(call.outcome)}</dd>
                  </dl>
                  <Transcript lines={call.transcript} />
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </aside>
  );
}

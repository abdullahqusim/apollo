import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDate } from "../format";
import type { Shortlist } from "../types";
import { Dialog } from "./Dialog";

const OVERRIDES = [
  { id: "patient_request", label: "Patient request" },
  { id: "continuity", label: "Continuity of care" },
  { id: "clinician_request", label: "Clinician request" },
  { id: "other", label: "Other" },
];

export function AssignDialog({ caseId, onClose, onAssigned }: {
  caseId: string;
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [data, setData] = useState<Shortlist | null>(null);
  const [clinicianId, setClinicianId] = useState("");
  const [slots, setSlots] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getShortlist(caseId)
      .then((res) => {
        const eligible = res.shortlist.filter((c) => c.candidate_slots.length > 0).slice(0, 5);
        setData({ ...res, shortlist: eligible });
        setClinicianId(eligible[0]?.clinician_id ?? "");
        setSlots(Object.fromEntries(eligible.map((c) => [c.clinician_id, c.candidate_slots[0].slot_id])));
      })
      .catch((e: Error) => setError(e.message));
  }, [caseId]);

  const options = data?.shortlist ?? [];
  const chosen = options.find((c) => c.clinician_id === clinicianId);
  const isOverride = !!chosen && chosen !== options[0];
  const ready = !!chosen && (!isOverride || !!reason);

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.assign({
        case_id: caseId,
        slot_id: slots[clinicianId],
        reason_chip: isOverride ? reason : "recommended",
        notes: notes || undefined,
      });
      onAssigned();
      onClose();
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  };

  return (
    <Dialog
      title={`Assign ${data?.patient_name ?? "patient"}`}
      width={780}
      onClose={onClose}
      footer={
        <>
          <button className="btn primary" disabled={!ready || saving} onClick={submit}>Book appointment</button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </>
      }
    >
      {data && options.length === 0 && <p className="empty">No eligible clinician has a free slot.</p>}
      {options.length > 0 && (
        <table className="grid">
          <thead>
            <tr><th>Clinician</th><th>Grade</th><th className="num">Load</th><th className="num">Logbook</th><th>Slot</th></tr>
          </thead>
          <tbody>
            {options.map((clinician, index) => (
              <tr key={clinician.clinician_id} className={clinician === chosen ? "selected" : undefined}>
                <td className="nowrap">
                  <label>
                    <input
                      type="radio"
                      name="clinician"
                      checked={clinician === chosen}
                      onChange={() => setClinicianId(clinician.clinician_id)}
                    />{" "}
                    {clinician.name}{index === 0 && <span className="muted"> (recommended)</span>}
                  </label>
                </td>
                <td className="nowrap">{clinician.tier_name}</td>
                <td className="num">{clinician.load_percent}%</td>
                <td className="num">{clinician.logbook_gap}</td>
                <td>
                  <select
                    className="field"
                    aria-label={`Slot with ${clinician.name}`}
                    value={slots[clinician.clinician_id]}
                    onChange={(e) => {
                      setSlots({ ...slots, [clinician.clinician_id]: e.target.value });
                      setClinicianId(clinician.clinician_id);
                    }}
                  >
                    {clinician.candidate_slots.map((slot) => (
                      <option key={slot.slot_id} value={slot.slot_id}>
                        {formatDate(slot.date)}, {slot.start}, {slot.bay}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {chosen && <p className="block muted">{chosen.reason_summary}</p>}
      {isOverride && (
        <>
          <div className="form-row">
            <label htmlFor="assign-reason">Reason</label>
            <select id="assign-reason" className="field" value={reason} onChange={(e) => setReason(e.target.value)}>
              <option value="">Select a reason</option>
              {OVERRIDES.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
          </div>
          <div className="form-row">
            <label htmlFor="assign-notes">Notes</label>
            <input id="assign-notes" className="field" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </>
      )}
      {error && <p className="form-error">{error}</p>}
    </Dialog>
  );
}

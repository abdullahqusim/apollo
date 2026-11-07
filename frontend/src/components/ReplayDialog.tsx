import { useState } from "react";
import { api } from "../api";
import { Dialog } from "./Dialog";

const ROWS: [string, string][] = [
  ["Chair utilisation", "chair_utilisation"],
  ["Average wait, urgent", "average_wait_urgent"],
  ["Average wait, soon", "average_wait_soon"],
  ["Average wait, routine", "average_wait_routine"],
  ["Urgent window breaches", "urgent_window_breaches"],
  ["Reschedules per patient", "reschedules_per_patient"],
  ["Triage agreement with clinician", "triage_agreement_rate"],
  ["Cancellations refilled", "cancellations_recovered_rate"],
];

export function ReplayDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [metrics, setMetrics] = useState<Record<string, string | number> | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.replayWeek();
      setMetrics(res.metrics);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog
      title="Replay a week"
      width={440}
      onClose={onClose}
      footer={
        <>
          <button className="btn primary" disabled={running} onClick={run}>{metrics ? "Run again" : "Run"}</button>
          <button className="btn" onClick={onClose}>Close</button>
        </>
      }
    >
      {metrics ? (
        <table className="grid">
          <thead><tr><th>Measure</th><th className="num">Result</th></tr></thead>
          <tbody>
            {ROWS.map(([label, key]) => <tr key={key}><td>{label}</td><td className="num">{metrics[key]}</td></tr>)}
          </tbody>
        </table>
      ) : (
        <p className="message">Runs a synthetic week of cancellations, missed visits and new cases.</p>
      )}
      {error && <p className="form-error">{error}</p>}
    </Dialog>
  );
}

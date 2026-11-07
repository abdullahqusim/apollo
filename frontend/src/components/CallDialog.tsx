import { useMemo, useState } from "react";
import { api, type IntakeResult } from "../api";
import { Dialog } from "./Dialog";

type Line = { speaker: "agent" | "patient"; text: string };

const agent = (text: string): Line => ({ speaker: "agent", text });
const patient = (text: string): Line => ({ speaker: "patient", text });

const script = (name: string, problem: string, availability: string, shortNotice: string): Line[] => [
  agent("You're through to Apollo. Can I take your name and what's the problem?"),
  patient(`My name is ${name}. ${problem}`),
  agent("Which days and times work for you?"),
  patient(availability),
  agent("Could you come in at short notice if a chair opens up?"),
  patient(shortNotice),
  agent("Thanks. We'll text you about an appointment."),
];

const SCENARIOS = [
  { id: "routine", label: "Lost filling, routine", name: "Rory Sinclair", problem: "I lost a filling last week and cold drinks hurt.", availability: "I can't do Mondays. Tuesday and Thursday mornings are best.", shortNotice: "Yes, that's fine." },
  { id: "urgent", label: "Broken tooth, urgent", name: "Isla Grant", problem: "I broke my front tooth in a fall and it's bleeding a little.", availability: "Any day is fine.", shortNotice: "Yes." },
  { id: "unclear", label: "Unclear symptoms", name: "Ewan Reid", problem: "Something just feels a bit odd on one side sometimes.", availability: "Afternoons are better.", shortNotice: "No, not really." },
  { id: "emergency", label: "Emergency", name: "Niamh Duff", problem: "My face has swollen up and the swelling is spreading down my neck.", availability: "Any time.", shortNotice: "Yes." },
];

export function CallDialog({ onClose, onDone }: { onClose: () => void; onDone: (result: IntakeResult) => void }) {
  const [scenarioId, setScenarioId] = useState("routine");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scenario = SCENARIOS.find((s) => s.id === scenarioId)!;
  const transcript = useMemo(
    () => script(scenario.name, scenario.problem, scenario.availability, scenario.shortNotice),
    [scenario],
  );

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      const stamp = Date.now();
      onDone(await api.sendCall({
        call_id: `demo-${stamp}`,
        caller_phone: `07700 9${String(stamp).slice(-5)}`,
        transcript,
      }));
      onClose();
    } catch (e) {
      setError((e as Error).message);
      setSending(false);
    }
  };

  return (
    <Dialog
      title="Simulate a call"
      width={520}
      onClose={onClose}
      footer={
        <>
          <button className="btn primary" disabled={sending} onClick={send}>End call and process</button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </>
      }
    >
      <div className="form-row">
        <label htmlFor="call-scenario">Caller</label>
        <select id="call-scenario" className="field" value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
          {SCENARIOS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>
      <div className="transcript">
        {transcript.map((line, index) => (
          <p key={index}><b>{line.speaker === "agent" ? "Line" : "Caller"}:</b> {line.text}</p>
        ))}
      </div>
      {error && <p className="form-error">{error}</p>}
    </Dialog>
  );
}

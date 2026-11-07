import { useMemo, useState } from "react";
import { api, type IntakeResult } from "../api";
import { Dialog } from "./Dialog";

type Line = { speaker: "agent" | "patient"; text: string };

const agent = (text: string): Line => ({ speaker: "agent", text });
const patient = (text: string): Line => ({ speaker: "patient", text });

type Scenario = {
  id: string;
  label: string;
  name: string;
  born: string;
  history: string;
  problem: string;
  availability: string;
  shortNotice: string;
  agentUrgency?: string;
};

const script = ({ name, born, history, problem, availability, shortNotice }: Scenario): Line[] => [
  agent("You're through to Apollo. Can I take your name and what's the problem?"),
  patient(`My name is ${name}. ${problem}`),
  agent("Please may I have your date of birth."),
  patient(born),
  agent("Do you have any known conditions, allergies, or take any regular medications?"),
  patient(history),
  agent("Which days and times work for you?"),
  patient(availability),
  agent("Could you come in at short notice if a chair opens up?"),
  patient(shortNotice),
  agent("Thanks. We'll text you about an appointment."),
];

const SCENARIOS: Scenario[] = [
  { id: "routine", label: "Lost filling, routine", name: "Rory Sinclair", born: "The 3rd of March 1985.", history: "I've got asthma, I'm allergic to penicillin and I take ibuprofen.", problem: "I lost a filling last week and cold drinks hurt.", availability: "I can't do Mondays. Tuesday and Thursday mornings are best.", shortNotice: "Yes, that's fine." },
  { id: "urgent", label: "Broken tooth, urgent", name: "Isla Grant", born: "12/07/1999", history: "No, none of those.", problem: "I broke my front tooth in a fall and it's bleeding a little.", availability: "Any day is fine.", shortNotice: "Yes." },
  { id: "disagree", label: "Line rates it higher than triage", name: "Morag Kerr", born: "The 21st of June 1941.", history: "I'd rather not say.", problem: "My old filling is sensitive to cold.", availability: "Any day is fine.", shortNotice: "Yes.", agentUrgency: "urgent" },
  { id: "unclear", label: "Too little information, flagged", name: "Ewan Reid", born: "2nd of November 1970.", history: "I take ramipril.", problem: "Something just feels a bit odd on one side sometimes.", availability: "Afternoons are better.", shortNotice: "No, not really." },
  { id: "severe", label: "Abscess, flagged as too severe", name: "Calum Ross", born: "14/02/1978", history: "No.", problem: "I think I have an abscess and it's getting worse.", availability: "Any day is fine.", shortNotice: "Yes." },
  { id: "emergency", label: "Emergency", name: "Niamh Duff", born: "9th of September 2001.", history: "No.", problem: "My face has swollen up and the swelling is spreading down my neck.", availability: "Any time.", shortNotice: "Yes." },
];

export function CallDialog({ onClose, onDone }: { onClose: () => void; onDone: (result: IntakeResult) => void }) {
  const [scenarioId, setScenarioId] = useState("routine");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scenario = SCENARIOS.find((s) => s.id === scenarioId)!;
  const transcript = useMemo(() => script(scenario), [scenario]);

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      const stamp = Date.now();
      onDone(await api.sendCall({
        call_id: `demo-${stamp}`,
        caller_phone: `07700 9${String(stamp).slice(-5)}`,
        transcript,
        agent_urgency: scenario.agentUrgency,
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

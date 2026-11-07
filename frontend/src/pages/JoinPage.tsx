import { useState, type FormEvent } from "react";
import { api } from "../api";
import type { Availability } from "../types";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

const items = (text: string) => text.split(",").map((item) => item.trim()).filter(Boolean);

const emptyWeek = (): Availability =>
  Object.fromEntries(DAYS.map((day) => [day.toLowerCase(), { am: false, pm: false }]));

/** The online version of the phone line: same questions, same outcomes. */
export function JoinPage() {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [problem, setProblem] = useState("");
  const [conditions, setConditions] = useState("");
  const [allergies, setAllergies] = useState("");
  const [medications, setMedications] = useState("");
  const [ratherNotSay, setRatherNotSay] = useState(false);
  const [week, setWeek] = useState<Availability>(emptyWeek);
  const [shortNotice, setShortNotice] = useState(false);
  const [earlier, setEarlier] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (day: string, session: "am" | "pm") => {
    setWeek({ ...week, [day]: { ...week[day], [session]: !week[day][session] } });
    setError(null);
  };
  const hasTime = Object.values(week).some((day) => day.am || day.pm);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!hasTime) {
      setError("Choose at least one morning or afternoon you can come in.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await api.register({
        name: name.trim(),
        phone: phone.trim(),
        problem: problem.trim(),
        date_of_birth: birthDate,
        medical_history: {
          conditions: ratherNotSay ? [] : items(conditions),
          allergies: ratherNotSay ? [] : items(allergies),
          medications: ratherNotSay ? [] : items(medications),
          declined: ratherNotSay,
        },
        availability: week,
        short_notice_ok: shortNotice,
        wants_earlier: earlier,
      });
      window.location.href = res.redirect_url!;
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  };

  return (
    <div className="patient">
      <header className="patient-head">
        <h1>Apollo</h1>
        <p>Free treatment from supervised dental students</p>
      </header>
      <main className="patient-main">
        <form onSubmit={submit}>
          <label className="q">
            <span>Your name</span>
            <input className="p-field" required autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="q">
            <span>Date of birth</span>
            <input className="p-field" required type="date" autoComplete="bday" max={new Date().toISOString().slice(0, 10)} value={birthDate} onChange={(e) => setBirthDate(e.target.value)} />
          </label>
          <label className="q">
            <span>Mobile number<small>We will text you about your appointment.</small></span>
            <input className="p-field" required type="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <label className="q">
            <span>What's the problem?<small>Tell us in your own words.</small></span>
            <textarea className="p-field" required value={problem} onChange={(e) => setProblem(e.target.value)} />
          </label>
          <fieldset>
            <legend>Your medical history</legend>
            <label className="q">
              <span>Known conditions<small>Separate each one with a comma. Leave blank if none.</small></span>
              <input className="p-field" disabled={ratherNotSay} value={conditions} onChange={(e) => setConditions(e.target.value)} />
            </label>
            <label className="q">
              <span>Allergies</span>
              <input className="p-field" disabled={ratherNotSay} value={allergies} onChange={(e) => setAllergies(e.target.value)} />
            </label>
            <label className="q">
              <span>Regular medications</span>
              <input className="p-field" disabled={ratherNotSay} value={medications} onChange={(e) => setMedications(e.target.value)} />
            </label>
            <label className="choice">
              <input type="checkbox" checked={ratherNotSay} onChange={(e) => setRatherNotSay(e.target.checked)} />
              I'd rather not say
            </label>
          </fieldset>
          <fieldset>
            <legend>When can you come in?</legend>
            <table className="av">
              <thead><tr><th>Day</th><th>Morning</th><th>Afternoon</th></tr></thead>
              <tbody>
                {DAYS.map((day) => {
                  const key = day.toLowerCase();
                  return (
                    <tr key={day}>
                      <th scope="row">{day}</th>
                      <td><input type="checkbox" aria-label={`${day} morning`} checked={week[key].am} onChange={() => toggle(key, "am")} /></td>
                      <td><input type="checkbox" aria-label={`${day} afternoon`} checked={week[key].pm} onChange={() => toggle(key, "pm")} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </fieldset>
          <fieldset>
            <legend>Anything else?</legend>
            <label className="choice">
              <input type="checkbox" checked={shortNotice} onChange={(e) => setShortNotice(e.target.checked)} />
              I can come in at short notice if a chair opens up
            </label>
            <label className="choice">
              <input type="checkbox" checked={earlier} onChange={(e) => setEarlier(e.target.checked)} />
              Move me to an earlier appointment if one comes up
            </label>
          </fieldset>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="p-btn" type="submit" disabled={saving}>{saving ? "Sending" : "Send"}</button>
        </form>
      </main>
    </div>
  );
}

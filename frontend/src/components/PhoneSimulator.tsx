import { useEffect, useState } from "react";
import { api } from "../api";
import type { PhoneEntry } from "../types";
import { PhoneThread } from "./PhoneThread";

export function PhoneSimulator({ token, onPick }: { token: string | null; onPick: (token: string) => void }) {
  const [phones, setPhones] = useState<PhoneEntry[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const current = token ?? chosen ?? phones[0]?.token ?? null;

  useEffect(() => {
    let active = true;
    const load = () => api.getPhones().then((res) => { if (active) setPhones(res.phones); }).catch(() => undefined);
    load();
    const timer = setInterval(load, 2000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  const pick = (next: string) => { setChosen(next); onPick(next); };
  const known = phones.some((phone) => phone.token === current);

  return (
    <>
      <div className="picker">
        <select className="field" aria-label="Patient phone" value={current ?? ""} onChange={(e) => pick(e.target.value)}>
          {!known && current && <option value={current}>Selected patient</option>}
          {phones.map((phone) => <option key={phone.token} value={phone.token}>{phone.name}</option>)}
        </select>
      </div>
      <div className="device">
        {current ? <PhoneThread key={current} token={current} /> : <p className="empty">No patients have been texted yet.</p>}
      </div>
    </>
  );
}

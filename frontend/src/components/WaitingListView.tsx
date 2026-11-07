import { useState } from "react";
import { api } from "../api";
import { formatDate, sentence, urgencyTone } from "../format";
import type { Role, WaitingCase } from "../types";

const GRADES: Record<number, string> = { 1: "Year 3", 2: "Year 4", 3: "Year 5", 4: "Postgraduate", 5: "Dentist" };

type Filter = "active" | "all" | "unmatched" | "offered" | "booked" | "review" | "closed";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "active", label: "Not booked yet" },
  { id: "all", label: "All patients" },
  { id: "unmatched", label: "Waiting for a match" },
  { id: "offered", label: "Offered, awaiting reply" },
  { id: "booked", label: "Booked" },
  { id: "review", label: "Tutor review" },
  { id: "closed", label: "Closed" },
];

function stageOf(c: WaitingCase): Filter {
  if (c.appointment) return c.appointment.state;
  if (c.status === "awaiting_tutor" || c.status === "intake_done") return "review";
  if (c.status === "accepted") return "unmatched";
  return c.status === "scheduled" ? "booked" : "closed";
}

function Status({ item }: { item: WaitingCase }) {
  if (item.appointment) {
    const when = `${formatDate(item.appointment.date)}, ${item.appointment.start}`;
    return item.appointment.state === "offered"
      ? <span className="tag blue">Offered {when}</span>
      : <span className="tag green">Booked {when}</span>;
  }
  const stage = stageOf(item);
  if (stage === "review") return <span className="tag amber">Tutor review</span>;
  if (stage === "unmatched") return <span className="tag">Waiting for a match</span>;
  if (item.status === "emergency_redirected") return <span className="tag red">Sent to A&amp;E</span>;
  return <span className="tag">{sentence(item.status)}</span>;
}

export function WaitingListView({ cases, role, onOpenPatient, onAssign, onChanged }: {
  cases: WaitingCase[];
  role: Role;
  onOpenPatient: (id: string) => void;
  onAssign: (caseId: string) => void;
  onChanged: () => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("active");
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const term = search.trim().toLowerCase();
  const rows = cases.filter((c) =>
    (filter === "all" || stageOf(c) === filter || (filter === "active" && ["unmatched", "offered", "review"].includes(stageOf(c))))
    && (!term || c.patient_name.toLowerCase().includes(term) || c.phone.includes(term)));
  const clinical = role === "clinical";
  const unmatched = cases.filter((c) => stageOf(c) === "unmatched").length;

  const matchAll = async () => {
    setRunning(true);
    setNotice(null);
    try {
      const res = await api.matchWaitingList();
      setNotice(res.waiting === 0
        ? "Nobody is waiting for a match."
        : `Texted ${res.offered} of ${res.waiting} patients an appointment. ${res.unmatched} have no slot that fits yet.`);
      onChanged();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <div className="toolbar">
        <input
          className="field wide"
          type="search"
          aria-label="Search by name or phone"
          placeholder="Search by name or phone"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="field" aria-label="Filter" value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
          {FILTERS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
        </select>
        <span className="spacer" />
        <button className="btn primary" disabled={running} onClick={matchAll}>Match waiting list ({unmatched})</button>
      </div>
      {notice && <p className="notice">{notice}</p>}
      <section className="panel">
        <div className="tablewrap">
          <table className="grid">
            <thead>
              <tr>
                <th>Patient</th><th>Urgency</th><th>Summary</th>{clinical && <th>Likely procedures</th>}
                <th>Minimum grade</th><th className="num">Days waiting</th><th>Status</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => {
                const notes = [c.channel === "online" ? "Online" : "Phone", ...(c.short_notice_ok ? ["Short notice"] : []), ...c.flags];
                const bookable = ["unmatched", "review"].includes(stageOf(c));
                return (
                  <tr key={c.case_id}>
                    <td className="nowrap">
                      <button className="link" onClick={() => onOpenPatient(c.patient_id)}>{c.patient_name}</button>
                      <div className="muted small">{sentence(notes.join(", "))}</div>
                    </td>
                    <td><span className={`tag ${urgencyTone(c.urgency)}`}>{sentence(c.urgency)}</span></td>
                    <td className="summary">{c.summary_plain}</td>
                    {clinical && <td>{c.likely_procedures.join(", ")}</td>}
                    <td className="nowrap">{GRADES[c.required_tier]}</td>
                    <td className="num">{c.days_waiting}</td>
                    <td><Status item={c} /></td>
                    <td className="actions">
                      {bookable && <button className="btn small" onClick={() => onAssign(c.case_id)}>Book</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="empty">No patients match this filter.</p>}
      </section>
    </>
  );
}

import { Fragment, useState } from "react";
import { formatDate, sentence } from "../format";
import type { Clinician, ClinicianData } from "../types";

const GRADES = ["Year 3", "Year 4", "Year 5", "Postgraduate", "Qualified Dentist"];

const logbookTotals = (c: Clinician) => {
  const entries = Object.entries(c.logbook_targets);
  const target = entries.reduce((sum, [, value]) => sum + value, 0);
  const done = entries.reduce((sum, [name, value]) => sum + Math.min(value, c.logbook_done[name] ?? 0), 0);
  return { done, target, left: target - done };
};

function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const width = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="meter" title={label} role="img" aria-label={label}>
      <span style={{ width: `${width}%` }} />
    </div>
  );
}

const shade = (booked: number) => (booked >= 4 ? "b3" : booked >= 2 ? "b2" : "b1");

function ScheduleGrid({ clinician }: { clinician: Clinician }) {
  const dates = [...new Set(clinician.strip_14d.map((s) => s.date))];
  return (
    <div className="heat">
      <table>
        <thead>
          <tr>
            <th />
            {dates.map((date, index) => (
              <th key={date} className={index === 5 ? "week" : undefined}>
                {formatDate(date).split(" ").slice(0, 2).join(" ").replace(",", "")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(["AM", "PM"] as const).map((session) => (
            <tr key={session}>
              <th scope="row">{session}</th>
              {dates.map((date, index) => {
                const entry = clinician.strip_14d.find((s) => s.date === date && s.session === session);
                const off = !entry || entry.status === "off";
                const booked = entry?.booked ?? 0;
                const kind = off ? "off" : booked === 0 ? "open" : shade(booked);
                const label = `${formatDate(date)} ${session}: ${off ? "not in clinic" : booked ? `${booked} booked` : "nothing booked"}`;
                return (
                  <td key={date} className={index === 5 ? "week" : undefined}>
                    <span className={`cell ${kind}`} title={label}>{off ? "" : booked || ""}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="legend">
        <span className="cell off" /> Not in clinic
        <span className="cell open" /> Nothing booked
        <span className="cell b1" /> 1
        <span className="cell b2" /> 2 to 3
        <span className="cell b3" /> 4 or more appointments
      </p>
    </div>
  );
}

function ClinicianDetail({ clinician }: { clinician: Clinician }) {
  const logbook = Object.entries(clinician.logbook_targets);
  return (
    <div className="clin-detail">
      <div>
        <h3>Logbook</h3>
        {logbook.length === 0 && <p className="muted">No logbook targets.</p>}
        {logbook.map(([name, target]) => {
          const done = Math.min(target, clinician.logbook_done[name] ?? 0);
          return (
            <div className="log-row" key={name}>
              <span className="log-name">{name}</span>
              <Meter value={done} max={target} label={`${done} of ${target} done`} />
              <span className="log-count">{done}/{target}</span>
            </div>
          );
        })}
      </div>
      <div>
        <h3>Next 14 days</h3>
        <ScheduleGrid clinician={clinician} />
      </div>
    </div>
  );
}

export function CliniciansView({ data }: { data: ClinicianData }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const names = new Map(data.clinicians.map((c) => [c.id, c.name]));

  return (
    <>
      <div className="stats">
        <span>Available today<b>{data.metrics.clinicians_available_today}</b></span>
        <span>Average load, 7 days<b>{data.metrics.average_load_percent}%</b></span>
        <span>Students behind on logbook<b>{data.metrics.students_behind_targets}</b></span>
      </div>
      <section className="panel">
        <table className="grid clinicians">
          <thead>
            <tr>
              <th>Clinician</th><th>Today</th><th>Load, 7 days</th><th className="num">Free, 48h</th>
              <th>Logbook</th><th>Supervisor</th>
            </tr>
          </thead>
          {GRADES.map((grade) => {
            const group = data.clinicians.filter((c) => c.tier_name === grade);
            if (group.length === 0) return null;
            return (
              <tbody key={grade}>
                <tr className="group"><th colSpan={6}>{grade} <span>{group.length}</span></th></tr>
                {group.map((c) => {
                  const isOpen = expanded === c.id;
                  const log = logbookTotals(c);
                  return (
                    <Fragment key={c.id}>
                      <tr
                        className={`clickable ${isOpen ? "open-row" : ""}`}
                        aria-expanded={isOpen}
                        onClick={() => setExpanded(isOpen ? null : c.id)}
                      >
                        <td className="nowrap clin-name">
                          <span className="chev">{isOpen ? "▾" : "▸"}</span>{c.name}
                          {c.status !== "active" && <span className="tag amber">{sentence(c.status)}</span>}
                        </td>
                        <td className="nowrap">{c.today.length ? c.today.join(", ") : <span className="muted">Not in</span>}</td>
                        <td>
                          <div className="meter-cell">
                            <Meter value={c.load_percent} max={100} label={`${c.load_percent}% of chair time booked`} />
                            <span>{c.load_percent}%</span>
                          </div>
                        </td>
                        <td className="num">{c.free_in_48h_count}</td>
                        <td>
                          {log.target > 0 ? (
                            <div className="meter-cell">
                              <Meter value={log.done} max={log.target} label={`${log.done} of ${log.target} logbook cases done`} />
                              <span>{log.left ? `${log.left} left` : "Complete"}</span>
                            </div>
                          ) : <span className="muted">None</span>}
                        </td>
                        <td className="nowrap muted">{c.supervisor_id ? names.get(c.supervisor_id) : ""}</td>
                      </tr>
                      {isOpen && <tr className="detail"><td colSpan={6}><ClinicianDetail clinician={c} /></td></tr>}
                    </Fragment>
                  );
                })}
              </tbody>
            );
          })}
        </table>
      </section>
    </>
  );
}

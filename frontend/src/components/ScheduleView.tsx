import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDate, OFFER_REPLIES, refillOutcome, sentence, shiftWeekday, timeLeft, urgencyTone } from "../format";
import type { Candidate, FreeGap, ReleasedSlot, SlotItem, TodayData } from "../types";
import { DayCalendar } from "./DayCalendar";

const lengthOf = (start: string, end: string) => {
  const toMinutes = (clock: string) => Number(clock.slice(0, 2)) * 60 + Number(clock.slice(3));
  return toMinutes(end) - toMinutes(start);
};

function SuggestedPatients({ slotId, room, onOffered, onFindPatient }: {
  slotId: string;
  room: number;
  onOffered: () => void;
  onFindPatient: () => void;
}) {
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.getCandidates(slotId, room).then((res) => { if (active) setCandidates(res.candidates); }).catch(() => undefined);
    return () => { active = false; };
  }, [slotId, room]);

  const offer = async (caseId: string) => {
    setError(null);
    try {
      await api.offerSlot(caseId, slotId);
      onOffered();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!candidates) return null;
  return (
    <>
      <p className="section-title">Suggested patients</p>
      {candidates.length === 0 ? (
        <p className="empty">
          No waiting patient fits this time. <button className="link" onClick={onFindPatient}>Open the waiting list</button>
        </p>
      ) : (
        <div className="tablewrap">
          <table className="grid">
            <thead><tr><th>Patient</th><th>Urgency</th><th>Needs</th><th className="num">Length</th><th>Min. grade</th><th className="num">Waiting</th><th /></tr></thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={c.case_id}>
                  <td className="nowrap">{c.patient_name}</td>
                  <td><span className={`tag ${urgencyTone(c.urgency)}`}>{sentence(c.urgency)}</span></td>
                  <td className="needs" title={c.summary}>{c.summary}</td>
                  <td className="num nowrap">{c.minutes} min</td>
                  <td className="nowrap">{c.min_grade}</td>
                  <td className="num nowrap">{c.days_waiting} {c.days_waiting === 1 ? "day" : "days"}</td>
                  <td className="actions"><button className="btn small" onClick={() => offer(c.case_id)}>Text offer</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && <p className="form-error">{error}</p>}
    </>
  );
}

function FreeDetails({ gap, onChanged, onFindPatient, onClose }: {
  gap: FreeGap;
  onChanged: () => void;
  onFindPatient: () => void;
  onClose: () => void;
}) {
  return (
    <section className="panel drawer">
      <div className="panel-head">
        <h2>Free {gap.start} to {gap.end}</h2>
        <span className="muted">{gap.minutes} minutes, {gap.bay}, {gap.clinician.name}, {gap.clinician.tier_name}</span>
        <div className="right"><button className="btn small" onClick={onClose}>Close</button></div>
      </div>
      <SuggestedPatients key={gap.slot_id} slotId={gap.slot_id} room={gap.minutes} onOffered={onChanged} onFindPatient={onFindPatient} />
    </section>
  );
}

function SlotDetails({ slot, released, onOpenPatient, onOpenPhone, onCancel, onFindPatient, onChanged, onClose }: {
  slot: SlotItem;
  released?: ReleasedSlot;
  onOpenPatient: (id: string) => void;
  onOpenPhone: (token: string) => void;
  onCancel: (slot: SlotItem) => void;
  onFindPatient: () => void;
  onChanged: () => void;
  onClose: () => void;
}) {
  const canCancel = slot.booking && ["confirmed", "locked"].includes(slot.booking.state);
  const offers = released?.offers ?? [];
  const refill = slot.refill;
  const unfilled = !slot.patient && refill && refill.status !== "active" && refill.status !== "filled";
  const reasons = slot.booking?.match_reasons ?? [];

  return (
    <section className="panel drawer">
      <div className="panel-head">
        <h2>{slot.patient?.name ?? "Released chair"}</h2>
        {unfilled && <span className="tag red" role="alert">{refillOutcome(refill)}, still empty</span>}
        <span className="muted">{slot.start} to {slot.end}, {slot.bay}, {slot.clinician.name}, {slot.clinician.tier_name}</span>
        <div className="right">
          {slot.patient && <button className="btn small" onClick={() => onOpenPatient(slot.patient!.id)}>Open record</button>}
          {canCancel && <button className="btn small" onClick={() => onCancel(slot)}>Cancel appointment</button>}
          <button className="btn small" onClick={onClose}>Close</button>
        </div>
      </div>
      {slot.patient && slot.case && (
        <dl className="facts two">
          <dt>Reason for visit</dt><dd>{slot.case.summary_plain}</dd>
          <dt>Treatment</dt><dd>{slot.case.likely_procedures.join(", ") || "To be assessed"}</dd>
          <dt>Urgency</dt><dd>{sentence(slot.case.urgency)}</dd>
          {slot.patient.flags.length > 0 && <><dt>Flags</dt><dd>{sentence(slot.patient.flags.join(", "))}</dd></>}
        </dl>
      )}
      {reasons.length > 0 && (
        <>
          <p className="section-title">Why this match</p>
          <ul className="reasons">{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </>
      )}
      <div className={offers.length > 0 && unfilled ? "drawer-split" : undefined}>
      {offers.length > 0 && (
        <div>
          <p className="section-title">Standby offers</p>
          <div className="tablewrap">
            <table className="grid">
              <thead><tr><th>Patient</th><th>Reply</th>{!unfilled && <><th className="num">Time left</th><th /></>}</tr></thead>
              <tbody>
                {offers.map((offer) => {
                  const reply = OFFER_REPLIES[offer.response] ?? { label: sentence(offer.response), tone: "" };
                  return (
                    <tr key={offer.offer_id}>
                      <td className="nowrap"><button className="link" onClick={() => onOpenPatient(offer.patient_id)}>{offer.patient_name}</button></td>
                      <td><span className={`tag ${reply.tone}`}>{reply.label}</span></td>
                      {!unfilled && (
                        <>
                          <td className="num">{offer.response === "pending" ? timeLeft(offer.expires_at) : ""}</td>
                          <td className="actions"><button className="btn small" onClick={() => onOpenPhone(offer.token)}>Open phone</button></td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {unfilled && (
        <div>
          <SuggestedPatients
            key={slot.slot_id}
            slotId={slot.slot_id}
            room={lengthOf(slot.start, slot.end)}
            onOffered={onChanged}
            onFindPatient={onFindPatient}
          />
        </div>
      )}
      </div>
    </section>
  );
}

export function ScheduleView({
  day, released, selectedId, onSelect, onChangeDate, onOpenPatient, onOpenPhone, onCancel, onFindPatient, onChanged, onClearSelection,
}: {
  day: TodayData;
  released: ReleasedSlot[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onChangeDate: (date: string, slotId?: string) => void;
  onOpenPatient: (id: string) => void;
  onOpenPhone: (token: string) => void;
  onCancel: (slot: SlotItem) => void;
  onFindPatient: () => void;
  onChanged: () => void;
  onClearSelection: () => void;
}) {
  const selected = day.slots.find((s) => s.slot_id === selectedId);
  const gap = selected ? undefined : day.free.find((g) => g.slot_id === selectedId);
  const unfilled = released.filter((r) =>
    !r.booked && r.slot_id !== selectedId && (r.status === "exhausted" || r.status === "no_candidate"));

  return (
    <>
      {unfilled.map((chair) => (
        <div className="alert" role="alert" key={chair.slot_id}>
          <span>
            <strong>{refillOutcome(chair)}.</strong>{" "}
            {chair.bay}, {formatDate(chair.date)} at {chair.start} with {chair.clinician_name} is still empty.
          </span>
          <button className="btn small" onClick={() => onChangeDate(chair.date, chair.slot_id)}>Fill this chair</button>
        </div>
      ))}
      <div className="toolbar">
        <button className="btn" aria-label="Previous day" onClick={() => onChangeDate(shiftWeekday(day.date, -1))}>‹</button>
        <span className="date-title">{formatDate(day.date, "long")}</span>
        <button className="btn" aria-label="Next day" onClick={() => onChangeDate(shiftWeekday(day.date, 1))}>›</button>
        {day.date !== day.clinic_date && <button className="btn" onClick={() => onChangeDate(day.clinic_date)}>Today</button>}
        <span className="spacer" />
        <span className="muted">Appointments <b>{day.metrics.appointments}</b></span>
        <span className="muted">Chair time booked <b>{day.metrics.chair_time_percent}%</b></span>
        <span className="muted">Refilled <b>{day.metrics.cancellations_recovered_this_week}</b></span>
      </div>
      <div className="cal-area">
      {day.sessions.length === 0
        ? <p className="empty">No clinic sessions on this day.</p>
        : <DayCalendar day={day} selectedId={selectedId} onSelect={onSelect} />}
      {selected && (
        <SlotDetails
          slot={selected}
          released={released.find((r) => r.slot_id === selected.slot_id)}
          onOpenPatient={onOpenPatient}
          onOpenPhone={onOpenPhone}
          onCancel={onCancel}
          onFindPatient={onFindPatient}
          onChanged={onChanged}
          onClose={onClearSelection}
        />
      )}
      {gap && <FreeDetails gap={gap} onChanged={onChanged} onFindPatient={onFindPatient} onClose={onClearSelection} />}
      </div>
    </>
  );
}

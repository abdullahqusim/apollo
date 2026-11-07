import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { refillOutcome, sentence } from "../format";
import type { FreeGap, SlotItem, TodayData } from "../types";

const DAY_START = 9 * 60;
const DAY_END = 17 * 60;
const LUNCH = { start: 12 * 60 + 30, end: 13 * 60 + 30 };
const ROW_MINUTES = 15;
const ROWS = (DAY_END - DAY_START) / ROW_MINUTES;

const minutes = (clock: string) => {
  const [h, m] = clock.split(":").map(Number);
  return h * 60 + m;
};
const place = (start: string, end: string, row: number): CSSProperties => ({
  top: ((minutes(start) - DAY_START) / ROW_MINUTES) * row,
  height: ((minutes(end) - minutes(start)) / ROW_MINUTES) * row - 1,
});
const shortGrade = (grade: string) =>
  grade.replace("Qualified Dentist", "DDS").replace("Postgraduate", "PG").replace("Year ", "Y");

function slotState(slot: SlotItem): { className: string; label: string } {
  const refill = slot.refill;
  if (slot.booking?.state === "held") return { className: "held", label: "Awaiting reply" };
  if (slot.patient && slot.booking) {
    return refill?.status === "filled"
      ? { className: "refilled", label: "Refilled" }
      : { className: "", label: "" };
  }
  if (refill?.status === "active") return { className: "offering", label: `Standby: ${refill.pending} to reply` };
  if (refill) return { className: "unfilled", label: refillOutcome(refill) };
  return { className: "", label: "" };
}

function Appointment({ slot, row, selected, onSelect }: { slot: SlotItem; row: number; selected: boolean; onSelect: (id: string) => void }) {
  const state = slotState(slot);
  const height = ((minutes(slot.end) - minutes(slot.start)) / ROW_MINUTES) * row;
  const treatment = slot.case?.likely_procedures[0] ?? "";
  const title = [
    `${slot.start} to ${slot.end}`, slot.patient?.name, treatment,
    `${slot.clinician.name}, ${slot.clinician.tier_name}`, state.label,
  ].filter(Boolean).join("\n");

  return (
    <button
      className={`appt ${state.className} ${selected ? "selected" : ""}`}
      style={place(slot.start, slot.end, row)}
      aria-pressed={selected}
      title={title}
      data-selected={selected || undefined}
      onClick={() => onSelect(slot.slot_id)}
    >
      {height >= 15 && <span className="name">{slot.patient?.name ?? "Released"}</span>}
      {height >= 31 && <span className="line">{treatment || `${slot.start} to ${slot.end}`}</span>}
      {height >= 45 && state.label && <span className="state">{state.label}</span>}
      {height >= 60 && !state.label && slot.patient && slot.patient.flags.length > 0 && (
        <span className="line">{sentence(slot.patient.flags.join(", "))}</span>
      )}
    </button>
  );
}

function FreeBlock({ gap, row, selected, onSelect }: { gap: FreeGap; row: number; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button
      className={`cal-free ${selected ? "selected" : ""}`}
      style={place(gap.start, gap.end, row)}
      aria-label={`Free ${gap.start} to ${gap.end}, ${gap.bay}`}
      title={`Free ${gap.start} to ${gap.end}`}
      data-selected={selected || undefined}
      onClick={() => onSelect(gap.slot_id)}
    >
      Free {gap.minutes} min
    </button>
  );
}

export function DayCalendar({ day, selectedId, onSelect }: {
  day: TodayData;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const [row, setRow] = useState(18);
  const hours = [];
  for (let t = DAY_START; t < DAY_END; t += 60) hours.push(t);
  const height = row * ROWS;

  // The whole day always fits: rows take whatever height the window leaves.
  useLayoutEffect(() => {
    const box = scroller.current;
    if (!box) return;
    const measure = () => {
      const header = box.querySelector<HTMLElement>(".cal-bay")?.offsetHeight ?? 0;
      setRow(Math.max(6, (box.clientHeight - header) / ROWS));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, [day.bays.length]);

  return (
    <div className="calendar" ref={scroller}>
      <div className="cal-grid" style={{ "--bays": day.bays.length, "--row": `${row}px` } as CSSProperties}>
        <div className="cal-corner" />
        {day.bays.map((bay) => {
          const blocks = day.sessions.filter((s) => s.bay === bay);
          return (
            <div className="cal-bay" key={bay}>
              <strong>{bay}</strong>
              {blocks.map((block) => {
                const allDay = blocks.length > 1 && blocks[0].clinician.id === blocks[1].clinician.id;
                if (allDay && block !== blocks[0]) return null;
                return (
                  <span key={block.session} title={`${block.clinician.name}, ${block.clinician.tier_name}`}>
                    {allDay ? "" : `${block.session} `}{block.clinician.name.replace("Dr. ", "")} {shortGrade(block.clinician.tier_name)}
                  </span>
                );
              })}
            </div>
          );
        })}
        <div className="cal-times" style={{ height }}>
          {hours.map((t) => (
            <span key={t} style={{ top: ((t - DAY_START) / ROW_MINUTES) * row }}>{`${String(t / 60).padStart(2, "0")}:00`}</span>
          ))}
        </div>
        {day.bays.map((bay) => (
          <div className="cal-col" key={bay} style={{ height }}>
            {day.sessions.filter((s) => s.bay === bay).map((block) => (
              <div className="cal-work" key={block.session} style={place(block.start, block.end, row)} />
            ))}
            <div className="cal-lunch" style={{ top: ((LUNCH.start - DAY_START) / ROW_MINUTES) * row, height: ((LUNCH.end - LUNCH.start) / ROW_MINUTES) * row }}>Lunch</div>
            {day.free.filter((g) => g.bay === bay).map((gap) => (
              <FreeBlock key={gap.slot_id} gap={gap} row={row} selected={gap.slot_id === selectedId} onSelect={onSelect} />
            ))}
            {day.slots.filter((s) => s.bay === bay).map((slot) => (
              <Appointment key={slot.slot_id} slot={slot} row={row} selected={slot.slot_id === selectedId} onSelect={onSelect} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

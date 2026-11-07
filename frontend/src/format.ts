const zone = "Europe/London";

export const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: zone });

export const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: zone,
  });

/** Takes a date-only string such as 2026-11-09. */
export const formatDate = (date: string, style: "long" | "short" = "short") => {
  const value = new Date(`${date}T12:00:00Z`);
  return value.toLocaleDateString(
    "en-GB",
    style === "long"
      ? { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }
      : { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" },
  );
};

/** A date of birth is YYYY-MM-DD, or the caller's words if they couldn't be read as a date. */
export const formatBirthDate = (value: string) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return new Date(`${value}T12:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });
};

/** Moves to the next or previous weekday. */
export const shiftWeekday = (date: string, direction: 1 | -1) => {
  const value = new Date(`${date}T12:00:00Z`);
  do {
    value.setUTCDate(value.getUTCDate() + direction);
  } while (value.getUTCDay() === 0 || value.getUTCDay() === 6);
  return value.toISOString().slice(0, 10);
};

export const sentence = (value: string) => {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};

export const minutesLeft = (iso: string) => Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 60000));

export const refillOutcome = (refill: { status: string; declined: number; sent: number }) => {
  if (refill.status === "no_candidate") return "No standby match";
  if (refill.declined === refill.sent) return `All ${refill.sent} declined`;
  return `${refill.sent} offered, none took it`;
};

export const WORKLIST_TYPES: Record<string, string> = {
  red_flag: "Emergency",
  borderline_complexity: "Tutor review",
  symptoms_unclear: "Unclear symptoms",
  low_confidence: "Unclear symptoms",
  urgency_disagreement: "Urgency disagreement",
  asked_for_person: "Asked for a person",
  identity_unconfirmed: "Identity unconfirmed",
  no_backfill_candidate: "No standby match",
  offers_exhausted: "Chair not refilled",
  no_match: "No slot found",
  match_declined: "Turned down 3 times",
  other: "Other",
};

export const CALL_OUTCOMES: Record<string, string> = {
  emergency_redirected: "Sent to A&E",
  intake_completed: "Intake completed",
  booked: "Booked",
  cancelled: "Cancelled",
  rescheduled: "Rescheduled",
  escalated: "Passed to reception",
  abandoned: "Call dropped",
};

export const OFFER_REPLIES: Record<string, { label: string; tone: string }> = {
  pending: { label: "Waiting for reply", tone: "amber" },
  accepted: { label: "Accepted", tone: "green" },
  declined: { label: "Declined", tone: "red" },
  filled_by_other: { label: "Too late, chair taken", tone: "" },
  expired: { label: "No reply", tone: "red" },
};

export const EVENT_LABELS: Record<string, string> = {
  offers_sent: "Standby offers sent",
  offers_exhausted: "Standby offers ran out",
  parallel_offer_claimed: "Standby offer accepted",
  needs_attention_resolved: "Worklist item closed",
  simulation_run: "Week replayed",
  match_offered: "Appointment offered",
  match_accepted: "Appointment accepted",
  match_declined: "Appointment declined",
  match_none: "No slot found",
  batch_run: "Waiting list matched",
};

export const urgencyTone = (urgency?: string) =>
  urgency === "emergency" ? "red" : urgency === "urgent" ? "amber" : urgency === "soon" ? "blue" : "";

export const OUTCOME_TEXT: Record<string, string> = {
  offered: "Triaged and matched. An appointment offer has been texted.",
  waiting: "Triaged. No slot fits yet, so the patient is on the waiting list.",
  review: "Sent to the Worklist for a tutor to check.",
  emergency: "Emergency. The patient was told to go to A&E and nothing was booked.",
  updated: "Already on the list. Availability updated.",
  incomplete: "The call had no name or phone number. Added to the Worklist.",
};

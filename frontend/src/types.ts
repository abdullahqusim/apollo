export type Role = "receptionist" | "clinical";
export type Availability = Record<string, { am: boolean; pm: boolean }>;

export interface RefillSummary {
  status: "active" | "filled" | "exhausted" | "no_candidate";
  sent: number;
  declined: number;
  no_reply: number;
  pending: number;
}

export interface SlotItem {
  slot_id: string;
  bay: string;
  session: "AM" | "PM";
  start: string;
  end: string;
  clinician: { id: string; name: string; tier: number; tier_name: string };
  booking?: { id: string; state: string; reason?: string; match_reasons: string[] } | null;
  patient?: { id: string; name: string; flags: string[]; token: string } | null;
  case?: { id: string; summary_plain: string; urgency: string; complexity: number; likely_procedures: string[] } | null;
  refill?: RefillSummary | null;
}

export interface FreeGap {
  slot_id: string;
  bay: string;
  start: string;
  end: string;
  minutes: number;
  clinician: SlotItem["clinician"];
}

export interface DaySession {
  bay: string;
  session: "AM" | "PM";
  start: string;
  end: string;
  clinician: SlotItem["clinician"];
}

export interface TodayData {
  date: string;
  clinic_date: string;
  bays: string[];
  sessions: DaySession[];
  slots: SlotItem[];
  free: FreeGap[];
  metrics: { appointments: number; chair_time_percent: number; cancellations_recovered_this_week: number };
}

export interface Offer {
  offer_id: string;
  patient_id: string;
  patient_name: string;
  response: string;
  expires_at: string;
  token: string;
}

export interface ReleasedSlot extends RefillSummary {
  slot_id: string;
  date: string;
  start: string;
  bay: string;
  booked: boolean;
  clinician_name: string;
  offers: Offer[];
}

export interface Candidate {
  case_id: string;
  patient_id: string;
  patient_name: string;
  urgency: string;
  summary: string;
  minutes: number;
  min_grade: string;
  days_waiting: number;
}

export interface WorklistItem {
  id: string;
  reason: string;
  summary: string;
  suggested_action: string;
  status: string;
  created_at: string;
  patient?: { id: string; name: string } | null;
  slot?: { id: string; date: string } | null;
}

export interface Call {
  call_id: string;
  patient_id?: string;
  patient_name: string;
  patient_phone: string;
  started_at: string;
  outcome: string;
  summary: string;
  transcript: { speaker: string; text: string }[];
  case?: { urgency: string } | null;
}

export interface Appointment {
  state: "offered" | "booked";
  date: string;
  start: string;
  bay: string;
  clinician_name: string;
  reasons: string[];
}

export interface WaitingCase {
  case_id: string;
  patient_id: string;
  patient_name: string;
  phone: string;
  urgency: string;
  required_tier: number;
  status: string;
  flags: string[];
  short_notice_ok: boolean;
  summary_plain: string;
  likely_procedures: string[];
  days_waiting: number;
  channel: "phone" | "online";
  appointment?: Appointment | null;
}

export interface Clinician {
  id: string;
  name: string;
  tier_name: string;
  supervisor_id?: string | null;
  status: string;
  logbook_targets: Record<string, number>;
  logbook_done: Record<string, number>;
  load_percent: number;
  free_in_48h_count: number;
  today: string[];
  strip_14d: { date: string; session: "AM" | "PM"; status: string; booked: number }[];
}

export interface ClinicianData {
  clinicians: Clinician[];
  metrics: {
    clinicians_available_today: number;
    average_load_percent: number;
    students_behind_targets: number;
  };
}

export interface AuditEvent {
  id: string;
  at: string;
  actor: string;
  type: string;
  reason: string;
}

export interface Shortlist {
  patient_name: string;
  shortlist: {
    clinician_id: string;
    name: string;
    tier_name: string;
    load_percent: number;
    logbook_gap: number;
    reason_summary: string;
    candidate_slots: { slot_id: string; date: string; session: string; bay: string; start: string }[];
  }[];
}

export interface MedicalHistory {
  conditions: string[];
  allergies: string[];
  medications: string[];
  declined: boolean;
}

export interface PatientRecordData {
  patient: {
    name: string;
    phone: string;
    date_of_birth?: string | null;
    status: string;
    contact_token: string;
    flags: string[];
    short_notice_ok: boolean;
    wants_earlier: boolean;
    dna_count: number;
    availability: { grid: Availability; source: string };
  };
  case: {
    id: string;
    summary_plain: string;
    urgency: string;
    agent_urgency?: string | null;
    complexity: number;
    confidence: string;
    status: string;
    channel: "phone" | "online";
    clinical_panel?: {
      complaint_quote: string;
      medical_history?: MedicalHistory | null;
      possible_issues: string[];
      not_ruled_out: string[];
      likely_procedures: string[];
      tutor_review?: { decision: string; by: string } | null;
    };
  } | null;
  appointment?: Appointment | null;
  call_history: { id: string; summary: string; outcome: string; started_at: string }[];
}

export interface ThreadData {
  patient: { name: string; phone: string; status: string };
  messages: { id: string; body: string; direction: "in" | "out"; created_at: string }[];
  can_answer_offer: boolean;
  offer_expires_at: string | null;
  booking: { date: string; start: string } | null;
}

export interface PhoneEntry {
  name: string;
  token: string;
}

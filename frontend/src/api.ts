import type {
  AuditEvent, Availability, Call, Candidate, ClinicianData, PatientRecordData, PhoneEntry,
  ReleasedSlot, Role, Shortlist, ThreadData, TodayData, WaitingCase, WorklistItem,
} from "./types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${res.status})`);
  }
  return res.json();
}

const post = <T = unknown>(url: string, body?: unknown) =>
  request<T>(url, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export interface IntakeResult {
  outcome: string;
  token?: string;
  redirect_url?: string;
}

export const api = {
  getDay: (date: string | null) => request<TodayData>(`/api/console/today${date ? `?date=${date}` : ""}`),
  getCalls: () => request<{ calls: Call[] }>("/api/console/overnight"),
  getWorklist: () => request<{ items: WorklistItem[] }>("/api/console/needs_attention"),
  getReleased: () => request<{ released: ReleasedSlot[] }>("/api/console/released_slots"),
  getWaitingList: () => request<{ cases: WaitingCase[] }>("/api/console/waitlist"),
  getClinicians: () => request<ClinicianData>("/api/console/clinicians"),
  getAuditLog: () => request<{ events: AuditEvent[] }>("/api/console/activity?limit=200"),
  getPatient: (id: string, role: Role) => request<PatientRecordData>(`/api/console/patient/${id}?role=${role}`),
  getShortlist: (caseId: string) => request<Shortlist>(`/api/console/assign_shortlist/${caseId}`),
  getCandidates: (slotId: string, minutes: number) =>
    request<{ candidates: Candidate[] }>(`/api/console/slot_candidates/${slotId}?minutes=${minutes}`),
  getPhones: () => request<{ phones: PhoneEntry[] }>("/api/console/phones"),

  matchWaitingList: () => post<{ waiting: number; offered: number; unmatched: number }>("/api/console/match_waiting_list"),
  offerSlot: (case_id: string, slot_id: string) => post("/api/console/offer_slot", { case_id, slot_id }),
  assign: (data: { case_id: string; slot_id: string; reason_chip: string; notes?: string }) =>
    post("/api/console/assign", data),
  reviewTriage: (data: { case_id: string; decision: string; notes?: string }) =>
    post("/api/console/review_triage", data),
  closeWorklistItem: (item_id: string, action: "resolve" | "dismiss", notes: string) =>
    post("/api/console/resolve_attention", { item_id, action, notes }),
  cancelBooking: (booking_id: string) => post("/api/console/cancel_booking", { booking_id }),
  replayWeek: () => post<{ metrics: Record<string, string | number> }>("/api/console/simulate_week"),
  resetDemo: () => post("/api/console/reset_demo"),
  sendCall: (payload: unknown) => post<IntakeResult>("/webhooks/call-ended", payload),

  register: (data: {
    name: string; phone: string; problem: string; availability: Availability;
    short_notice_ok: boolean; wants_earlier: boolean;
  }) => post<IntakeResult>("/api/patient/register", data),
  getThread: (token: string) => request<ThreadData>(`/api/patient/${token}`),
  reply: (token: string, text: string) => post(`/api/patient/${token}/reply`, { text }),
};

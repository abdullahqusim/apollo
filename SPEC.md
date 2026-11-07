# Apollo: spec

Working spec for GUH 2026. Everything here is a prototype on synthetic data.

## 1. Problem and pitch

University dental hospitals run student clinics that treat volunteer patients for free. At Manchester the
volunteer scheme has been closed to new patients since May 2026, while other schools (Glasgow, Aberdeen) have
publicly appealed for *more* patients. The problem is not raw capacity. It is **case-mix matching**: students need
specific cases to sign off competencies, patients have specific needs, and nothing connects the two. Complex cases
are currently turned away instead of routed to someone qualified.

We build:
- a 24/7 voice front door (ElevenLabs) for intake, cancellations and reschedules
- a backend that owns all state: patients, triage, clinicians, slots, matching, cascades
- a receptionist console (plus a clinical view for tutors and dentists)
- patient message pages that stand in for SMS in the demo

## 2. Surfaces and who sees what

| Surface | User | Sees |
|---|---|---|
| Voice agent | Patient | Never sees or hears any diagnosis. Intake, cancel, reschedule, slot offers. |
| Receptionist console | Clinic admin | Urgency, complexity, tier, flags, plain summary, schedules, clinician load. **No differential.** |
| Clinical view | Tutors, dentists | Everything above plus possible issues, evidence, likely procedures. |
| Patient messages (`/p/<token>`) | Patient | Offers, confirmations, availability grid. |

Health data is special category data under GDPR: role-based views are our data-minimisation story.

## 3. Data model

- **Patient**: id, name, phone, date_of_birth, contact_token, availability, short_notice_ok, wants_earlier, notice_needed_days,
  flags (anxious, interpreter, access_needs), dna_count, status, created_at
- **Availability**: grid of weekday x {AM, PM}, blackout_dates[], source (`call` | `patient_confirmed`), confirmed_at
- **Case**: id, patient_id, summary_plain, complaint_quote, key_details{duration, pain_score, swelling, triggers,
  history_flags}, urgency, agent_urgency, medical_history{conditions[], allergies[], medications[], declined} (clinical
  view only; null means never asked), complexity, confidence, possible_issues[], not_ruled_out[], likely_procedures[],
  required_tier, status, tutor_review{decision, by, at}, confirmed_at_assessment{agree|edit|reject, notes}
- **Clinician**: id, name, tier, year (students), supervisor_id, competencies[], logbook_targets{procedure: n},
  logbook_done{procedure: n}, sessions[], status (active, leave, exam_week, off_clinic)
- **ClinicSession**: id, clinician_id, bay, date, session (AM/PM), start, end. A clinician's working block.
- **Slot**: id, clinician_id, bay, date, session, start, end, booking_id. One appointment cut from a session. Free time
  is whatever a session has left, and is never stored.
- **Booking**: id, slot_id, case_id, state, held_until, offers_made, reason, created_by (`engine` | staff name)
- **Offer**: id, slot_id, patient_id, mode (`single` | `parallel` | `choice`), sent_at, expires_at, response
- **Event** (audit log): id, at, actor (`Automated line` | staff name), type, entity, payload, reason

## 4. Triage

Two separate scores, never merged into one number.

**Urgency** (how soon):
| Class | Meaning | Action |
|---|---|---|
| Emergency | swelling spreading to eye/neck, difficulty breathing or swallowing, uncontrolled bleeding, facial trauma, high fever | Stop intake. Direct to NHS 111 / A&E. Never book. Log + Needs attention. |
| Urgent | needs seeing within 48h | Immediate greedy match |
| Soon | within 2 weeks | Next routine batch, priority |
| Routine | course of treatment | Routine batch |

**Complexity 1-5** (who can treat). Maps to the minimum tier:
| Complexity | Minimum tier |
|---|---|
| 1 | Year 3 |
| 2 | Year 4 |
| 3 | Year 5 |
| 4 | Postgrad |
| 5 | Qualified dentist |
(Thresholds per procedure live in a config table; this is the default.)

**Confidence** (high / medium / low) on the triage. Low means too little to tell what the problem is.

**Auto-match by default.** A person only checks a case that is low confidence (too little information) or urgent with
complexity 4+ (too severe). Accepting matches it as normal. Denying closes it and texts the patient. Everything else,
including medium confidence, is matched straight away and the patient answers YES or NO by text.

**Returning callers.** A second call is triaged again. Urgency only ever goes up: getting worse raises the case and adds
a flag, and any existing appointment stays put until a person moves it. An emergency cancels their appointment, withdraws
any offer and releases the chair.

**Denied symptoms.** "No trouble breathing" is not a red flag. Only wording right beside the symptom counts as a denial,
so "No, I can't breathe" stays an emergency.

**Clinical panel** (clinical view only):
- complaint in patient's own words (quoted)
- key details
- possible issues ranked High / Medium / Low (no percentages), each linked to supporting transcript lines
- not ruled out (serious items that would change urgency)
- likely procedures (these drive complexity, tier and logbook matching)
- confirmed at assessment: clinician agrees / edits / rejects -> gives a triage accuracy metric

Labels: "Possible issues for clinical review", never "Diagnosis". Provisional triage, confirmed by a clinician at
first appointment. In a real deployment this would likely need the MHRA software-as-medical-device pathway.

## 5. Clinician tiers and matching rules

Tiers, top to bottom: qualified dentist > postgrad > year 5 > year 4 > year 3.

Choose the clinician for a case by, in strict order:
1. Competent, at the **lowest** eligible tier.
2. Free within the urgency window (only move up a tier if no one eligible is free).
3. Students: case fills an outstanding logbook gap (teaching value and fairness between students).
4. Lower combined load (past 7 days + next 7 days).
5. Longest since their last case of this procedure type.

**Load** = booked chair time / available chair time, so part-time clinicians compare fairly.

The same rules rank the shortlist for manual assignment, so the console and the engine agree.

## 6. Scheduling engine

### Principle
Stability over optimality. The engine only fills **free or released capacity**. It never moves a confirmed booking
to tidy the schedule.

### Booking states
`proposed -> held -> confirmed -> locked -> attended | dna`, plus `cancelled`.
- proposed: engine may change freely (patient not told)
- held: offer out, timer running. **One active hold per patient.**
- confirmed: frozen, except forced moves (clinician unavailable): one rebook, top priority, receptionist notified
- locked: within 48h. Any change goes to the receptionist, not automatic.

### Match the course, not the slot
The engine assigns a patient to a clinician for the **course of treatment** and books the **first** appointment.
Follow-ups are booked chairside by the clinician with the patient present.

### Horizons
- **0-48h (urgent):** event-driven greedy match as soon as the case is accepted.
- **3-21 days (routine):** nightly batch. Assignment problem over pending cases x free slots, confirmed bookings
  fixed. OR-Tools CP-SAT. Constraints: competency/tier, availability, notice needed, one hold per patient.
- **Beyond 21 days:** not booked. Stays on the waitlist (rolling window; far-ahead bookings cancel more).

### Waitlist priority (strict order)
1. Urgency class
2. Days waiting (prevents starvation)
3. Teaching value (fills a logbook gap)

### Offers
- Urgent: single slot, auto-assigned.
- Routine: choice of 2-3 slots that fit the patient's availability. Hold only the first; show others as
  "if still available". Unpicked options released immediately.
- Reply windows by urgency: urgent 30 min, soon 4h, routine 24h.

### Cascade rules (cancellations and no-replies)
- Released slot goes first to the **standby pool** (patients who opted in to short notice).
- **No dominoes:** never move a confirmed patient to fill another slot. Exception: patients who opted in to
  "earlier if available". Chain depth max 1: their old slot is released but does not trigger another move.
- Same-day slots: offer to top 3 standby patients in parallel, first confirm wins, others get
  "already filled, you keep your place".
- Further-out slots: sequential offers.
- Caps:
  - max 3 offers per slot, then escalate to receptionist or leave open
  - max 2 changes offered per patient per course
  - no reply -> 24h cooldown before another offer; patient keeps waitlist position
  - never offer the same slot to the same patient twice
- Late cancellation (<24h): offer only to urgent queue + short-notice standby. No wide cascade.
- Quiet hours: no automated calls 21:00-08:00. Messages queued for morning.

Every assignment stores a plain-English `reason`, shown in the console.

## 7. Availability capture

On the call, keep it light:
- "Any days you can never come in?"
- "Mornings or afternoons better, or either?"
- short notice OK? earlier if available?
- Read back and confirm yes/no.
- Day names only. Never ask for spoken dates or numbers (worst case for speech recognition).

LLM converts the answer into the availability grid (source = `call`).

After the call: message with a link to a pre-filled tappable grid + blackout dates (source = `patient_confirmed`).

Availability older than ~4 weeks gets a re-confirm message before matching.

Phone-only patients: the agent offers at most 2 specific times aloud ("Tuesday at ten, or Thursday at two?").

## 8. Messaging layer

One function: `send(patient, message)`. There is no real SMS: the **demo** adapter writes to the in-app inbox shown
at `/p/<token>`, which updates live by polling (section 16).

Message types: `joined`, `availability_check`, `offer_single`, `offer_choice`, `offer_parallel`, `confirmed`,
`already_filled`, `reminder`, `cancelled`, `changed`.

## 9. Voice agent tool contract (backend <-> ElevenLabs)

The voice agent holds no state. It calls these tools and posts a result when the call ends.
**Agree this first.**

| Tool | Input | Output |
|---|---|---|
| `lookup_patient` | phone, name?, dob? | patient_id or null, upcoming bookings |
| `create_intake` | patient details, availability_text, transcript_so_far | patient_id, case_id |
| `submit_triage` | case_id, complaint_quote, key_details, red_flags[] | urgency, next_step (`book` / `emergency` / `review`) |
| `get_options` | case_id or booking_id, count (<=2 by voice) | slots[] with spoken labels |
| `book_slot` | case_id, slot_id | booking_id, state |
| `cancel_booking` | booking_id, reason | ok |
| `reschedule_booking` | booking_id | options (same as get_options) |
| `escalate` | patient_id?, reason (`asked_for_person` / `identity_unconfirmed` / `unclear` / `other`), summary | ticket_id |

End-of-call webhook `POST /webhooks/call-ended`:
```json
{
  "call_id": "...",
  "direction": "inbound|outbound",
  "patient_id": "... or null",
  "outcome": "intake_completed|booked|cancelled|rescheduled|emergency_redirected|escalated|abandoned",
  "transcript": [{"speaker": "patient|agent", "text": "...", "t": 12.4}],
  "summary": "...",
  "started_at": "...",
  "ended_at": "..."
}
```

Add `caller_phone` so we can text the patient. Optional: `caller_name`, `caller_dob`, `availability_text`,
`short_notice_ok`, `wants_earlier`, `conditions[]`, `allergies[]`, `medications[]`, `history_declined`,
`agent_urgency` (`urgent|soon|routine`). Anything not sent is read from the transcript, apart from `agent_urgency`.
Repeat `call_id`s are ignored.

Urgency: the agent and triage both rate the call, and the more urgent rating is used. A disagreement stays on the
case and in the audit log, but does not hold up matching. `emergency_redirected` always counts as an emergency,
even if triage disagrees, so a caller told to dial 999 is never booked.

Outbound (if supported): `POST /calls/outbound {patient_id, purpose: "offer", slot_ids[]}` -> agent offers
<=2 times, calls `book_slot` or declines.

Voice agent rules: never states a diagnosis; red flags -> emergency script; "speak to a person" -> `escalate`.

## 10. Receptionist console

Look: desktop clinical software. Title bar, flat tabs, grey chrome, ruled data grids, status bar, one blue. No
cards, pills, emoji, gradients on content, chat bubbles, or the word "AI". The agent is "Automated line". No NHS/MFT
logos.

Tabs:
1. **Schedule**: day calendar, bays x 15-minute rows, 09:00 to 17:00 with lunch. Appointment length comes from the
   procedure, so days have uneven blocks and gaps. Selecting an appointment opens its details below and switches the
   patient phone to that patient. A released chair shows who it was offered to, their replies and time left. Selecting
   a free gap suggests waiting patients who fit it.
2. **Flags** (human-in-the-loop queue): emergencies, too severe, too little information, got worse, asked for a person,
   identity unconfirmed, no slot for an urgent case, no reply to an urgent offer, offers turned down. Too severe and too little information are accepted or
   denied. The rest are marked done. Unfilled chairs stay in Schedule. Any row opens the patient record.
3. **Calls**: every call, newest first. A row opens the patient record. Callers with no record show the transcript.
4. **Waiting list**: stages enquiry -> intake done -> awaiting tutor -> accepted -> scheduled -> in treatment ->
   discharged. Sorted urgency then days waiting. Columns: urgency, complexity, grade, flags, availability source.
5. **Clinicians**: row per clinician: grade, supervisor, load, free in next 48h, logbook outstanding, status. Click a
   row for logbook detail and the 14-day schedule. Above the table: available today, average load, students behind.

Patient record: details, plain summary, availability, bookings, calls with transcripts. Clinical panel only for clinical roles.
Audit log (Tools menu): every action with actor and reason.

Manual assignment: "Assign" opens eligible clinicians, ranked, with load shown and the first marked as recommended.
Choosing anyone else needs a reason (patient request, continuity, clinician request, other).

## 11. Patient pages

- `/join`: the online version of the call. Same questions (name, date of birth, mobile, problem in their own words,
  medical history, availability, short notice, earlier appointments), same intake, same outcomes.
- `/p/<token>`: the patient's text thread, live. Yes and No answer an offer. Cancel appointment releases the chair.
- `/phone` and the console's Patient phone panel show the same thread in a phone frame for any patient.
- Parallel offers to several judges demonstrate first-confirm-wins live.
- Console has a **Reset demo** button. Laptop phone-frame fallback if venue wifi fails.

## 12. Simulation ("replay a week")

Not built. The first version showed fixed numbers, so it was removed rather than presented as results.

## 13. Guardrails summary

- No diagnosis to patients, ever; differential is clinical-view only
- Emergency red flags -> NHS 111 / A&E script, never booked
- Low confidence -> human review, no auto-match
- PII detection and prompt-injection filtering on transcripts before LLM processing
- Cascade caps and quiet hours (section 6)
- Full audit log with actor and reason

## 14. Demo script (~3 min)

1. Call the line: intake for a routine case; second call mentions swelling -> emergency mode.
2. Console: case appears; tutor approves a borderline case.
3. Clinicians screen: show load and logbook gaps behind a match.
4. Judges scan QR, join standby. Cancel an appointment on stage. Offers land on judges' phones; first to accept
   wins; board refills.

## 15. Build split

- **Voice (duo):** ElevenLabs agent, scripts, red-flag handling, tool calls in section 9.
- **Backend + engine + console + patient pages (Alqavi):** sections 3-8, 10-12.

MVP cut if short on time: triage + Needs attention + Today + cascade + patient pages. Drop the nightly CP-SAT batch
(greedy only) and the Clinicians expand view last.

## 16. Stack

Everything runs locally on one laptop as a single process.

- **Backend:** FastAPI with one uvicorn worker. OR-Tools for the nightly batch.
- **State:** no database. In-memory Pydantic objects behind one lock, with no `await` while it is held. Write a JSON
  snapshot after each change (temp file, then rename) and load it on startup. Reset demo reloads the seed data.
- **Frontend:** Vite + React + TypeScript with plain CSS. Built to static files, served by FastAPI.
- **Live updates:** console and patient pages poll every 1-2s for events since the last one seen. No SSE: quick
  tunnels do not support it.
- **Triage:** Claude Haiku 5.5 (`claude-haiku-5-5`) at low effort with structured output. A red-flag keyword check
  runs first. Refusals, API errors and invalid results go to Needs attention.
- **Phone line:** Twilio number connected to the ElevenLabs agent. Twilio is voice only: patient messages stay in the
  demo adapter (section 8).
- **Public access:** Cloudflare quick tunnel (`cloudflared tunnel --url http://localhost:8000`) for ElevenLabs and
  judges' phones. The URL changes on restart, so start it once and leave it running; if it restarts, update the URL in
  ElevenLabs and regenerate the QR code.
- **Access control:** password on console routes, shared secret on ElevenLabs tool endpoints, unguessable patient tokens.
- **Demo day:** the laptop needs internet for voice, triage and the tunnel. Keep it awake and plugged in, with a phone
  hotspot as backup. Test the full flow through the tunnel URL on mobile data beforehand.

## 17. Open questions

- Does the ElevenLabs setup support outbound calls?

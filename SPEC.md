# Dental clinic matching system: spec

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

- **Patient**: id, name, phone, contact_token, availability, short_notice_ok, wants_earlier, notice_needed_days,
  flags (anxious, interpreter, access_needs), dna_count, status, created_at
- **Availability**: grid of weekday x {AM, PM}, blackout_dates[], source (`call` | `patient_confirmed`), confirmed_at
- **Case**: id, patient_id, summary_plain, complaint_quote, key_details{duration, pain_score, swelling, triggers,
  history_flags}, urgency, complexity, confidence, possible_issues[], not_ruled_out[], likely_procedures[],
  required_tier, status, tutor_review{decision, by, at}, confirmed_at_assessment{agree|edit|reject, notes}
- **Clinician**: id, name, tier, year (students), supervisor_id, competencies[], logbook_targets{procedure: n},
  logbook_done{procedure: n}, sessions[], status (active, leave, exam_week, off_clinic)
- **Slot**: id, clinician_id, bay, date, session (AM/PM), start, end
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

**Confidence** (high / medium / low) on the triage. Low confidence = "symptoms unclear" -> Needs attention, no auto-match.

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

One function: `send(patient, message)`. Adapters:
- **demo** (default): writes to the in-app inbox shown at `/p/<token>`, pushed live
- **twilio** (optional, only if time): real SMS

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

Outbound (if supported): `POST /calls/outbound {patient_id, purpose: "offer", slot_ids[]}` -> agent offers
<=2 times, calls `book_slot` or declines.

Voice agent rules: never states a diagnosis; red flags -> emergency script; "speak to a person" -> `escalate`.

## 10. Receptionist console

Look: enterprise hospital software. Left nav, site/date selector, dense tables, muted status pills, single blue
accent. No sparkles, gradients, chat bubbles, or the word "AI". The agent is "Automated line". No NHS/MFT logos.

Screens:
1. **Today**: bays x AM/PM grid. Slot: student, patient, treatment, status, tier colour; refilling slots show live
   cascade status. Top strip: chairs filled today, open exceptions, waitlist size, cancellations recovered this week.
2. **Overnight summary** (first thing in the morning): calls, triaged, awaiting review, urgent at top.
3. **Needs attention** (human-in-the-loop queue): red flags, asked for a person, identity unconfirmed, symptoms
   unclear, borderline complexity (tutor), no backfill candidate, cascade exhausted. Each item: two-line summary,
   suggested action, approve / override.
4. **Cascade panel**: held slot, student need, ranked candidates with reasons, offer status, reply timer.
5. **Waitlist**: stages enquiry -> intake done -> awaiting tutor -> accepted -> scheduled -> in treatment ->
   discharged. Sorted urgency then days waiting. Columns: urgency, complexity, tier, flags, availability freshness.
6. **Clinicians**: row per clinician: tier, supervisor, competencies, load last 7 / next 7, free in next 48h,
   status. Expand: 14-day AM/PM strip, upcoming appointments, case mix, outstanding logbook needs.
   Top: clinicians available today, average load next 7 days, students behind on logbook targets.
7. **Patient drawer**: details, plain summary, availability grid with source and last confirmed, call history with
   transcript summaries, bookings, flags. Clinical panel only for clinical roles.
8. **Activity log**: every action with actor and reason.

Manual assignment: "Assign" opens a shortlist of eligible clinicians, engine-ranked, load shown, tie-break stated.
Overrides need a reason chip (patient request, continuity, clinician request, other).

## 11. Patient demo pages

- `/join` (QR on a slide): first name, preset scenario (no free-text symptoms), short notice OK, AM/PM preference.
  Creates a standby patient.
- `/p/<token>`: plain message thread, live. Offers with tap-to-pick and countdown, confirm/change/cancel,
  availability grid.
- Generic styling, not a clone of any messaging app.
- Parallel offers to several judges demonstrate first-confirm-wins live.
- Console has a **Reset demo** button. Laptop phone-frame fallback if venue wifi fails.

## 12. Simulation ("replay a week")

Seeded synthetic week: random cancellations, DNAs, new cases. Live metrics:
- chair utilisation
- average wait by urgency class
- urgent window breaches
- **reschedules per patient** (churn; target: none moved more than once)
- triage agreement with clinician (from synthetic assessments)

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
5. Run the week simulation: show the metrics.

## 15. Build split

- **Voice (duo):** ElevenLabs agent, scripts, red-flag handling, tool calls in section 9.
- **Backend + engine + console + patient pages (Alqavi):** sections 3-8, 10-12.

MVP cut if short on time: triage + Needs attention + Today + cascade + patient pages. Drop the nightly CP-SAT batch
(greedy only), the Clinicians expand view, and the simulation last.

## 16. Open questions

- Stack. Proposed: FastAPI (Python, OR-Tools) + SQLite/Postgres backend, Next.js console, SSE for live updates.
- Does the ElevenLabs setup support outbound calls?
- Product name.

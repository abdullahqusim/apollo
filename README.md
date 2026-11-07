# Apollo

Scheduling and case-mix matching for student dental clinics. Prototype on synthetic data, built for GUH 2026.

Student clinics need specific cases for logbook sign-off, patients arrive with unpredictable needs, and cancellations
leave chairs empty. Apollo takes intake by phone or online, triages it, matches each case to the lowest competent
clinician in a slot that fits the patient, and texts them to confirm. Cancelled chairs go to standby patients.

## How a patient moves through Apollo

1. **Intake.** A call ends and the transcript arrives at `POST /webhooks/call-ended`, or the patient fills in `/join`.
   Both ask for name, date of birth, mobile, the problem, medical history, availability, short notice and earlier
   appointments, and both run `process_intake` in `backend/pipeline.py`.
2. **Triage.** Emergencies are told to go to A&E and are never booked. Calls with too little information, and urgent
   cases that need a postgraduate or dentist, are flagged for someone to accept or deny. Everything else goes straight
   to matching.
3. **Matching.** Each procedure has a length, so the engine looks for a gap in a clinician's session that is long
   enough and fits the patient's availability. It holds the time and texts the patient. YES books it. NO offers the
   next best slot, up to 3 times, then the patient is flagged for a call. No reply releases the hold.
4. **Standby.** A cancellation releases the chair to patients who opted in to short notice. If all 3 decline, Schedule
   flags the chair and suggests patients to text.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Unix: source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..
python run.py
```

| Page | URL |
|---|---|
| Console | http://localhost:8000 |
| Online sign-up | http://localhost:8000/join |
| Patient phone | http://localhost:8000/phone |
| API docs | http://localhost:8000/docs |

Set `ANTHROPIC_API_KEY` for live triage. Without it, triage falls back to keyword rules.

State is saved to `backend/state.json`. Use Tools > Reset demo data in the console to return to the seed data.

Run the tests with `python -m unittest discover backend`. They use a temporary snapshot, so your state is safe.

## Demo

1. **Call.** Tools > Simulate a call. The patient phone on the right shows the appointment text. Tap Yes.
2. **Why.** Waiting list > open the patient to see why the engine chose that clinician and slot.
3. **Batch.** Waiting list > Match waiting list texts everyone waiting. Step through days in Schedule to see the holds.
   Click a free gap in the calendar to see which waiting patients fit it.
4. **Online.** Tools > Online sign-up QR code. Same questions, same outcome. Tick short notice and earlier to be
   offered released chairs.
5. **Cancel.** Select an appointment in Schedule and cancel it, or tap Cancel appointment on the phone. Standby offers
   go out. Tap No on all three phones to see the chair flagged, then Fill this chair.
6. **Roles.** Switch View as to Clinical to see the clinical panel.

## Layout

```
backend/
  models.py       Data models
  pipeline.py     Intake, matching engine, patient replies, offer expiry
  intake_parsing.py  Reads name and availability from call transcripts
  state.py        In-memory state, standby offers, JSON snapshot
  matching.py     Clinician ranking and logbook scoring
  triage.py       Red-flag rules and structured triage
  tools_api.py    Voice agent tools
  patient_api.py  Online sign-up and the text thread
  console_api.py  Console endpoints
  main.py         FastAPI app, serves the built frontend
frontend/src/
  pages/          Console, join
  components/     Views, dialogs, phone simulator
api/              Express service for the voice side (skeleton)
agent.md          Voice agent script
run.py            Entry point
```

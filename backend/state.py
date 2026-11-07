"""In-memory thread-safe state manager with JSON snapshot persistence.
"""

from __future__ import annotations
import json
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple

from models import (
    ClinicSession, appointment_id, case_minutes, slot_minutes, slot_when, to_clock, to_minutes,
)
from models import (
    Patient, Availability, Case, Clinician, Slot, Booking, Offer,
    PatientMessage, Event, NeedsAttentionItem, CallRecord, utc_now_iso, make_id
)
from seed import generate_seed_data, BASE_DATE_STR
from matching import (
    check_competency, patient_available_for_slot, calculate_clinician_load, OFFER_TIMEOUTS_MINUTES
)

SNAPSHOT_FILE = os.path.join(os.path.dirname(__file__), "state.json")


class StateManager:
    def __init__(self):
        self._lock = threading.RLock()
        self.ref_date_str = BASE_DATE_STR

        # Core collections
        self.patients: Dict[str, Patient] = {}
        self.cases: Dict[str, Case] = {}
        self.clinicians: Dict[str, Clinician] = {}
        self.sessions: Dict[str, ClinicSession] = {}
        self.slots: Dict[str, Slot] = {}
        self.bookings: Dict[str, Booking] = {}
        self.offers: Dict[str, Offer] = {}
        self.messages: Dict[str, PatientMessage] = {}
        self.events: List[Event] = []
        self.needs_attention: Dict[str, NeedsAttentionItem] = {}
        self.calls: Dict[str, CallRecord] = {}

        # Active cascades: slot_id -> dict
        # { "slot_id": "...", "started_at": "...", "mode": "parallel"|"sequential",
        #   "offers": ["off-1", "off-2"], "status": "active"|"filled"|"exhausted",
        #   "winner_patient_id": None, "reason": "..." }
        self.active_cascades: Dict[str, Dict[str, Any]] = {}

        # Load existing snapshot or initialize seed
        if os.path.exists(SNAPSHOT_FILE):
            try:
                self.load_snapshot()
            except Exception as e:
                print(f"[State] Warning: Failed to load snapshot: {e}. Falling back to seed data.")
                self.reset_demo(save=False)
        else:
            self.reset_demo(save=True)

    def reset_demo(self, save: bool = True):
        """Reload pristine synthetic seed data."""
        with self._lock:
            pats, cases, clns, slots, bkgs, offs, msgs, evts, atts, calls, sessions = generate_seed_data()
            self.patients = {p.id: p for p in pats}
            self.cases = {c.id: c for c in cases}
            self.clinicians = {c.id: c for c in clns}
            self.sessions = {s.id: s for s in sessions}
            self.slots = {s.id: s for s in slots}
            self.bookings = {b.id: b for b in bkgs}
            self.offers = {o.id: o for o in offs}
            self.messages = {m.id: m for m in msgs}
            self.events = list(evts)
            self.needs_attention = {a.id: a for a in atts}
            self.calls = {c.id: c for c in calls}
            self.active_cascades = {}

            self._log_event_locked(
                actor="System",
                evt_type="demo_reset",
                entity="system",
                payload={},
                reason="Demo data reset."
            )

        if save:
            self.save_snapshot()

    def _log_event_locked(self, actor: str, evt_type: str, entity: str, payload: Dict[str, Any], reason: str) -> Event:
        evt = Event(
            actor=actor,
            type=evt_type,
            entity=entity,
            payload=payload,
            reason=reason,
        )
        self.events.append(evt)
        return evt

    def log_event(self, actor: str, evt_type: str, entity: str, payload: Dict[str, Any], reason: str) -> Event:
        with self._lock:
            evt = self._log_event_locked(actor, evt_type, entity, payload, reason)
        self.save_snapshot()
        return evt

    def send_message_locked(self, patient_id: str, msg_type: str, title: str, body: str, payload: Optional[Dict[str, Any]] = None, direction: str = "out") -> PatientMessage:
        msg = PatientMessage(
            patient_id=patient_id,
            type=msg_type,
            title=title,
            body=body,
            payload=payload,
            direction=direction,
        )
        self.messages[msg.id] = msg
        return msg

    # ==========================
    # CHAIR TIME
    # ==========================
    def occupies(self, slot: Slot) -> bool:
        """A slot blocks time while booked, held, or released and not yet refilled."""
        booking = self.bookings.get(slot.booking_id) if slot.booking_id else None
        if booking and booking.state in ("held", "confirmed", "locked", "attended"):
            return True
        return slot.id in self.active_cascades

    def session_slots(self, session: ClinicSession) -> List[Slot]:
        first, last = to_minutes(session.start), to_minutes(session.end)
        return sorted(
            (s for s in self.slots.values()
             if s.clinician_id == session.clinician_id and s.date == session.date
             and first <= to_minutes(s.start) < last and self.occupies(s)),
            key=lambda s: to_minutes(s.start),
        )

    def free_gaps(self, session: ClinicSession) -> List[Tuple[int, int]]:
        """Unbooked stretches of a session, as (start, end) in minutes."""
        gaps = []
        cursor = to_minutes(session.start)
        for slot in self.session_slots(session):
            if to_minutes(slot.start) > cursor:
                gaps.append((cursor, to_minutes(slot.start)))
            cursor = max(cursor, to_minutes(slot.end))
        if cursor < to_minutes(session.end):
            gaps.append((cursor, to_minutes(session.end)))
        return gaps

    def open_slots(self, minutes: int) -> List[Slot]:
        """Every place an appointment of this length could go. Nothing here is stored yet."""
        found: List[Slot] = []
        for session in self.sessions.values():
            for start, end in self.free_gaps(session):
                if end - start >= minutes:
                    clock = to_clock(start)
                    found.append(Slot(
                        id=appointment_id(session.date, clock, session.clinician_id),
                        clinician_id=session.clinician_id, bay=session.bay, date=session.date,
                        session=session.session, start=clock, end=to_clock(start + minutes),
                    ))
        for slot_id, record in self.active_cascades.items():
            slot = self.slots.get(slot_id)
            if slot and not slot.booking_id and record.get("status") in ("exhausted", "no_candidate") and slot_minutes(slot) >= minutes:
                found.append(slot)
        return found

    def peek_slot(self, slot_id: str, minutes: int) -> Optional[Slot]:
        """The slot this id refers to if an appointment of this length still fits there."""
        existing = self.slots.get(slot_id)
        if existing:
            booking = self.bookings.get(existing.booking_id) if existing.booking_id else None
            taken = booking and booking.state in ("held", "confirmed", "locked", "attended")
            return None if taken or slot_minutes(existing) < minutes else existing

        parsed = re.fullmatch(r"slot-(\d{4}-\d{2}-\d{2})-(\d{2})(\d{2})-(.+)", slot_id)
        if not parsed:
            return None
        date, hours, mins, clinician_id = parsed.groups()
        start = int(hours) * 60 + int(mins)
        for session in self.sessions.values():
            if session.date != date or session.clinician_id != clinician_id:
                continue
            if any(gap_start <= start and start + minutes <= gap_end for gap_start, gap_end in self.free_gaps(session)):
                return Slot(
                    id=slot_id, clinician_id=clinician_id, bay=session.bay, date=date, session=session.session,
                    start=to_clock(start), end=to_clock(start + minutes),
                )
        return None

    def resolve_slot(self, slot_id: str, minutes: int) -> Optional[Slot]:
        slot = self.peek_slot(slot_id, minutes)
        if slot:
            self.slots[slot.id] = slot
        return slot

    def load_of(self, clinician: Clinician) -> float:
        return calculate_clinician_load(
            clinician, list(self.slots.values()), list(self.bookings.values()),
            self.ref_date_str, list(self.sessions.values()),
        )

    def free_slot(self, slot: Slot) -> None:
        """Hand the time back. Released chairs stay on the book until they are dealt with."""
        slot.booking_id = None
        if slot.id not in self.active_cascades:
            self.slots.pop(slot.id, None)

    # ==========================
    # RELEASED SLOTS AND OFFERS
    # ==========================
    def trigger_cascade_for_slot(self, slot_id: str, cancelled_booking_id: Optional[str], reason: str, cancelled_by: str = "Receptionist") -> Dict[str, Any]:
        """Trigger cascade for a released slot.
        - Standby pool first (short_notice_ok)
        - Same day slots: top 3 in parallel, first confirm wins
        - Further out: sequential
        - Caps: max 3 offers per slot, then escalate
        """
        with self._lock:
            slot = self.slots.get(slot_id)
            if not slot:
                return {"status": "error", "message": f"Slot {slot_id} not found"}

            clinician = self.clinicians.get(slot.clinician_id)
            if not clinician:
                return {"status": "error", "message": "Clinician not found"}

            # Unlink cancelled booking if present
            if cancelled_booking_id and cancelled_booking_id in self.bookings:
                bkg = self.bookings[cancelled_booking_id]
                was_held = bkg.state == "held"
                bkg.state = "cancelled"
                slot.booking_id = None
                self.active_cascades.pop(slot_id, None)
                for pending in self.offers.values():
                    if pending.booking_id == bkg.id and pending.response == "pending":
                        pending.response = "expired"
                patient = self.patients.get(bkg.patient_id)
                case = self.cases.get(bkg.case_id)
                if patient:
                    patient.status = "waitlist" if was_held else "cancelled"
                if case and not was_held:
                    case.status = "cancelled"
                if patient:
                    self.send_message_locked(
                        patient_id=patient.id,
                        msg_type="cancelled",
                        title="Appointment cancelled",
                        body=f"Your appointment on {slot_when(slot)} has been cancelled. Call us if you need to rebook.",
                    )
                self._log_event_locked(
                    actor=cancelled_by,
                    evt_type="booking_cancelled",
                    entity="booking",
                    payload={"booking_id": bkg.id, "slot_id": slot.id, "patient_id": bkg.patient_id},
                    reason=reason or "Booking cancelled",
                )

            # Find candidates:
            # Standby patients (short_notice_ok) who are active or waitlisted/standby
            # Not already booked in a confirmed slot (unless wants_earlier)
            # Not already offered this slot
            previous_ids = (self.active_cascades.get(slot_id) or {}).get("offers", [])
            existing_offers_for_slot = [self.offers[i] for i in previous_ids if i in self.offers]
            patients_offered_this_slot = {o.patient_id for o in existing_offers_for_slot}

            if len(existing_offers_for_slot) >= 3:
                declined = sum(1 for o in existing_offers_for_slot if o.response == "declined")
                total = len(existing_offers_for_slot)
                when = f"{slot.bay}, {slot.date} {slot.start}"
                if declined == total:
                    outcome = f"All {total} standby patients declined {when} with {clinician.name}."
                else:
                    outcome = f"None of the {total} standby patients took {when} with {clinician.name}."
                # Max 3 offers reached -> Escalate to receptionist
                att_id = make_id("att")
                att = NeedsAttentionItem(
                    id=att_id,
                    slot_id=slot_id,
                    reason="offers_exhausted",
                    summary=outcome,
                    suggested_action="Open the chair in Schedule and choose a suggested patient.",
                )
                self.needs_attention[att.id] = att
                self.active_cascades[slot_id] = {
                    "slot_id": slot_id,
                    "started_at": utc_now_iso(),
                    "mode": "exhausted",
                    "offers": [o.id for o in existing_offers_for_slot],
                    "status": "exhausted",
                    "reason": "Offer limit reached",
                }
                self._log_event_locked(
                    actor="System",
                    evt_type="offers_exhausted",
                    entity="slot",
                    payload={"slot_id": slot_id},
                    reason="Offer limit of 3 reached. Added to the worklist.",
                )
                return {"status": "exhausted", "message": "Offer limit reached, added to the worklist"}

            # Filter eligible candidates
            candidates: List[Tuple[Patient, Case, int]] = []
            for pat in self.patients.values():
                if not pat.short_notice_ok:
                    continue
                if any(o.patient_id == pat.id and o.response == "pending" for o in self.offers.values()):
                    continue
                # Someone already booked later can move up if they asked to.
                current = [b for b in self.bookings.values() if b.patient_id == pat.id and b.state in ("confirmed", "locked")]
                moving_up = (
                    pat.status == "scheduled" and pat.wants_earlier and bool(current)
                    and all((self.slots[b.slot_id].date, self.slots[b.slot_id].start) > (slot.date, slot.start) for b in current)
                )
                if pat.status not in ("standby", "waitlist") and not moving_up:
                    continue
                if pat.id in patients_offered_this_slot:
                    continue
                if not patient_available_for_slot(pat, slot):
                    continue

                # Find patient's primary open case
                open_stages = ("accepted", "scheduled") if moving_up else ("accepted",)
                patient_cases = [c for c in self.cases.values() if c.patient_id == pat.id and c.status in open_stages]
                if not patient_cases:
                    continue
                case = patient_cases[0]

                if clinician.tier < case.required_tier or not check_competency(clinician, case):
                    continue
                if case_minutes(case.likely_procedures) > slot_minutes(slot):
                    continue

                # Teaching gap bonus
                gap = sum(
                    max(0, clinician.logbook_targets.get(p, 0) - clinician.logbook_done.get(p, 0))
                    for p in case.likely_procedures
                )
                candidates.append((pat, case, gap))

            if not candidates:
                # No backfill candidate
                att = NeedsAttentionItem(
                    slot_id=slot_id,
                    reason="no_backfill_candidate",
                    summary=f"No standby patient matches the released chair in {slot.bay} ({slot.date} {slot.session}).",
                    suggested_action="Check the waiting list or keep the chair for walk-ins.",
                )
                self.needs_attention[att.id] = att
                self.active_cascades[slot_id] = {
                    "slot_id": slot_id,
                    "started_at": utc_now_iso(),
                    "mode": "none",
                    "offers": [],
                    "status": "no_candidate",
                    "reason": "No standby match",
                }
                return {"status": "no_candidates", "message": "No eligible standby candidates found"}

            # Standby pool before the wider waiting list, then:
            # 1. Higher logbook gap (student teaching value)
            # 2. Patient waiting days
            # Demo only: people who scanned the QR code go first so offers reach their phones.
            candidates.sort(key=lambda x: (
                not x[0].joined_via_qr,
                x[0].status == "scheduled",
                x[0].status != "standby",
                -x[2],
                x[0].created_at,
            ))

            is_same_day = (slot.date == self.ref_date_str)
            target_candidates = candidates[:3] if is_same_day else candidates[:1]
            mode = "parallel" if is_same_day and len(target_candidates) > 1 else "single"

            # Create offers
            created_offers = []
            now_dt = datetime.now(timezone.utc)
            # Demo timeout: 15 minutes for immediate demo visibility, or 30 mins
            expires_at = (now_dt + timedelta(minutes=15)).isoformat()

            for pat, case, gap in target_candidates:
                off = Offer(
                    slot_id=slot_id,
                    patient_id=pat.id,
                    case_id=case.id,
                    mode=mode,
                    sent_at=utc_now_iso(),
                    expires_at=expires_at,
                    spoken_label=f"{slot.date} {slot.session} ({slot.start}-{slot.end}) in {slot.bay}",
                )
                self.offers[off.id] = off
                created_offers.append(off)

                # Send in-app message to patient
                if mode == "parallel":
                    title = "Appointment available today"
                    body = (
                        f"A short-notice appointment has opened today at {slot.start} with {clinician.name} ({clinician.tier_name}). "
                        f"We have offered it to a few patients and the first to reply YES gets it. Reply NO if you can't make it."
                    )
                else:
                    title = "Appointment available"
                    body = (
                        f"A short-notice appointment has opened: {slot_when(slot)} with {clinician.name}. Reply YES to take it or NO."
                    )

                self.send_message_locked(
                    patient_id=pat.id,
                    msg_type="offer_parallel" if mode == "parallel" else "offer_single",
                    title=title,
                    body=body,
                    payload={
                        "offer_id": off.id,
                        "slot_id": slot.id,
                        "slot_date": slot.date,
                        "slot_session": slot.session,
                        "slot_time": f"{slot.start} - {slot.end}",
                        "bay": slot.bay,
                        "clinician_name": clinician.name,
                        "clinician_tier": clinician.tier_name,
                        "expires_at": expires_at,
                        "mode": mode,
                    }
                )

            self.active_cascades[slot_id] = {
                "slot_id": slot_id,
                "started_at": utc_now_iso(),
                "mode": mode,
                "offers": previous_ids + [o.id for o in created_offers],
                "status": "active",
                "winner_patient_id": None,
                "reason": f"Offered to {len(created_offers)} standby patient(s).",
            }

            self._log_event_locked(
                actor="System",
                evt_type="offers_sent",
                entity="slot",
                payload={"slot_id": slot_id, "mode": mode, "patient_count": len(created_offers)},
                reason=f"Chair released. Offered to {', '.join(p[0].name for p in target_candidates)}."
            )

        self.save_snapshot()
        return {
            "status": "dispatched",
            "mode": mode,
            "offers": [o.id for o in created_offers],
            "candidate_names": [p[0].name for p in target_candidates]
        }

    def claim_offer(self, offer_id: str, patient_id: str) -> Dict[str, Any]:
        """Patient claims / accepts an offer (First-confirm-wins for parallel offers)."""
        with self._lock:
            offer = self.offers.get(offer_id)
            if not offer:
                return {"status": "error", "message": "Offer not found"}

            if offer.patient_id != patient_id:
                return {"status": "error", "message": "Offer does not belong to this patient"}

            if offer.response != "pending":
                return {"status": "error", "message": f"Offer is already {offer.response}"}

            slot = self.slots.get(offer.slot_id)
            if not slot:
                return {"status": "error", "message": "Associated slot not found"}

            # Check if slot was already taken by someone else (First-confirm-wins!)
            if slot.booking_id:
                existing_bkg = self.bookings.get(slot.booking_id)
                if existing_bkg and existing_bkg.patient_id != patient_id and existing_bkg.state in ("held", "confirmed", "locked", "attended"):
                    offer.response = "filled_by_other"
                    self.send_message_locked(
                        patient_id=patient_id,
                        msg_type="already_filled",
                        title="Appointment taken",
                        body="Another patient accepted this appointment first. You keep your place on the waiting list.",
                        payload={"slot_id": slot.id}
                    )
                    return {
                        "status": "already_filled",
                        "message": "Another patient accepted this appointment first. You keep your place on the waiting list."
                    }

            # Moving up frees the later appointment. It does not start another round of offers.
            for earlier in self.bookings.values():
                if earlier.patient_id == patient_id and earlier.state in ("confirmed", "locked"):
                    earlier.state = "cancelled"
                    old_slot = self.slots.get(earlier.slot_id)
                    if old_slot and old_slot.booking_id == earlier.id:
                        self.free_slot(old_slot)

            # WINNER! Claim the slot
            offer.response = "accepted"
            patient = self.patients.get(patient_id)
            case = self.cases.get(offer.case_id)
            clinician = self.clinicians.get(slot.clinician_id)

            bkg_id = make_id("bkg")
            booking = Booking(
                id=bkg_id,
                slot_id=slot.id,
                case_id=offer.case_id,
                patient_id=patient_id,
                state="confirmed",
                reason=f"{patient.name if patient else 'Patient'} accepted a standby offer.",
                created_by="patient_confirmation",
                created_at=utc_now_iso(),
            )
            self.bookings[bkg_id] = booking
            slot.booking_id = bkg_id
            if case:
                slot.end = to_clock(to_minutes(slot.start) + case_minutes(case.likely_procedures))

            if patient:
                patient.status = "scheduled"
            if case:
                case.status = "scheduled"

            # Update active cascade record
            if slot.id in self.active_cascades:
                cascade = self.active_cascades[slot.id]
                cascade["status"] = "filled"
                cascade["winner_patient_id"] = patient_id

            # Invalidate sibling parallel offers for other patients
            sibling_offers = [o for o in self.offers.values() if o.slot_id == slot.id and o.id != offer.id and o.response == "pending"]
            for sib in sibling_offers:
                sib.response = "filled_by_other"
                sib_pat = self.patients.get(sib.patient_id)
                if sib_pat and sib_pat.status == "offered":
                    sib_pat.status = "standby"
                self.send_message_locked(
                    patient_id=sib.patient_id,
                    msg_type="already_filled",
                    title="Appointment taken",
                    body="Another patient accepted this appointment first. You keep your place on the waiting list.",
                    payload={"slot_id": slot.id}
                )

            # Send confirmation receipt to the winner
            self.send_message_locked(
                patient_id=patient_id,
                msg_type="confirmed",
                title="Appointment confirmed",
                body=(
                    f"Booked: {slot_when(slot)} with "
                    f"{clinician.name if clinician else 'the clinical team'}, {slot.bay}. Please arrive 10 minutes early. Reply CANCEL if you can't make it."
                ),
                payload={
                    "booking_id": booking.id,
                    "slot_id": slot.id,
                    "date": slot.date,
                    "session": slot.session,
                    "time": f"{slot.start} - {slot.end}",
                    "bay": slot.bay,
                    "clinician_name": clinician.name if clinician else "Staff",
                }
            )

            self._log_event_locked(
                actor=patient.name if patient else "Patient",
                evt_type="parallel_offer_claimed" if offer.mode == "parallel" else "booking_confirmed",
                entity="booking",
                payload={"booking_id": booking.id, "slot_id": slot.id, "patient_id": patient_id},
                reason=f"{patient.name if patient else patient_id} accepted the offer. Chair refilled."
            )

        self.save_snapshot()
        return {
            "status": "confirmed",
            "booking_id": booking.id,
            "slot_id": slot.id,
            "patient_name": patient.name if patient else "Patient"
        }

    def decline_offer(self, offer_id: str, patient_id: str) -> Dict[str, Any]:
        """Patient declines an offer."""
        with self._lock:
            offer = self.offers.get(offer_id)
            if not offer or offer.patient_id != patient_id:
                return {"status": "error", "message": "Offer not found or unauthorized"}

            offer.response = "declined"
            patient = self.patients.get(patient_id)
            if patient and patient.status == "offered":
                patient.status = "standby"

            self.send_message_locked(
                patient_id=patient_id,
                msg_type="cancelled",
                title="Offer declined",
                body="Thanks for letting us know. You stay on the standby list.",
            )

            self._log_event_locked(
                actor=patient.name if patient else "Patient",
                evt_type="offer_declined",
                entity="offer",
                payload={"offer_id": offer.id, "slot_id": offer.slot_id, "patient_id": patient_id},
                reason="Patient declined the offer."
            )

        self.save_snapshot()
        return {"status": "declined"}

    # ==========================
    # SNAPSHOT PERSISTENCE
    # ==========================
    def save_snapshot(self):
        """Write atomic JSON snapshot to disk (temp file, then rename)."""
        with self._lock:
            self._write_snapshot()

    def _write_snapshot(self):
        data = {
            "ref_date_str": self.ref_date_str,
            "patients": {k: v.model_dump() for k, v in self.patients.items()},
            "cases": {k: v.model_dump() for k, v in self.cases.items()},
            "clinicians": {k: v.model_dump() for k, v in self.clinicians.items()},
            "sessions": {k: v.model_dump() for k, v in self.sessions.items()},
            "slots": {k: v.model_dump() for k, v in self.slots.items()},
            "bookings": {k: v.model_dump() for k, v in self.bookings.items()},
            "offers": {k: v.model_dump() for k, v in self.offers.items()},
            "messages": {k: v.model_dump() for k, v in self.messages.items()},
            "events": [e.model_dump() for e in self.events],
            "needs_attention": {k: v.model_dump() for k, v in self.needs_attention.items()},
            "calls": {k: v.model_dump() for k, v in self.calls.items()},
            "active_cascades": self.active_cascades,
        }

        tmp_dir = os.path.dirname(SNAPSHOT_FILE)
        fd, tmp_path = tempfile.mkstemp(dir=tmp_dir, prefix="state_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            shutil.move(tmp_path, SNAPSHOT_FILE)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def load_snapshot(self):
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.ref_date_str = data.get("ref_date_str", BASE_DATE_STR)
        self.patients = {k: Patient(**v) for k, v in data.get("patients", {}).items()}
        self.cases = {k: Case(**v) for k, v in data.get("cases", {}).items()}
        self.clinicians = {k: Clinician(**v) for k, v in data.get("clinicians", {}).items()}
        self.sessions = {k: ClinicSession(**v) for k, v in data.get("sessions", {}).items()}
        self.slots = {k: Slot(**v) for k, v in data.get("slots", {}).items()}
        self.bookings = {k: Booking(**v) for k, v in data.get("bookings", {}).items()}
        self.offers = {k: Offer(**v) for k, v in data.get("offers", {}).items()}
        self.messages = {k: PatientMessage(**v) for k, v in data.get("messages", {}).items()}
        self.events = [Event(**e) for e in data.get("events", [])]
        self.needs_attention = {k: NeedsAttentionItem(**v) for k, v in data.get("needs_attention", {}).items()}
        self.calls = {k: CallRecord(**v) for k, v in data.get("calls", {}).items()}
        self.active_cascades = data.get("active_cascades", {})


# Global singleton
STATE = StateManager()

"""Intake, matching and patient replies.

Phone calls and the online form both end in process_intake, so they ask for the
same things and lead to the same outcomes. The matching engine then proposes one
appointment by text. Standby is separate: it only fills chairs that were released.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from intake_parsing import full_week, read_history
from matching import (
    OFFER_TIMEOUTS_MINUTES, calculate_waitlist_priority, check_competency,
    patient_available_for_slot, rank_eligible_clinicians,
)
from models import (
    Booking, Case, MedicalHistory, NeedsAttentionItem, Offer, Patient, Slot, TIER_NAMES, case_minutes, slot_minutes,
    slot_when,
    to_clock, to_minutes, utc_now_iso,
)
from state import STATE
from triage import URGENCY_ORDER as RATINGS, TriageResult, get_anthropic_client, triage

ACTIVE_BOOKING = ("held", "confirmed", "locked")
OPEN_CASE = ("intake_done", "awaiting_tutor", "accepted", "scheduled")
WINDOW_DAYS = {"urgent": 2, "soon": 14, "routine": 21}
MAX_PROPOSALS = 3
URGENCY_ORDER = {"urgent": 0, "soon": 1, "routine": 2}
MATCHABLE_PATIENTS = ("waitlist",)
FLAG_ACTIONS = {
    "symptoms_unclear": "Accept to match it as it stands, or deny and tell the patient.",
    "too_severe": "Check a senior clinician can see them, then accept or deny.",
}


@dataclass
class IntakeData:
    channel: str  # "phone" or "online"
    name: str
    phone: str
    problem: str
    transcript: str = ""
    availability: Dict[str, Dict[str, bool]] = field(default_factory=full_week)
    short_notice_ok: bool = False
    wants_earlier: bool = False
    date_of_birth: Optional[str] = None
    medical_history: Optional[MedicalHistory] = None  # Given directly. Otherwise read from the transcript.
    agent_urgency: Optional[str] = None


# --- Matching ---------------------------------------------------------------

def _day_part(slot: Slot) -> str:
    day = datetime.strptime(slot.date, "%Y-%m-%d").strftime("%A")
    return f"{day} {'mornings' if slot.session == 'AM' else 'afternoons'}"


def _active_offer(patient_id: str) -> Optional[Offer]:
    pending = [o for o in STATE.offers.values() if o.patient_id == patient_id and o.response == "pending"]
    return max(pending, key=lambda o: o.sent_at) if pending else None


def _active_booking(patient_id: str) -> Optional[Booking]:
    active = [b for b in STATE.bookings.values() if b.patient_id == patient_id and b.state in ACTIVE_BOOKING]
    return min(active, key=lambda b: (STATE.slots[b.slot_id].date, STATE.slots[b.slot_id].start)) if active else None


def _released_now() -> set:
    return {slot_id for slot_id, record in STATE.active_cascades.items() if record.get("status") == "active"}


def rank_clinicians(case: Case, window: int = 14) -> List[Dict[str, Any]]:
    return rank_eligible_clinicians(
        case, list(STATE.clinicians.values()), STATE.open_slots(case_minutes(case.likely_procedures)),
        STATE.load_of, STATE.ref_date_str, urgency_days_window=window,
    )


def find_match(case: Case, patient: Patient) -> Optional[Dict[str, Any]]:
    """Choose a clinician and slot. Strict rule order lives in rank_eligible_clinicians."""
    window = WINDOW_DAYS.get(case.urgency, 21)
    minutes = case_minutes(case.likely_procedures)
    ranked = rank_clinicians(case, window)
    first_day = datetime.strptime(STATE.ref_date_str, "%Y-%m-%d")
    if case.urgency != "urgent":
        first_day += timedelta(days=1)
    earliest = first_day.strftime("%Y-%m-%d")
    # Same-day urgent cases still start after the first patients are in.
    blocked = set(case.declined_slot_ids) | _released_now()

    fitting: List[Tuple[Dict[str, Any], List[Slot]]] = []
    for entry in ranked:
        slots = sorted(
            (s for s in entry["free_slots_in_window"]
             if s.id not in blocked and s.date >= earliest and patient_available_for_slot(patient, s)),
            key=lambda s: (s.date, s.start),
        )
        if slots:
            fitting.append((entry, slots))
    if not fitting:
        return None

    entry, slots = fitting[0]
    clinician, slot = entry["clinician"], slots[0]
    same_grade = [e for e, _ in fitting if e["clinician"].tier == clinician.tier]
    load = round(entry["load"] * 100)

    if clinician.tier == case.required_tier:
        reasons = [f"{clinician.tier_name} is the lowest grade that can treat this case"]
    else:
        reasons = [f"No lower grade had a slot that fits, so moved up to {clinician.tier_name}"]
    reasons.append(f"Patient is free on {_day_part(slot)}")
    reasons.append(f"{minutes} minutes needed, and this gap has room")
    if entry["logbook_gap"] > 0:
        reasons.append(f"{clinician.name} still needs {entry['logbook_gap']} of these for their logbook")
    if len(same_grade) > 1:
        reasons.append(f"Lightest load of {len(same_grade)} eligible {clinician.tier_name} clinicians ({load}%)")
    else:
        reasons.append(f"Current load {load}%")

    return {
        "clinician": clinician,
        "slot": slot,
        "reasons": reasons,
        "alternatives": slots[1:],
    }


def propose(case: Case, patient: Patient, match: Dict[str, Any], actor: str = "Matching") -> Offer:
    """Hold the slot and ask the patient. They hold one proposal at a time."""
    length = case_minutes(case.likely_procedures)
    slot = STATE.resolve_slot(match["slot"].id, length)
    if slot is None:
        raise ValueError("That time has just been taken")
    clinician = match["clinician"]
    minutes = OFFER_TIMEOUTS_MINUTES.get(case.urgency, 1440)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()

    booking = Booking(
        slot_id=slot.id, case_id=case.id, patient_id=patient.id, state="held", held_until=expires,
        reason=match["reasons"][0], match_reasons=match["reasons"], created_by="engine",
    )
    STATE.bookings[booking.id] = booking
    slot.booking_id = booking.id

    offer = Offer(
        slot_id=slot.id, patient_id=patient.id, case_id=case.id, booking_id=booking.id,
        kind="match", mode="single", expires_at=expires,
    )
    STATE.offers[offer.id] = offer
    case.match_attempts += 1
    patient.status = "offered"

    reply_by = f"{minutes} minutes" if minutes < 60 else f"{minutes // 60} hours"
    STATE.send_message_locked(
        patient_id=patient.id, msg_type="offer_single", title="Appointment offered",
        body=(
            f"We have an appointment for you: {slot_when(slot)} with {clinician.name} "
            f"({clinician.tier_name}), about {length} minutes. Reply YES to book it or NO for another time. "
            f"We will hold it for {reply_by}."
        ),
        payload={"offer_id": offer.id},
    )
    STATE._log_event_locked(
        actor=actor, evt_type="match_offered", entity="booking",
        payload={"booking_id": booking.id, "slot_id": slot.id, "patient_id": patient.id},
        reason=f"{patient.name} offered {slot_when(slot)} with {clinician.name}. {match['reasons'][0]}.",
    )
    return offer


def match_case(case: Case, patient: Patient) -> Optional[Offer]:
    """Propose the best slot, or tell the patient they are waiting."""
    match = find_match(case, patient)
    if match:
        return propose(case, patient, match)

    if case.urgency == "urgent":
        _flag(patient, case, "no_match", f"No slot fits this urgent case within 48 hours.",
              "Call the patient and arrange a slot.")
    STATE.send_message_locked(
        patient_id=patient.id, msg_type="changed", title="On the waiting list",
        body="We have no appointment that fits your availability yet. You are on the waiting list and we will text you when one opens up.",
    )
    STATE._log_event_locked(
        actor="Matching", evt_type="match_none", entity="case", payload={"case_id": case.id},
        reason=f"No slot fits {patient.name}'s availability. Left on the waiting list.",
    )
    return None


def run_batch() -> Dict[str, int]:
    """Match everyone on the waiting list, most urgent first."""
    with STATE._lock:
        waiting = []
        for case in STATE.cases.values():
            patient = STATE.patients.get(case.patient_id)
            if (patient and case.status == "accepted" and patient.status in MATCHABLE_PATIENTS
                    and not _active_offer(patient.id) and not _active_booking(patient.id)):
                waiting.append((calculate_waitlist_priority(case, patient, STATE.ref_date_str), case, patient))
        waiting.sort(key=lambda row: row[0])

        offered = 0
        for _, case, patient in waiting:
            if match_case(case, patient):
                offered += 1
        STATE._log_event_locked(
            actor="Matching", evt_type="batch_run", entity="system", payload={"offered": offered},
            reason=f"Matched the waiting list: {offered} of {len(waiting)} patients offered an appointment.",
        )
    STATE.save_snapshot()
    return {"waiting": len(waiting), "offered": offered, "unmatched": len(waiting) - offered}


def candidates_for_slot(slot_id: str, room: int, limit: int = 5) -> List[Dict[str, Any]]:
    """Reverse match: the waiting patients who best suit one open chair or gap."""
    with STATE._lock:
        slot = STATE.peek_slot(slot_id, 15)
        if slot is None:
            return []
        room = max(room, slot_minutes(slot)) if slot_id in STATE.slots else room
        clinician = STATE.clinicians[slot.clinician_id]
        rows = []
        for case in STATE.cases.values():
            patient = STATE.patients.get(case.patient_id)
            if (not patient or case.status != "accepted" or patient.status not in ("waitlist", "standby")
                    or clinician.tier < case.required_tier or not check_competency(clinician, case)
                    or case_minutes(case.likely_procedures) > room
                    or slot.id in case.declined_slot_ids or not patient_available_for_slot(patient, slot)
                    or _active_offer(patient.id) or _active_booking(patient.id)):
                continue
            minutes = case_minutes(case.likely_procedures)
            days_waiting = -calculate_waitlist_priority(case, patient, STATE.ref_date_str)[1]
            # Urgent cases first, then the tightest fit: no more grade than the case needs,
            # the least chair time left over, then soonest need and longest wait.
            rank = (
                case.urgency != "urgent",
                clinician.tier - case.required_tier,
                room - minutes,
                URGENCY_ORDER.get(case.urgency, 3),
                -days_waiting,
            )
            rows.append((rank, case, patient, minutes, days_waiting))
        rows.sort(key=lambda row: row[0])
        return [
            {
                "case_id": case.id, "patient_id": patient.id, "patient_name": patient.name,
                "urgency": case.urgency, "summary": case.summary_plain, "minutes": minutes,
                "min_grade": TIER_NAMES.get(case.required_tier, ""), "days_waiting": days_waiting,
            }
            for _, case, patient, minutes, days_waiting in rows[:limit]
        ]


def offer_slot(case_id: str, slot_id: str) -> Offer:
    """Staff send a specific open chair to a specific patient."""
    with STATE._lock:
        case = STATE.cases[case_id]
        patient = STATE.patients[case.patient_id]
        slot = STATE.peek_slot(slot_id, case_minutes(case.likely_procedures))
        if slot is None:
            raise ValueError("That time has just been taken")
        clinician = STATE.clinicians[slot.clinician_id]
        if _active_offer(patient.id):
            raise ValueError(f"{patient.name} already has an offer waiting for a reply")
        record = STATE.active_cascades.get(slot.id)
        if record and record.get("status") == "active":
            raise ValueError("This chair is already out with standby patients")
        offer = propose(case, patient, {
            "slot": slot, "clinician": clinician,
            "reasons": ["Chosen by reception from the suggested patients"],
        }, actor="Receptionist")
    STATE.save_snapshot()
    return offer


# --- Flag helper ------------------------------------------------------------

def _flag(patient: Optional[Patient], case: Optional[Case], reason: str, summary: str, action: str) -> None:
    item = NeedsAttentionItem(
        patient_id=patient.id if patient else None, case_id=case.id if case else None,
        reason=reason, summary=summary, suggested_action=action,
    )
    STATE.needs_attention[item.id] = item


# --- Intake -----------------------------------------------------------------

def _find_patient(name: str, phone: str) -> Optional[Patient]:
    clean = phone.replace(" ", "").replace("-", "")
    for patient in STATE.patients.values():
        same_phone = patient.phone.replace(" ", "").replace("-", "") == clean
        if same_phone and patient.name.strip().lower() == name.strip().lower():
            return patient
    return None


def _open_case(patient_id: str) -> Optional[Case]:
    for case in STATE.cases.values():
        if case.patient_id == patient_id and case.status in OPEN_CASE:
            return case
    return None


def _stand_down(patient: Patient, keep: Case, reason: str) -> None:
    """Withdraw everything a patient has open, so a chair isn't held for someone who won't come."""
    for booking in [b for b in STATE.bookings.values() if b.patient_id == patient.id and b.state in ACTIVE_BOOKING]:
        STATE.trigger_cascade_for_slot(booking.slot_id, booking.id, reason, cancelled_by="Automated line")
    for offer in [o for o in STATE.offers.values() if o.patient_id == patient.id and o.response == "pending"]:
        offer.response = "expired"
        _follow_up_standby(offer.slot_id)
    for case in STATE.cases.values():
        if case.patient_id == patient.id and case.id != keep.id and case.status in OPEN_CASE:
            case.status = "cancelled"


def _update_open_case(data: IntakeData, patient: Patient, case: Case, result: TriageResult) -> Dict[str, Any]:
    """A patient we already have called again. Their details refresh, and getting worse reaches a person."""
    patient.date_of_birth = data.date_of_birth or patient.date_of_birth
    patient.availability.grid = data.availability
    patient.short_notice_ok = data.short_notice_ok
    patient.wants_earlier = data.wants_earlier
    case.medical_history = data.medical_history or case.medical_history

    assessment = result.assessment
    worse = assessment and RATINGS.index(assessment.urgency) < RATINGS.index(case.urgency)
    if worse:
        before, case.urgency = case.urgency, assessment.urgency
        case.summary_plain = assessment.summary_plain
        _flag(patient, case, "got_worse", f"Called back. Was {before}, now {case.urgency}. {case.summary_plain}",
              "Check whether they need to be seen sooner.")
        booked = _active_offer(patient.id) or _active_booking(patient.id)
        if case.status == "accepted" and not booked:
            match_case(case, patient)
    STATE.send_message_locked(
        patient_id=patient.id, msg_type="changed", title="Details updated",
        body=("Thanks for letting us know. We will check whether you need to be seen sooner." if worse else
              "We already have you on our list, so we have updated your availability."),
    )
    STATE._log_event_locked(
        actor="Automated line" if data.channel == "phone" else "Online form",
        evt_type="availability_updated", entity="patient", payload={"patient_id": patient.id},
        reason=f"{patient.name} called again and got worse." if worse else f"{patient.name} updated their availability.",
    )
    STATE.save_snapshot()
    return {"outcome": "updated", "patient_id": patient.id, "case_id": case.id, "token": patient.contact_token}


async def process_intake(data: IntakeData) -> Dict[str, Any]:
    """Shared by the phone webhook and the online form."""
    with STATE._lock:
        patient = _find_patient(data.name, data.phone)

    result = await triage(get_anthropic_client(), data.problem, data.transcript or data.problem, data.agent_urgency)
    assessment = result.assessment

    with STATE._lock:
        existing = _open_case(patient.id) if patient else None
        if patient and existing and result.next_step != "emergency":
            return _update_open_case(data, patient, existing, result)
        if not patient:
            patient = Patient(name=data.name, phone=data.phone, joined_via_qr=data.channel == "online")
            STATE.patients[patient.id] = patient
        patient.date_of_birth = data.date_of_birth or patient.date_of_birth
        patient.availability.grid = data.availability
        patient.availability.source = "call" if data.channel == "phone" else "patient_confirmed"
        patient.availability.confirmed_at = utc_now_iso()
        patient.short_notice_ok = data.short_notice_ok
        patient.wants_earlier = data.wants_earlier
        patient.status = "waitlist"

        complexity = assessment.complexity if assessment else (5 if result.next_step == "emergency" else 2)
        history = data.medical_history or (assessment.medical_history if assessment else read_history(data.transcript))
        case = Case(
            patient_id=patient.id,
            channel=data.channel,
            summary_plain=assessment.summary_plain if assessment else data.problem[:160],
            complaint_quote=data.problem,
            urgency=assessment.urgency if assessment else (
                "emergency" if result.next_step == "emergency" else data.agent_urgency or "routine"
            ),
            agent_urgency=data.agent_urgency,
            medical_history=history,
            complexity=complexity,
            required_tier=complexity,
            confidence=assessment.confidence if assessment else "low",
            possible_issues=assessment.possible_issues if assessment else [],
            not_ruled_out=assessment.not_ruled_out if assessment else [],
            likely_procedures=assessment.likely_procedures if assessment else [],
            status="intake_done",
        )
        STATE.cases[case.id] = case
        actor = "Automated line" if data.channel == "phone" else "Online form"
        STATE._log_event_locked(
            actor=actor, evt_type="intake_created", entity="case",
            payload={"patient_id": patient.id, "case_id": case.id},
            reason=f"{patient.name}: {result.reason}." + (f" {result.disagreement}" if result.disagreement else ""),
        )

        if result.next_step == "emergency":
            outcome = "emergency"
            _stand_down(patient, case, "Patient sent to emergency care")
            case.urgency = "emergency"
            case.status = "emergency_redirected"
            patient.status = "cancelled"
            _flag(patient, case, "red_flag", data.problem[:160], "Call the patient to check they went to A&E.")
            STATE.send_message_locked(
                patient_id=patient.id, msg_type="emergency", title="Get urgent care",
                body="What you told us needs urgent care today. Please go to A&E now, or call NHS 111 or 999. We cannot book this at the student clinic.",
            )
        elif result.next_step == "review":
            outcome = "review"
            case.status = "awaiting_tutor"
            summary = f"{case.summary_plain} {result.disagreement}" if result.disagreement else case.summary_plain
            _flag(patient, case, result.flag, summary, FLAG_ACTIONS[result.flag])
            STATE.send_message_locked(
                patient_id=patient.id, msg_type="received", title="Details received",
                body=f"Thanks {patient.name.split()[0]}. A clinician needs to check your details first. We will text you when they have.",
            )
        else:
            case.status = "accepted"
            STATE.send_message_locked(
                patient_id=patient.id, msg_type="received", title="Details received",
                body=f"Thanks {patient.name.split()[0]}, we have your details and availability.",
            )
            outcome = "offered" if match_case(case, patient) else "waiting"

        STATE.save_snapshot()
        return {"outcome": outcome, "patient_id": patient.id, "case_id": case.id, "token": patient.contact_token}


def case_approved(case: Case) -> None:
    """A tutor accepted the case, so it joins normal matching."""
    patient = STATE.patients.get(case.patient_id)
    if patient and patient.status == "waitlist" and not _active_offer(patient.id) and not _active_booking(patient.id):
        match_case(case, patient)


def case_denied(case: Case) -> None:
    """Staff turned the case down, so it leaves the waiting list and the patient is told."""
    patient = STATE.patients.get(case.patient_id)
    if patient:
        _stand_down(patient, case, "Case turned down by staff")
    case.status = "discharged"
    if patient:
        patient.status = "discharged"
        STATE.send_message_locked(
            patient_id=patient.id, msg_type="changed", title="We can't book this",
            body="We can't offer you an appointment at the student clinic for this. Please see your dentist, or call NHS 111 if you need help soon.",
        )


# --- Replies ----------------------------------------------------------------

def _release_hold(offer: Offer) -> None:
    booking = STATE.bookings.get(offer.booking_id) if offer.booking_id else None
    if booking and booking.state == "held":
        booking.state = "cancelled"
        slot = STATE.slots.get(booking.slot_id)
        if slot and slot.booking_id == booking.id:
            STATE.free_slot(slot)


def _accept_match(offer: Offer, patient: Patient) -> None:
    booking = STATE.bookings[offer.booking_id]
    slot = STATE.slots[offer.slot_id]
    clinician = STATE.clinicians[slot.clinician_id]
    case = STATE.cases[offer.case_id]
    offer.response = "accepted"
    booking.state = "confirmed"
    slot.end = to_clock(to_minutes(slot.start) + case_minutes(case.likely_procedures))
    booking.held_until = None
    patient.status = "scheduled"
    case.status = "scheduled"
    record = STATE.active_cascades.get(slot.id)
    if record:
        record["status"] = "filled"
        record["winner_patient_id"] = patient.id
    STATE.send_message_locked(
        patient_id=patient.id, msg_type="confirmed", title="Appointment booked",
        body=f"Booked: {slot_when(slot)} with {clinician.name}, {slot.bay}. Please arrive 10 minutes early. Reply CANCEL if you can't make it.",
    )
    STATE._log_event_locked(
        actor=patient.name, evt_type="match_accepted", entity="booking",
        payload={"booking_id": booking.id, "slot_id": slot.id},
        reason=f"{patient.name} accepted {slot.date} {slot.session} with {clinician.name}.",
    )


def _decline_match(offer: Offer, patient: Patient) -> None:
    case = STATE.cases[offer.case_id]
    offer.response = "declined"
    _release_hold(offer)
    case.declined_slot_ids.append(offer.slot_id)
    patient.status = "waitlist"
    STATE._log_event_locked(
        actor=patient.name, evt_type="match_declined", entity="offer",
        payload={"offer_id": offer.id, "slot_id": offer.slot_id},
        reason=f"{patient.name} declined the proposed appointment.",
    )
    if case.match_attempts >= MAX_PROPOSALS:
        _flag(patient, case, "match_declined", f"{patient.name} turned down {MAX_PROPOSALS} proposed appointments.",
              "Call the patient to find a time that works.")
        STATE.send_message_locked(
            patient_id=patient.id, msg_type="changed", title="We will call you",
            body="Thanks for letting us know. Someone from the clinic will call you to find a time that works.",
        )
    else:
        match_case(case, patient)


def _follow_up_standby(slot_id: str) -> None:
    """When nobody is left waiting to reply, try the next person or flag the chair."""
    slot = STATE.slots.get(slot_id)
    record = STATE.active_cascades.get(slot_id)
    if not slot or not record or record.get("status") != "active" or slot.booking_id:
        return
    offers = [STATE.offers[i] for i in record.get("offers", []) if i in STATE.offers]
    if any(o.response == "pending" for o in offers):
        return
    STATE.trigger_cascade_for_slot(slot_id, None, "Standby replies received")


def respond(patient: Patient, offer: Offer, accept: bool) -> Dict[str, Any]:
    with STATE._lock:
        if offer.response != "pending":
            return {"status": "closed"}
        if offer.kind == "match":
            if accept:
                _accept_match(offer, patient)
            else:
                _decline_match(offer, patient)
            result = {"status": "ok"}
        elif accept:
            result = STATE.claim_offer(offer.id, patient.id)
        else:
            result = STATE.decline_offer(offer.id, patient.id)
            _follow_up_standby(offer.slot_id)
    STATE.save_snapshot()
    return result


def handle_reply(patient: Patient, text: str) -> None:
    """Every patient reply arrives here, whatever screen sent it."""
    word = text.strip().upper()
    with STATE._lock:
        STATE.send_message_locked(
            patient_id=patient.id, msg_type="reply", title="Reply", body=text.strip(), direction="in",
        )
        offer = _active_offer(patient.id)
        booking = _active_booking(patient.id)
        if word in ("YES", "Y") and offer:
            respond(patient, offer, True)
        elif word in ("NO", "N") and offer:
            respond(patient, offer, False)
        elif word == "CANCEL" and booking and booking.state != "held":
            slot_id = booking.slot_id
            STATE.trigger_cascade_for_slot(slot_id, booking.id, "Patient cancelled by text", cancelled_by=patient.name)
        else:
            if offer:
                prompt = "Please reply YES to book this appointment or NO for another time."
            elif booking:
                prompt = "Reply CANCEL if you can't make your appointment."
            else:
                prompt = "Nothing needs a reply right now. We will text you when we have an appointment."
            STATE.send_message_locked(patient_id=patient.id, msg_type="changed", title="Reply", body=prompt)
    STATE.save_snapshot()


def expire_offers() -> None:
    """Close offers past their reply window. Runs on every poll, so it needs no scheduler."""
    now = datetime.now(timezone.utc)
    with STATE._lock:
        expired = [
            o for o in STATE.offers.values()
            if o.response == "pending" and datetime.fromisoformat(o.expires_at.replace("Z", "+00:00")) <= now
        ]
        for offer in expired:
            offer.response = "expired"
            patient = STATE.patients.get(offer.patient_id)
            if offer.kind == "match":
                _release_hold(offer)
                if patient:
                    patient.status = "waitlist"
                    STATE.send_message_locked(
                        patient_id=patient.id, msg_type="changed", title="Offer ended",
                        body="We did not hear back, so we released that appointment. You keep your place on the waiting list.",
                    )
            STATE._log_event_locked(
                actor="System", evt_type="offer_expired", entity="offer", payload={"offer_id": offer.id},
                reason=f"{patient.name if patient else 'Patient'} did not reply in time.",
            )
        for offer in expired:
            if offer.kind == "standby":
                _follow_up_standby(offer.slot_id)
    if expired:
        STATE.save_snapshot()

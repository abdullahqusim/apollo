"""Voice agent tool contract endpoints.
Used by ElevenLabs conversational agent and local voice front door.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state import STATE
from models import slot_when
from intake_parsing import parse_dob
from models import (
    MedicalHistory, Patient, Case, Slot, Booking, Offer, NeedsAttentionItem,
    CallRecord, utc_now_iso, make_id
)
from models import case_minutes
from pipeline import find_match
from triage import agent_urgency_from, triage, get_anthropic_client, has_red_flag

router = APIRouter(prefix="/api/tools", tags=["Voice Agent Tools"])


# Tool 1: lookup_patient
class LookupPatientRequest(BaseModel):
    phone: str
    name: Optional[str] = None
    dob: Optional[str] = None


@router.post("/lookup_patient")
def lookup_patient(req: LookupPatientRequest):
    # Normalize phone: remove spaces/hyphens
    clean_phone = req.phone.replace(" ", "").replace("-", "")
    with STATE._lock:
        found_pat = None
        for p in STATE.patients.values():
            if p.phone.replace(" ", "").replace("-", "") == clean_phone:
                found_pat = p
                break

        if not found_pat:
            return {"patient_id": None, "upcoming_bookings": []}

        # Find upcoming bookings
        upcoming = []
        for b in STATE.bookings.values():
            if b.patient_id == found_pat.id and b.state in ("held", "confirmed", "locked"):
                slot = STATE.slots.get(b.slot_id)
                cln = STATE.clinicians.get(slot.clinician_id) if slot else None
                upcoming.append({
                    "booking_id": b.id,
                    "slot_id": b.slot_id,
                    "date": slot.date if slot else "Unknown",
                    "session": slot.session if slot else "AM",
                    "start": slot.start if slot else "",
                    "end": slot.end if slot else "",
                    "bay": slot.bay if slot else "",
                    "clinician_name": cln.name if cln else "Clinical team",
                    "state": b.state,
                })

        return {
            "patient_id": found_pat.id,
            "patient_name": found_pat.name,
            "upcoming_bookings": upcoming
        }


# Tool 2: create_intake
class CreateIntakeRequest(BaseModel):
    name: str
    phone: str
    dob: Optional[str] = None
    availability_text: Optional[str] = None
    transcript_so_far: Optional[str] = None
    short_notice_ok: Optional[bool] = True


@router.post("/create_intake")
def create_intake(req: CreateIntakeRequest):
    with STATE._lock:
        # Check if existing patient
        clean_phone = req.phone.replace(" ", "").replace("-", "")
        patient = None
        for p in STATE.patients.values():
            if p.phone.replace(" ", "").replace("-", "") == clean_phone:
                patient = p
                break

        if not patient:
            patient = Patient(
                name=req.name,
                phone=req.phone,
                short_notice_ok=req.short_notice_ok if req.short_notice_ok is not None else True,
                status="waitlist"
            )
            STATE.patients[patient.id] = patient
        patient.date_of_birth = parse_dob(req.dob or "") or patient.date_of_birth

        # Create intake Case
        case = Case(
            patient_id=patient.id,
            summary_plain=req.availability_text or "Intake call in progress",
            complaint_quote=req.transcript_so_far or "Intake via automated voice line",
            urgency="routine",
            status="intake_done"
        )
        STATE.cases[case.id] = case

        STATE._log_event_locked(
            actor="Automated line",
            evt_type="intake_created",
            entity="case",
            payload={"patient_id": patient.id, "case_id": case.id},
            reason=f"New phone intake created for {patient.name} ({patient.phone})."
        )

    STATE.save_snapshot()
    return {"patient_id": patient.id, "case_id": case.id}


# Tool 3: submit_triage
class SubmitTriageRequest(BaseModel):
    case_id: str
    complaint_quote: str
    key_details: Optional[Dict[str, Any]] = None
    red_flags: Optional[List[str]] = None
    medical_history: Optional[MedicalHistory] = None
    agent_urgency: Optional[str] = None


@router.post("/submit_triage")
async def submit_triage(req: SubmitTriageRequest):
    # Run triage logic
    client = get_anthropic_client()
    agent_urgency = agent_urgency_from(req.agent_urgency)
    triage_res = await triage(client, req.complaint_quote, req.complaint_quote, agent_urgency)

    with STATE._lock:
        case = STATE.cases.get(req.case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        case.complaint_quote = req.complaint_quote
        case.agent_urgency = agent_urgency
        case.medical_history = req.medical_history or (
            triage_res.assessment.medical_history if triage_res.assessment else None
        )
        if req.key_details:
            case.key_details = req.key_details

        if triage_res.next_step == "emergency":
            case.urgency = "emergency"
            case.status = "emergency_redirected"
            case.summary_plain = "EMERGENCY: Patient redirected to NHS 111 / A&E."
            # Raise emergency Needs Attention item
            att = NeedsAttentionItem(
                patient_id=case.patient_id,
                case_id=case.id,
                reason="red_flag",
                summary=triage_res.reason,
                suggested_action="Call the patient to check they went to A&E or called NHS 111.",
            )
            STATE.needs_attention[att.id] = att
            STATE._log_event_locked(
                actor="Automated line",
                evt_type="emergency_redirected",
                entity="case",
                payload={"case_id": case.id, "reason": triage_res.reason},
                reason=f"Emergency: {triage_res.reason}. Patient told to attend A&E."
            )
            STATE.save_snapshot()
            return {
                "urgency": "emergency",
                "next_step": "emergency",
                "summary": "Red flag detected. Diverting to emergency script.",
            }

        # Normal or review triage
        if triage_res.assessment:
            case.urgency = triage_res.assessment.urgency
            case.complexity = triage_res.assessment.complexity
            case.confidence = triage_res.assessment.confidence
            case.summary_plain = triage_res.assessment.summary_plain
            case.possible_issues = triage_res.assessment.possible_issues
            case.not_ruled_out = triage_res.assessment.not_ruled_out
            case.likely_procedures = triage_res.assessment.likely_procedures
            case.required_tier = triage_res.assessment.complexity
        elif agent_urgency:
            case.urgency = agent_urgency

        if triage_res.next_step == "review":
            case.status = "awaiting_tutor"
            att = NeedsAttentionItem(
                patient_id=case.patient_id,
                case_id=case.id,
                reason="low_confidence" if case.confidence == "low" else "borderline_complexity",
                summary=case.summary_plain,
                suggested_action="Tutor to confirm urgency and grade.",
            )
            STATE.needs_attention[att.id] = att
        else:
            case.status = "accepted"
            if triage_res.disagreement:
                att = NeedsAttentionItem(
                    patient_id=case.patient_id,
                    case_id=case.id,
                    reason="urgency_disagreement",
                    summary=f"{triage_res.disagreement} Using {case.urgency}.",
                    suggested_action="Tutor to confirm the urgency.",
                )
                STATE.needs_attention[att.id] = att

        STATE._log_event_locked(
            actor="Automated line",
            evt_type="triage_completed",
            entity="case",
            payload={"case_id": case.id, "urgency": case.urgency, "complexity": case.complexity},
            reason=f"Triage complete: {case.urgency}, complexity {case.complexity} ({triage_res.reason})."
        )

    STATE.save_snapshot()
    return {
        "urgency": case.urgency,
        "next_step": triage_res.next_step,
        "summary": case.summary_plain,
        "complexity": case.complexity,
    }


# Tool 4: get_options
class GetOptionsRequest(BaseModel):
    case_id: Optional[str] = None
    booking_id: Optional[str] = None
    count: Optional[int] = 2  # <=2 by voice


@router.post("/get_options")
def get_options(req: GetOptionsRequest):
    with STATE._lock:
        case = None
        patient = None
        if req.case_id:
            case = STATE.cases.get(req.case_id)
            if case:
                patient = STATE.patients.get(case.patient_id)
        elif req.booking_id:
            bkg = STATE.bookings.get(req.booking_id)
            if bkg:
                case = STATE.cases.get(bkg.case_id)
                patient = STATE.patients.get(bkg.patient_id)

        if not case or not patient:
            raise HTTPException(status_code=404, detail="Case or patient not found")

        match = find_match(case, patient)
        slots_to_return = []
        if match:
            slots_to_return = [match["slot"], *match["alternatives"]][:max(1, req.count or 1)]

        # Format spoken labels
        options = []
        for s in slots_to_return:
            cln = STATE.clinicians.get(s.clinician_id)
            # Spoken label
            dt = s.date  # e.g. 2026-11-09
            spoken_label = f"{dt} {s.session} at {s.start} in {s.bay} with {cln.name if cln else 'the student clinic'}"
            options.append({
                "slot_id": s.id,
                "date": s.date,
                "session": s.session,
                "start": s.start,
                "bay": s.bay,
                "clinician_name": cln.name if cln else "Clinical team",
                "clinician_tier": cln.tier_name if cln else "Student",
                "spoken_label": spoken_label,
            })

        return {"options": options}


# Tool 5: book_slot
class BookSlotRequest(BaseModel):
    case_id: str
    slot_id: str


@router.post("/book_slot")
def book_slot(req: BookSlotRequest):
    with STATE._lock:
        case = STATE.cases.get(req.case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        patient = STATE.patients.get(case.patient_id)
        slot = STATE.resolve_slot(req.slot_id, case_minutes(case.likely_procedures))
        if not slot:
            raise HTTPException(status_code=409, detail="Slot is no longer available")

        cln = STATE.clinicians.get(slot.clinician_id)
        bkg_id = make_id("bkg")
        bkg = Booking(
            id=bkg_id,
            slot_id=slot.id,
            case_id=case.id,
            patient_id=patient.id if patient else "",
            state="confirmed",
            reason=f"Booked via automated voice line with {cln.name if cln else 'clinician'}.",
            created_by="Automated line",
            created_at=utc_now_iso(),
        )
        STATE.bookings[bkg_id] = bkg
        slot.booking_id = bkg_id

        if patient:
            patient.status = "scheduled"
            STATE.send_message_locked(
                patient_id=patient.id,
                msg_type="confirmed",
                title="Appointment confirmed",
                body=f"Your appointment is on {slot_when(slot)} with {cln.name if cln else 'the clinical team'}, {slot.bay}.",
            )
        case.status = "scheduled"

        STATE._log_event_locked(
            actor="Automated line",
            evt_type="booking_confirmed",
            entity="booking",
            payload={"booking_id": bkg_id, "slot_id": slot.id, "patient_id": patient.id if patient else ""},
            reason=f"Slot booked via phone call for {patient.name if patient else 'patient'}."
        )

    STATE.save_snapshot()
    return {"booking_id": bkg.id, "state": bkg.state}


# Tool 6: cancel_booking
class CancelBookingRequest(BaseModel):
    booking_id: str
    reason: Optional[str] = "Cancelled via automated voice line"


@router.post("/cancel_booking")
def cancel_booking(req: CancelBookingRequest):
    with STATE._lock:
        bkg = STATE.bookings.get(req.booking_id)
        if not bkg:
            raise HTTPException(status_code=404, detail="Booking not found")
        slot_id = bkg.slot_id

    result = STATE.trigger_cascade_for_slot(
        slot_id, req.booking_id, req.reason or "Cancelled by patient", cancelled_by="Automated line"
    )
    return {"ok": True, "result": result}


# Tool 7: reschedule_booking
class RescheduleBookingRequest(BaseModel):
    booking_id: str


@router.post("/reschedule_booking")
def reschedule_booking(req: RescheduleBookingRequest):
    return get_options(GetOptionsRequest(booking_id=req.booking_id, count=2))


# Tool 8: escalate
class EscalateRequest(BaseModel):
    patient_id: Optional[str] = None
    reason: str  # "asked_for_person" | "identity_unconfirmed" | "unclear" | "other"
    summary: str


@router.post("/escalate")
def escalate(req: EscalateRequest):
    with STATE._lock:
        att = NeedsAttentionItem(
            patient_id=req.patient_id,
            reason=req.reason if req.reason in [
                "asked_for_person", "identity_unconfirmed", "symptoms_unclear", "other"
            ] else "other",
            summary=req.summary,
            suggested_action="Call the patient back.",
        )
        STATE.needs_attention[att.id] = att

        STATE._log_event_locked(
            actor="Automated line",
            evt_type="call_escalated",
            entity="ticket",
            payload={"ticket_id": att.id, "patient_id": req.patient_id, "reason": req.reason},
            reason=f"Call escalated to receptionist: {req.summary} ({req.reason})"
        )

    STATE.save_snapshot()
    return {"ticket_id": att.id, "status": "escalated"}

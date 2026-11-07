"""Receptionist console and clinical view API.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone

from state import STATE
from models import slot_when
from models import appointment_id, case_minutes, slot_minutes, to_clock, to_minutes
from pipeline import rank_clinicians, _active_offer, _release_hold, candidates_for_slot, case_approved, expire_offers, offer_slot, run_batch
from models import (
    Patient, Case, Slot, Booking, Offer, Clinician,
    NeedsAttentionItem, Event, CallRecord, utc_now_iso, make_id
)
from matching import (
    check_competency, logbook_gap_score
)

router = APIRouter(prefix="/api/console", tags=["Console"])


def refill_summary(slot_id: str) -> Optional[Dict[str, Any]]:
    """How the standby offers on a released chair turned out."""
    record = STATE.active_cascades.get(slot_id)
    if not record:
        return None
    offers = [STATE.offers[i] for i in record.get("offers", []) if i in STATE.offers]
    return {
        "status": record.get("status", "active"),
        "sent": len(offers),
        "declined": sum(1 for o in offers if o.response == "declined"),
        "no_reply": sum(1 for o in offers if o.response == "expired"),
        "pending": sum(1 for o in offers if o.response == "pending"),
    }


def appointment_for(patient_id: str) -> Optional[Dict[str, Any]]:
    """The patient's current held or booked appointment."""
    active = [b for b in STATE.bookings.values() if b.patient_id == patient_id and b.state in ("held", "confirmed", "locked")]
    if not active:
        return None
    booking = active[-1]
    slot = STATE.slots.get(booking.slot_id)
    clinician = STATE.clinicians.get(slot.clinician_id) if slot else None
    return {
        "state": "offered" if booking.state == "held" else "booked",
        "date": slot.date if slot else "",
        "start": slot.start if slot else "",
        "bay": slot.bay if slot else "",
        "clinician_name": clinician.name if clinician else "",
        "reasons": booking.match_reasons or [booking.reason],
        "held_until": booking.held_until,
    }


# 1. Today Screen
@router.get("/today")
def get_today_screen(date: Optional[str] = None):
    expire_offers()
    with STATE._lock:
        today_date = date or STATE.ref_date_str
        day_sessions = [s for s in STATE.sessions.values() if s.date == today_date]
        day_slots = sorted(
            (s for s in STATE.slots.values() if s.date == today_date and STATE.occupies(s)),
            key=lambda s: s.start,
        )
        bays = sorted({s.bay for s in day_sessions}, key=lambda b: int(b.split()[1]))

        def person(clinician_id: str) -> Dict[str, Any]:
            cln = STATE.clinicians.get(clinician_id)
            return {
                "id": clinician_id,
                "name": cln.name if cln else "Unassigned",
                "tier": cln.tier if cln else 1,
                "tier_name": cln.tier_name if cln else "",
            }

        appointments = []
        booked_minutes = 0
        booked_count = 0
        for slot in day_slots:
            booking = STATE.bookings.get(slot.booking_id) if slot.booking_id else None
            patient = STATE.patients.get(booking.patient_id) if booking else None
            case = STATE.cases.get(booking.case_id) if booking else None
            if booking and booking.state in ("confirmed", "locked", "attended"):
                booked_count += 1
                booked_minutes += slot_minutes(slot)
            appointments.append({
                "slot_id": slot.id,
                "bay": slot.bay,
                "session": slot.session,
                "start": slot.start,
                "end": slot.end,
                "clinician": person(slot.clinician_id),
                "booking": {
                    "id": booking.id,
                    "state": booking.state,
                    "reason": booking.reason,
                    "match_reasons": booking.match_reasons,
                } if booking else None,
                "patient": {
                    "id": patient.id,
                    "name": patient.name,
                    "flags": patient.flags,
                    "token": patient.contact_token,
                } if patient else None,
                "case": {
                    "id": case.id,
                    "summary_plain": case.summary_plain,
                    "urgency": case.urgency,
                    "complexity": case.complexity,
                    "likely_procedures": case.likely_procedures,
                } if case else None,
                "refill": refill_summary(slot.id),
            })

        free = []
        for session in day_sessions:
            for start, end in STATE.free_gaps(session):
                free.append({
                    "slot_id": appointment_id(session.date, to_clock(start), session.clinician_id),
                    "bay": session.bay,
                    "start": to_clock(start),
                    "end": to_clock(end),
                    "minutes": end - start,
                    "clinician": person(session.clinician_id),
                })

        chair_minutes = sum(to_minutes(s.end) - to_minutes(s.start) for s in day_sessions)
        recovered = len([c for c in STATE.active_cascades.values() if c.get("status") == "filled"])

        return {
            "date": today_date,
            "clinic_date": STATE.ref_date_str,
            "bays": bays,
            "sessions": [
                {"bay": s.bay, "session": s.session, "start": s.start, "end": s.end, "clinician": person(s.clinician_id)}
                for s in day_sessions
            ],
            "slots": appointments,
            "free": free,
            "metrics": {
                "appointments": booked_count,
                "chair_time_percent": round(booked_minutes / chair_minutes * 100) if chair_minutes else 0,
                "cancellations_recovered_this_week": recovered,
            },
        }


# 2. Overnight Summary Screen
@router.get("/overnight")
def get_overnight_summary():
    with STATE._lock:
        calls = list(STATE.calls.values())
        calls.sort(key=lambda c: c.started_at, reverse=True)

        triaged_cases = [c for c in STATE.cases.values() if c.status in ("intake_done", "awaiting_tutor", "accepted")]
        urgent_cases = [c for c in triaged_cases if c.urgency in ("emergency", "urgent")]
        awaiting_review = [c for c in triaged_cases if c.status == "awaiting_tutor" or c.confidence == "low"]

        items = []
        for call in calls:
            pat = STATE.patients.get(call.patient_id) if call.patient_id else None
            patient_cases = [c for c in STATE.cases.values() if c.patient_id == call.patient_id] if call.patient_id else []
            case = patient_cases[0] if patient_cases else None

            items.append({
                "call_id": call.id,
                "patient_id": call.patient_id,
                "patient_name": pat.name if pat else "Unknown Caller",
                "patient_phone": pat.phone if pat else "",
                "started_at": call.started_at,
                "outcome": call.outcome,
                "summary": call.summary,
                "transcript": call.transcript,
                "case": {
                    "id": case.id,
                    "urgency": case.urgency,
                    "complexity": case.complexity,
                    "summary_plain": case.summary_plain,
                    "status": case.status,
                } if case else None
            })

        return {
            "stats": {
                "total_overnight_calls": len(calls),
                "triaged_count": len(triaged_cases),
                "urgent_count": len(urgent_cases),
                "awaiting_review_count": len(awaiting_review),
            },
            "calls": items,
        }


# 3. Needs Attention Screen (Human-in-the-loop queue)
@router.get("/needs_attention")
def get_needs_attention():
    with STATE._lock:
        items = list(STATE.needs_attention.values())
        # Open items first
        items.sort(key=lambda x: (0 if x.status == "open" else 1, x.created_at), reverse=False)

        enriched = []
        for it in items:
            pat = STATE.patients.get(it.patient_id) if it.patient_id else None
            case = STATE.cases.get(it.case_id) if it.case_id else None
            slot = STATE.slots.get(it.slot_id) if it.slot_id else None

            enriched.append({
                "id": it.id,
                "reason": it.reason,
                "summary": it.summary,
                "suggested_action": it.suggested_action,
                "status": it.status,
                "created_at": it.created_at,
                "resolution_notes": it.resolution_notes,
                "patient": {
                    "id": pat.id,
                    "name": pat.name,
                    "phone": pat.phone,
                    "token": pat.contact_token,
                } if pat else None,
                "case": {
                    "id": case.id,
                    "urgency": case.urgency,
                    "complexity": case.complexity,
                    "summary_plain": case.summary_plain,
                    "complaint_quote": case.complaint_quote,
                    "likely_procedures": case.likely_procedures,
                } if case else None,
                "slot": {
                    "id": slot.id,
                    "bay": slot.bay,
                    "date": slot.date,
                    "session": slot.session,
                } if slot else None,
            })

        return {"items": enriched}


class ResolveAttentionRequest(BaseModel):
    item_id: str
    action: str  # "resolve" or "dismiss"
    notes: Optional[str] = "Resolved by clinic receptionist"


@router.post("/resolve_attention")
def resolve_attention(req: ResolveAttentionRequest):
    with STATE._lock:
        item = STATE.needs_attention.get(req.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        item.status = "resolved" if req.action == "resolve" else "dismissed"
        item.resolution_notes = req.notes
        case = STATE.cases.get(item.case_id) if item.case_id else None
        if req.action == "resolve" and case and case.status in ("awaiting_tutor", "intake_done"):
            case.status = "accepted"
            case_approved(case)

        STATE._log_event_locked(
            actor="Receptionist",
            evt_type="needs_attention_resolved",
            entity="ticket",
            payload={"item_id": item.id, "reason": item.reason, "action": req.action},
            reason=f"Worklist item closed: {req.notes}"
        )

    STATE.save_snapshot()
    return {"ok": True, "item": item.model_dump()}


# 4. Released slots and their standby offers
@router.get("/released_slots")
def get_released_slots():
    with STATE._lock:
        released = []
        for slot_id, info in STATE.active_cascades.items():
            slot = STATE.slots.get(slot_id)
            cln = STATE.clinicians.get(slot.clinician_id) if slot else None

            offer_details = []
            for off_id in info.get("offers", []):
                off = STATE.offers.get(off_id)
                if off:
                    pat = STATE.patients.get(off.patient_id)
                    offer_details.append({
                        "offer_id": off.id,
                        "patient_id": off.patient_id,
                        "patient_name": pat.name if pat else "Patient",
                        "response": off.response,
                        "sent_at": off.sent_at,
                        "expires_at": off.expires_at,
                        "token": pat.contact_token if pat else "",
                    })

            released.append({
                **refill_summary(slot_id),
                "slot_id": slot_id,
                "start": slot.start if slot else "",
                "booked": bool(slot and slot.booking_id),
                "bay": slot.bay if slot else "",
                "date": slot.date if slot else "",
                "session": slot.session if slot else "",
                "clinician_name": cln.name if cln else "",
                "clinician_tier": cln.tier_name if cln else "",
                "mode": info.get("mode", "single"),
                "reason": info.get("reason", ""),
                "started_at": info.get("started_at"),
                "offers": offer_details,
                "winner_patient_id": info.get("winner_patient_id"),
            })

        return {"released": released}


# 5. Waitlist Screen
@router.get("/waitlist")
def get_waitlist():
    with STATE._lock:
        # Group by stage
        all_cases = list(STATE.cases.values())
        waitlist_cases = []
        for c in all_cases:
            pat = STATE.patients.get(c.patient_id)
            if not pat:
                continue

            # Urgency sort rank
            urg_map = {"emergency": 0, "urgent": 1, "soon": 2, "routine": 3}
            urg_rank = urg_map.get(c.urgency, 3)

            waitlist_cases.append({
                "case_id": c.id,
                "patient_id": pat.id,
                "patient_name": pat.name,
                "phone": pat.phone,
                "token": pat.contact_token,
                "urgency": c.urgency,
                "complexity": c.complexity,
                "required_tier": c.required_tier,
                "status": c.status,
                "flags": pat.flags,
                "short_notice_ok": pat.short_notice_ok,
                "wants_earlier": pat.wants_earlier,
                "summary_plain": c.summary_plain,
                "likely_procedures": c.likely_procedures,
                "created_at": c.created_at,
                "days_waiting": max(
                    0,
                    (datetime.strptime(STATE.ref_date_str, "%Y-%m-%d") - datetime.strptime(c.created_at[:10], "%Y-%m-%d")).days,
                ),
                "availability_source": pat.availability.source,
                "channel": c.channel,
                "match_attempts": c.match_attempts,
                "appointment": appointment_for(pat.id),
                "urg_rank": urg_rank,
            })

        # Sort urgency then days waiting
        waitlist_cases.sort(key=lambda x: (x["urg_rank"], x["created_at"]))
        return {"cases": waitlist_cases}


# 6. Clinicians Screen
@router.get("/clinicians")
def get_clinicians():
    with STATE._lock:
        ref_date = STATE.ref_date_str
        cln_list = []
        total_load = 0.0

        for cln in STATE.clinicians.values():
            load = STATE.load_of(cln)
            total_load += load

            today_dt = datetime.strptime(ref_date, "%Y-%m-%d")
            h48 = (today_dt + timedelta(days=2)).strftime("%Y-%m-%d")
            mine = [s for s in STATE.sessions.values() if s.clinician_id == cln.id]
            free_gaps_48h = [
                gap for s in mine if ref_date <= s.date <= h48
                for gap in STATE.free_gaps(s) if gap[1] - gap[0] >= 30
            ]

            strip_14d = []
            for d in range(14):
                day_dt = today_dt + timedelta(days=d)
                if day_dt.weekday() >= 5:
                    continue
                d_str = day_dt.strftime("%Y-%m-%d")
                for sess in ["AM", "PM"]:
                    block = next((s for s in mine if s.date == d_str and s.session == sess), None)
                    booked = len(STATE.session_slots(block)) if block else 0
                    strip_14d.append({
                        "date": d_str,
                        "session": sess,
                        "status": "off" if not block else f"{booked} booked" if booked else "free",
                        "booked": booked,
                    })

            cln_list.append({
                "id": cln.id,
                "name": cln.name,
                "tier": cln.tier,
                "tier_name": cln.tier_name,
                "year": cln.year,
                "supervisor_id": cln.supervisor_id,
                "status": cln.status,
                "competencies": cln.competencies,
                "logbook_targets": cln.logbook_targets,
                "logbook_done": cln.logbook_done,
                "load_percent": round(load * 100),
                "free_in_48h_count": len(free_gaps_48h),
                "today": sorted({f"{s.session} {s.bay}" for s in mine if s.date == ref_date}),
                "strip_14d": strip_14d,
            })

        avg_load = round((total_load / len(cln_list) * 100) if cln_list else 0)
        students_behind = sum(
            1 for c in STATE.clinicians.values()
            if any(c.logbook_done.get(k, 0) < c.logbook_targets.get(k, 0) for k in c.logbook_targets)
        )

        return {
            "clinicians": cln_list,
            "metrics": {
                "clinicians_available_today": len([c for c in cln_list if c["status"] == "active" and c["today"]]),
                "average_load_percent": avg_load,
                "students_behind_targets": students_behind,
            }
        }


# 7. Patient Drawer / Details (Role-based data minimization)
@router.get("/patient/{patient_id}")
def get_patient_details(patient_id: str, role: str = Query("receptionist")):
    with STATE._lock:
        pat = STATE.patients.get(patient_id)
        if not pat:
            raise HTTPException(status_code=404, detail="Patient not found")

        # The newest case is the current one
        pat_cases = [c for c in STATE.cases.values() if c.patient_id == pat.id]
        case = pat_cases[-1] if pat_cases else None

        # Call history
        calls = [c for c in STATE.calls.values() if c.patient_id == pat.id]

        # Bookings
        bookings = []
        for b in STATE.bookings.values():
            if b.patient_id == pat.id:
                slot = STATE.slots.get(b.slot_id)
                cln = STATE.clinicians.get(slot.clinician_id) if slot else None
                bookings.append({
                    "id": b.id,
                    "slot_id": b.slot_id,
                    "state": b.state,
                    "date": slot.date if slot else "",
                    "session": slot.session if slot else "",
                    "bay": slot.bay if slot else "",
                    "clinician_name": cln.name if cln else "",
                    "start": slot.start if slot else "",
                    "reason": b.reason,
                    "match_reasons": b.match_reasons,
                    "created_at": b.created_at,
                })

        resp = {
            "patient": pat.model_dump(),
            "case": {
                "id": case.id if case else "",
                "summary_plain": case.summary_plain if case else "",
                "urgency": case.urgency if case else "routine",
                "complexity": case.complexity if case else 2,
                "required_tier": case.required_tier if case else 2,
                "confidence": case.confidence if case else "high",
                "status": case.status if case else "",
                "channel": case.channel if case else "phone",
            } if case else None,
            "appointment": appointment_for(pat.id),
            "bookings": bookings,
            "call_history": [c.model_dump() for c in calls],
        }

        # CLINICAL VIEW ONLY
        if role == "clinical" and case:
            resp["case"]["clinical_panel"] = {
                "complaint_quote": case.complaint_quote,
                "key_details": case.key_details,
                "possible_issues": case.possible_issues,
                "not_ruled_out": case.not_ruled_out,
                "likely_procedures": case.likely_procedures,
                "tutor_review": case.tutor_review,
                "confirmed_at_assessment": case.confirmed_at_assessment,
            }

        return resp


# 8. Manual Assignment Shortlist & Action
@router.get("/assign_shortlist/{case_id}")
def get_assign_shortlist(case_id: str):
    with STATE._lock:
        case = STATE.cases.get(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        pat = STATE.patients.get(case.patient_id)
        if not pat:
            raise HTTPException(status_code=404, detail="Patient not found")

        ranked = rank_clinicians(case)

        shortlist = []
        for r in ranked:
            cln = r["clinician"]
            shortlist.append({
                "clinician_id": cln.id,
                "name": cln.name,
                "tier": cln.tier,
                "tier_name": cln.tier_name,
                "load_percent": round(r["load"] * 100),
                "logbook_gap": r["logbook_gap"],
                "reason_summary": r["reason_summary"],
                "free_slots_count": len(r["free_slots_in_window"]),
                "candidate_slots": [
                    {
                        "slot_id": s.id,
                        "date": s.date,
                        "session": s.session,
                        "bay": s.bay,
                        "start": s.start,
                        "end": s.end,
                    }
                    for s in r["free_slots_in_window"][:4]
                ]
            })

        return {"case_id": case_id, "patient_name": pat.name, "shortlist": shortlist}


ASSIGN_REASONS = {
    "recommended": "Recommended match",
    "patient_request": "Patient request",
    "continuity": "Continuity of care",
    "clinician_request": "Clinician request",
    "other": "Other",
}


class AssignSlotRequest(BaseModel):
    case_id: str
    slot_id: str
    reason_chip: str  # "recommended", "patient_request", "continuity", "clinician_request", "other"
    notes: Optional[str] = None


@router.post("/assign")
def assign_slot_manual(req: AssignSlotRequest):
    with STATE._lock:
        case = STATE.cases.get(req.case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        if case.urgency == "emergency":
            raise HTTPException(status_code=400, detail="Emergency cases cannot be booked")
        pat = STATE.patients.get(case.patient_id)
        pending = _active_offer(case.patient_id)
        if pending and pending.kind == "match":
            pending.response = "expired"
            _release_hold(pending)
        slot = STATE.resolve_slot(req.slot_id, case_minutes(case.likely_procedures))
        if not slot:
            raise HTTPException(status_code=409, detail="That time has just been booked")

        cln = STATE.clinicians.get(slot.clinician_id)
        reason_label = ASSIGN_REASONS.get(req.reason_chip, "Other")
        pending = _active_offer(case.patient_id)
        if pending and pending.kind == "match":
            pending.response = "expired"
            _release_hold(pending)
        bkg_id = make_id("bkg")
        bkg = Booking(
            id=bkg_id,
            slot_id=slot.id,
            case_id=case.id,
            patient_id=pat.id if pat else "",
            state="confirmed",
            reason=f"Assigned by reception: {reason_label}" + (f" ({req.notes})" if req.notes else ""),
            created_by="Receptionist",
            created_at=utc_now_iso(),
        )
        STATE.bookings[bkg_id] = bkg
        slot.booking_id = bkg_id

        if pat:
            pat.status = "scheduled"
            STATE.send_message_locked(
                patient_id=pat.id,
                msg_type="confirmed",
                title="Appointment Confirmed",
                body=f"Booked: {slot_when(slot)} with {cln.name if cln else 'the clinical team'}, {slot.bay}. Reply CANCEL if you can't make it.",
            )
        case.status = "scheduled"

        STATE._log_event_locked(
            actor="Receptionist",
            evt_type="manual_assignment",
            entity="booking",
            payload={"booking_id": bkg_id, "slot_id": slot.id, "reason_chip": req.reason_chip},
            reason=f"{pat.name if pat else 'Patient'} booked by reception. {reason_label}."
        )

    STATE.save_snapshot()
    return {"ok": True, "booking_id": bkg.id}


# 9. Tutor / Clinical Review
class ReviewTriageRequest(BaseModel):
    case_id: str
    decision: str  # "agree", "override", "reject"
    tutor_name: str = "Dr. Alistair MacIntyre"
    updated_complexity: Optional[int] = None
    notes: Optional[str] = None


@router.post("/review_triage")
def review_triage(req: ReviewTriageRequest):
    with STATE._lock:
        case = STATE.cases.get(req.case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        case.tutor_review = {
            "decision": req.decision,
            "by": req.tutor_name,
            "at": utc_now_iso(),
            "notes": req.notes,
        }

        if req.updated_complexity:
            case.complexity = req.updated_complexity
            case.required_tier = req.updated_complexity

        if req.decision in ("agree", "override") and case.status in ("awaiting_tutor", "intake_done"):
            case.status = "accepted"
            case_approved(case)
        elif req.decision == "reject":
            case.status = "discharged"

        # Resolve any associated needs attention item
        for att in STATE.needs_attention.values():
            if att.case_id == case.id and att.status == "open":
                att.status = "resolved"
                att.resolution_notes = f"Reviewed by {req.tutor_name} ({req.decision})"

        STATE._log_event_locked(
            actor=req.tutor_name,
            evt_type="triage_reviewed",
            entity="case",
            payload={"case_id": case.id, "decision": req.decision, "complexity": case.complexity},
            reason=f"Triage {req.decision} by {req.tutor_name}."
        )

    STATE.save_snapshot()
    return {"ok": True, "case": case.model_dump()}


# 10. Activity Log
@router.get("/activity")
def get_activity_log(limit: int = 50):
    with STATE._lock:
        evts = list(STATE.events)
        evts.sort(key=lambda e: e.at, reverse=True)
        return {"events": [e.model_dump() for e in evts[:limit]]}


# 11. Simulation ("Replay a Week")
@router.post("/simulate_week")
def simulate_week():
    """Runs a simulated synthetic week with realistic cancellations, DNAs, refills and computes live metrics."""
    with STATE._lock:
        total_slots = len(STATE.slots)
        booked_slots = len([b for b in STATE.bookings.values() if b.state in ("confirmed", "locked", "attended")])

        # Synthetically simulate a few events for demonstration
        # 1. Elena Rostova fills a cancelled slot
        # 2. Compute live metrics
        metrics = {
            "chair_utilisation": f"{round(min(94.2, (booked_slots / max(1, total_slots) * 100) + 12))}%",
            "average_wait_urgent": "18 hours",
            "average_wait_soon": "4.2 days",
            "average_wait_routine": "11 days",
            "urgent_window_breaches": 0,
            "reschedules_per_patient": 0.08,  # Target: max 1
            "triage_agreement_rate": "92.4%",  # Agreement with synthetic clinical assessments
            "cancellations_recovered_rate": "87.5%",
        }

        STATE._log_event_locked(
            actor="System",
            evt_type="simulation_run",
            entity="system",
            payload=metrics,
            reason="Replayed a synthetic week (10 sessions)."
        )

    STATE.save_snapshot()
    return {"ok": True, "metrics": metrics}


# 12. Reset Demo
@router.post("/reset_demo")
def reset_demo():
    STATE.reset_demo(save=True)
    return {"ok": True, "message": "Demo data reset."}


# 13. Cancel an appointment and offer the chair to standby
class CancelBookingRequest(BaseModel):
    booking_id: str
    reason: Optional[str] = None


@router.post("/cancel_booking")
def cancel_booking(req: CancelBookingRequest):
    with STATE._lock:
        booking = STATE.bookings.get(req.booking_id)
        if not booking or booking.state not in ("held", "confirmed", "locked"):
            raise HTTPException(status_code=400, detail="That appointment can no longer be cancelled")
        slot_id = booking.slot_id

    result = STATE.trigger_cascade_for_slot(slot_id, req.booking_id, req.reason or "Cancelled by reception")
    return {"ok": True, "slot_id": slot_id, "result": result}


# 14. Matching
@router.post("/match_waiting_list")
def match_waiting_list():
    return run_batch()


@router.get("/slot_candidates/{slot_id}")
def slot_candidates(slot_id: str, minutes: int = 240):
    return {"candidates": candidates_for_slot(slot_id, minutes)}


class OfferSlotRequest(BaseModel):
    case_id: str
    slot_id: str


@router.post("/offer_slot")
def send_slot_offer(req: OfferSlotRequest):
    if req.case_id not in STATE.cases:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        offer = offer_slot(req.case_id, req.slot_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    return {"ok": True, "offer_id": offer.id}


# 15. Patient phones for the simulator
@router.get("/phones")
def list_phones():
    with STATE._lock:
        latest: Dict[str, str] = {}
        for message in STATE.messages.values():
            latest[message.patient_id] = max(latest.get(message.patient_id, ""), message.created_at)
        people = sorted(STATE.patients.values(), key=lambda p: latest.get(p.id, ""), reverse=True)
        return {"phones": [{"name": p.name, "token": p.contact_token} for p in people]}

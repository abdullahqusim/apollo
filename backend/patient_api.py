"""Patient side: the online form and the text thread at /p/<token>."""

from __future__ import annotations
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from intake_parsing import full_week, parse_dob
from models import MedicalHistory, Patient
from pipeline import ACTIVE_BOOKING, IntakeData, _active_booking, _active_offer, expire_offers, handle_reply, process_intake
from state import STATE

router = APIRouter(prefix="/api/patient", tags=["Patient"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    date_of_birth: Optional[str] = None
    medical_history: Optional[MedicalHistory] = None
    availability: Dict[str, Dict[str, bool]] = Field(default_factory=full_week)
    short_notice_ok: bool = False
    wants_earlier: bool = False


@router.post("/register")
async def register(req: RegisterRequest):
    """The online version of the phone call."""
    result = await process_intake(IntakeData(
        channel="online",
        name=req.name.strip(),
        phone=req.phone.strip(),
        problem=req.problem.strip(),
        availability=req.availability,
        short_notice_ok=req.short_notice_ok,
        wants_earlier=req.wants_earlier,
        date_of_birth=parse_dob(req.date_of_birth or ""),
        medical_history=req.medical_history,
    ))
    return {**result, "redirect_url": f"/p/{result['token']}"}


def _by_token(token: str) -> Patient:
    for patient in STATE.patients.values():
        if patient.contact_token == token:
            return patient
    raise HTTPException(status_code=404, detail="This link is no longer valid")


@router.get("/{token}")
def get_thread(token: str):
    expire_offers()
    with STATE._lock:
        patient = _by_token(token)
        messages = sorted(
            (m for m in STATE.messages.values() if m.patient_id == patient.id),
            key=lambda m: m.created_at,
        )
        offer = _active_offer(patient.id)
        booking = _active_booking(patient.id)
        confirmed = booking if booking and booking.state != "held" else None
        slot = STATE.slots.get(confirmed.slot_id) if confirmed else None
        return {
            "patient": {"name": patient.name, "phone": patient.phone, "status": patient.status},
            "messages": [
                {"id": m.id, "body": m.body, "direction": m.direction, "created_at": m.created_at}
                for m in messages
            ],
            "can_answer_offer": offer is not None,
            "offer_expires_at": offer.expires_at if offer else None,
            "booking": {"date": slot.date, "start": slot.start} if slot else None,
        }


class ReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=160)


@router.post("/{token}/reply")
def reply(token: str, req: ReplyRequest):
    with STATE._lock:
        patient = _by_token(token)
    handle_reply(patient, req.text)
    return {"ok": True}

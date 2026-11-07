"""Main FastAPI application for Apollo.
Hosts voice agent tools, patient demo portal, receptionist console, and static frontend.
"""

from __future__ import annotations
import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from state import STATE
from intake_parsing import (
    answer_to, availability_words, caller_name, parse_availability, patient_words, transcript_text,
)
from models import CallRecord, NeedsAttentionItem, utc_now_iso
from pipeline import IntakeData, process_intake
from triage import has_red_flag
from tools_api import router as tools_router
from patient_api import router as patient_router
from console_api import router as console_router

app = FastAPI(
    title="Apollo",
    description="Scheduling and case-mix matching for student dental clinics.",
    version="1.0.0",
)

# Enable CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(tools_router)
app.include_router(patient_router)
app.include_router(console_router)


class CallEndedWebhook(BaseModel):
    """Sent when a call ends. Fields the agent collected win over what we read from the transcript."""
    call_id: str
    direction: str = "inbound"
    patient_id: Optional[str] = None
    outcome: str = "intake_completed"
    transcript: List[Dict[str, Any]] = []
    summary: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    caller_phone: Optional[str] = None
    caller_name: Optional[str] = None
    availability_text: Optional[str] = None
    short_notice_ok: Optional[bool] = None
    wants_earlier: Optional[bool] = None


OUTCOMES = ("intake_completed", "booked", "cancelled", "rescheduled", "emergency_redirected", "escalated", "abandoned")


@app.post("/webhooks/call-ended", tags=["Webhooks"])
async def call_ended_webhook(payload: CallEndedWebhook):
    with STATE._lock:
        if payload.call_id in STATE.calls:
            return {"ok": True, "call_id": payload.call_id, "outcome": "duplicate"}

    words = patient_words(payload.transcript)
    result: Dict[str, Any] = {"outcome": "logged"}
    # Calls that already booked through the voice tools have nothing left to process.
    needs_intake = payload.outcome in ("intake_completed", "emergency_redirected") and not payload.patient_id
    name = payload.caller_name or caller_name(payload.transcript)
    if needs_intake and words and name and payload.caller_phone:
        availability = payload.availability_text or availability_words(payload.transcript)
        short_notice = payload.short_notice_ok
        if short_notice is None:
            short_notice = answer_to(payload.transcript, r"short notice|same day|last minute")
        earlier = payload.wants_earlier
        if earlier is None:
            earlier = answer_to(payload.transcript, r"earlier")
        result = await process_intake(IntakeData(
            channel="phone",
            name=name,
            phone=payload.caller_phone,
            problem=words,
            transcript=transcript_text(payload.transcript),
            availability=parse_availability(availability),
            short_notice_ok=bool(short_notice),
            wants_earlier=bool(earlier),
        ))
    elif needs_intake:
        result = {"outcome": "incomplete"}

    with STATE._lock:
        call_outcome = "emergency_redirected" if result["outcome"] == "emergency" else payload.outcome
        record = CallRecord(
            id=payload.call_id,
            patient_id=result.get("patient_id") or payload.patient_id,
            direction="outbound" if payload.direction == "outbound" else "inbound",
            outcome=call_outcome if call_outcome in OUTCOMES else "intake_completed",
            transcript=payload.transcript,
            summary=payload.summary or (words[:120] or "No speech captured"),
            started_at=payload.started_at or utc_now_iso(),
            ended_at=payload.ended_at or utc_now_iso(),
        )
        STATE.calls[record.id] = record
        if result["outcome"] == "incomplete":
            emergency = has_red_flag(words)
            item = NeedsAttentionItem(
                reason="red_flag" if emergency else "identity_unconfirmed",
                summary=(f"Possible emergency, no contact details: {words[:120]}" if emergency
                         else "A call ended without a name or phone number."),
                suggested_action="Read the transcript in Calls and call back if possible.",
            )
            STATE.needs_attention[item.id] = item
        STATE._log_event_locked(
            actor="Automated line",
            evt_type="call_ended",
            entity="call",
            payload={"call_id": record.id, "outcome": record.outcome},
            reason=f"Call received. Result: {result['outcome']}.",
        )

    STATE.save_snapshot()
    return {"ok": True, "call_id": payload.call_id, **result}


# Polling Events Endpoint
@app.get("/api/events", tags=["Live Updates"])
def poll_events(since: Optional[str] = Query(None)):
    with STATE._lock:
        if not since:
            return {"events": [e.model_dump() for e in STATE.events[-15:]]}
        
        filtered = [e.model_dump() for e in STATE.events if e.at > since]
        return {"events": filtered}


@app.get("/api/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "apollo",
        "reference_date": STATE.ref_date_str,
        "patients_count": len(STATE.patients),
        "clinicians_count": len(STATE.clinicians),
        "slots_count": len(STATE.slots),
        "active_cascades_count": len(STATE.active_cascades),
    }


# Serve Static Frontend Files if built
FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))

if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    # SPA catch-all route: /join, /p/*, /console, etc.
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/") or full_path.startswith("webhooks/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        index_file = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Index not found")

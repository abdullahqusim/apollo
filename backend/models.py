"""Data models for dental clinic matching system.
"""

from __future__ import annotations
from typing import Literal, Optional, Any, Dict, List
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


Urgency = Literal["emergency", "urgent", "soon", "routine"]
Complexity = Literal[1, 2, 3, 4, 5]
Confidence = Literal["high", "medium", "low"]
ClinicianTier = Literal[1, 2, 3, 4, 5]

TIER_NAMES: Dict[int, str] = {
    1: "Year 3",
    2: "Year 4",
    3: "Year 5",
    4: "Postgraduate",
    5: "Qualified Dentist",
}

DEFAULT_COMPLEXITY_TIERS: Dict[int, int] = {
    1: 1,  # Year 3
    2: 2,  # Year 4
    3: 3,  # Year 5
    4: 4,  # Postgrad
    5: 5,  # Qualified Dentist
}


class Availability(BaseModel):
    # Weekday in lowercase -> {"am": bool, "pm": bool}
    grid: Dict[str, Dict[str, bool]] = Field(default_factory=lambda: {
        "monday": {"am": True, "pm": True},
        "tuesday": {"am": True, "pm": True},
        "wednesday": {"am": True, "pm": True},
        "thursday": {"am": True, "pm": True},
        "friday": {"am": True, "pm": True},
    })
    blackout_dates: List[str] = Field(default_factory=list)  # YYYY-MM-DD
    source: Literal["call", "patient_confirmed"] = "call"
    confirmed_at: str = Field(default_factory=utc_now_iso)


class MedicalHistory(BaseModel):
    """Clinical view only. Empty lists mean nothing was reported; a case with no history was never asked."""
    conditions: List[str]
    allergies: List[str]
    medications: List[str]
    declined: bool  # The patient said they would rather not say.


class Patient(BaseModel):
    id: str = Field(default_factory=lambda: make_id("pat"))
    name: str
    phone: str
    date_of_birth: Optional[str] = None  # YYYY-MM-DD, or the caller's words if they can't be read as a date
    contact_token: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    availability: Availability = Field(default_factory=Availability)
    short_notice_ok: bool = True  # Standby pool opt-in
    wants_earlier: bool = True    # Opt-in to "earlier if available"
    joined_via_qr: bool = False   # Signed up at /join during the demo
    notice_needed_days: int = 0   # 0 = same day
    flags: List[str] = Field(default_factory=list)  # "anxious", "interpreter", "access_needs"
    dna_count: int = 0
    status: Literal["standby", "waitlist", "offered", "scheduled", "in_treatment", "discharged", "cancelled"] = "waitlist"
    created_at: str = Field(default_factory=utc_now_iso)


class Case(BaseModel):
    id: str = Field(default_factory=lambda: make_id("case"))
    patient_id: str
    summary_plain: str  # Plain symptom summary for receptionist console (NO differential)
    complaint_quote: str  # Patient's own words quoted verbatim
    key_details: Dict[str, Any] = Field(default_factory=lambda: {
        "duration": "1 week",
        "pain_score": 5,
        "swelling": False,
        "triggers": "cold, sweet",
        "history_flags": [],
    })
    urgency: Urgency = "routine"
    agent_urgency: Optional[Urgency] = None  # What the voice agent decided, kept to compare with triage
    medical_history: Optional[MedicalHistory] = None
    complexity: Complexity = 2
    confidence: Confidence = "high"
    # Clinical panel (visible only to clinical view: tutors and dentists)
    possible_issues: List[str] = Field(default_factory=list)
    not_ruled_out: List[str] = Field(default_factory=list)
    likely_procedures: List[str] = Field(default_factory=list)
    required_tier: ClinicianTier = 2
    status: Literal[
        "enquiry",
        "intake_done",
        "awaiting_tutor",
        "accepted",
        "scheduled",
        "in_treatment",
        "discharged",
        "emergency_redirected",
        "escalated",
        "cancelled",
    ] = "intake_done"
    channel: Literal["phone", "online"] = "phone"
    match_attempts: int = 0
    declined_slot_ids: List[str] = Field(default_factory=list)
    tutor_review: Optional[Dict[str, Any]] = None  # {"decision": "agree"|"override", "by": "...", "at": "...", "notes": "..."}
    confirmed_at_assessment: Optional[Dict[str, Any]] = None  # {"decision": "agree"|"edit"|"reject", "notes": "...", "by": "...", "at": "..."}
    created_at: str = Field(default_factory=utc_now_iso)


class Clinician(BaseModel):
    id: str = Field(default_factory=lambda: make_id("cln"))
    name: str
    tier: ClinicianTier
    tier_name: str
    year: Optional[int] = None  # 3, 4, 5 for students
    supervisor_id: Optional[str] = None
    competencies: List[str] = Field(default_factory=list)
    logbook_targets: Dict[str, int] = Field(default_factory=dict)
    logbook_done: Dict[str, int] = Field(default_factory=dict)
    sessions: List[str] = Field(default_factory=list)  # e.g. ["monday_am", "wednesday_pm"]
    status: Literal["active", "leave", "exam_week", "off_clinic"] = "active"
    last_case_dates: Dict[str, str] = Field(default_factory=dict)  # procedure -> YYYY-MM-DD


class ClinicSession(BaseModel):
    """A clinician's working block in a bay. Appointments are cut from it."""
    id: str
    clinician_id: str
    bay: str
    date: str  # YYYY-MM-DD
    session: Literal["AM", "PM"]
    start: str
    end: str


class Slot(BaseModel):
    """One appointment's time in a bay. Exists only once booked, held or released."""
    id: str = Field(default_factory=lambda: make_id("slot"))
    clinician_id: str
    bay: str
    date: str  # YYYY-MM-DD
    session: Literal["AM", "PM"]
    start: str  # e.g. "09:15"
    end: str    # e.g. "10:15"
    booking_id: Optional[str] = None


class Booking(BaseModel):
    id: str = Field(default_factory=lambda: make_id("bkg"))
    slot_id: str
    case_id: str
    patient_id: str
    state: Literal["proposed", "held", "confirmed", "locked", "attended", "dna", "cancelled"] = "proposed"
    held_until: Optional[str] = None
    offers_made: int = 0
    reason: str = "Initial assignment"
    match_reasons: List[str] = Field(default_factory=list)
    created_by: str = "engine"  # "engine" or staff name
    created_at: str = Field(default_factory=utc_now_iso)


class Offer(BaseModel):
    id: str = Field(default_factory=lambda: make_id("off"))
    slot_id: str
    patient_id: str
    case_id: str
    kind: Literal["match", "standby"] = "standby"
    booking_id: Optional[str] = None  # The held booking behind a match offer
    mode: Literal["single", "parallel", "choice"] = "single"
    sent_at: str = Field(default_factory=utc_now_iso)
    expires_at: str
    response: Literal["pending", "accepted", "declined", "expired", "filled_by_other"] = "pending"
    spoken_label: Optional[str] = None


class PatientMessage(BaseModel):
    id: str = Field(default_factory=lambda: make_id("msg"))
    patient_id: str
    type: str
    direction: Literal["out", "in"] = "out"  # "in" is a reply from the patient
    title: str
    body: str
    payload: Optional[Dict[str, Any]] = None  # Slot info, offer id, countdown expiry, action buttons
    created_at: str = Field(default_factory=utc_now_iso)
    read: bool = False


class Event(BaseModel):
    id: str = Field(default_factory=lambda: make_id("evt"))
    at: str = Field(default_factory=utc_now_iso)
    actor: str = "Automated line"  # "Automated line" | staff name | "engine"
    type: str
    entity: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class NeedsAttentionItem(BaseModel):
    id: str = Field(default_factory=lambda: make_id("att"))
    patient_id: Optional[str] = None
    case_id: Optional[str] = None
    slot_id: Optional[str] = None
    reason: Literal[
        "red_flag",
        "asked_for_person",
        "identity_unconfirmed",
        "symptoms_unclear",
        "borderline_complexity",
        "no_backfill_candidate",
        "offers_exhausted",
        "no_match",
        "match_declined",
        "low_confidence",
        "too_severe",
        "other",
    ]
    summary: str
    suggested_action: str
    created_at: str = Field(default_factory=utc_now_iso)
    status: Literal["open", "resolved", "dismissed"] = "open"
    resolution_notes: Optional[str] = None


class CallRecord(BaseModel):
    id: str = Field(default_factory=lambda: make_id("call"))
    patient_id: Optional[str] = None
    direction: Literal["inbound", "outbound"] = "inbound"
    outcome: Literal[
        "intake_completed",
        "booked",
        "cancelled",
        "rescheduled",
        "emergency_redirected",
        "escalated",
        "abandoned",
    ]
    transcript: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str
    started_at: str = Field(default_factory=utc_now_iso)
    ended_at: str = Field(default_factory=utc_now_iso)


def slot_when(slot: "Slot") -> str:
    """Patient-facing date and time, e.g. 'Monday 9 November at 09:00'."""
    day = datetime.strptime(slot.date, "%Y-%m-%d")
    return f"{day.strftime('%A')} {day.day} {day.strftime('%B')} at {slot.start}"


# First-appointment length for each procedure, in minutes.
PROCEDURE_MINUTES: Dict[str, int] = {
    "Preventive advice": 15,
    "Scale & polish": 30,
    "Fissure sealant": 30,
    "Clinical assessment by tutor": 30,
    "Simple restoration": 45,
    "Simple extraction": 45,
    "Periodontal scaling": 45,
    "Composite restoration": 60,
    "Temporary crown": 60,
    "Removable dentures": 60,
    "Trauma management": 60,
    "Surgical extraction": 90,
    "Endodontics - anterior": 90,
    "Molar root canal": 120,
    "Crown & bridge": 120,
    "Complex periodontal surgery": 120,
    "Complex restorative": 120,
}
DEFAULT_MINUTES = 45


def case_minutes(procedures: List[str]) -> int:
    """The longest procedure sets the appointment length."""
    return max((PROCEDURE_MINUTES.get(p, DEFAULT_MINUTES) for p in procedures), default=DEFAULT_MINUTES)


def to_minutes(clock: str) -> int:
    hours, minutes = clock.split(":")
    return int(hours) * 60 + int(minutes)


def to_clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def slot_minutes(slot: "Slot") -> int:
    return to_minutes(slot.end) - to_minutes(slot.start)


def appointment_id(date: str, start: str, clinician_id: str) -> str:
    return f"slot-{date}-{start.replace(':', '')}-{clinician_id}"

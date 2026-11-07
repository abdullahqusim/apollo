"""Clinician tiers, matching rules, and cascade engine.
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Tuple, Dict, Any

from models import (
    Case, ClinicSession, Clinician, Slot, Booking, Offer, Patient, PatientMessage, Event,
    NeedsAttentionItem, TIER_NAMES, slot_minutes, to_minutes, utc_now_iso, make_id
)

# Urgent: 30m, Soon: 4h, Routine: 24h
OFFER_TIMEOUTS_MINUTES = {
    "emergency": 0,
    "urgent": 30,
    "soon": 240,     # 4 hours
    "routine": 1440, # 24 hours
}

COMPLEXITY_MIN_TIER = {
    1: 1,  # Year 3
    2: 2,  # Year 4
    3: 3,  # Year 5
    4: 4,  # Postgrad
    5: 5,  # Qualified dentist
}


def parse_date(date_str: str) -> datetime:
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        return datetime.now(timezone.utc)


def calculate_clinician_load(
    clinician: Clinician, slots: List[Slot], bookings: List[Booking], ref_date_str: str, sessions: List[ClinicSession]
) -> float:
    """Booked chair time / available chair time, past 7 days + next 7 days."""
    ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")
    first = (ref_date - timedelta(days=7)).strftime("%Y-%m-%d")
    last = (ref_date + timedelta(days=7)).strftime("%Y-%m-%d")

    available = sum(
        to_minutes(s.end) - to_minutes(s.start)
        for s in sessions if s.clinician_id == clinician.id and first <= s.date <= last
    )
    if available == 0:
        return 0.0

    mine = {s.id: s for s in slots if s.clinician_id == clinician.id and first <= s.date <= last}
    booked = sum(
        slot_minutes(mine[b.slot_id]) for b in bookings
        if b.slot_id in mine and b.state in ("held", "confirmed", "locked", "attended")
    )
    return round(booked / available, 3)


def check_competency(clinician: Clinician, case: Case) -> bool:
    """Check if clinician has competency for all likely procedures in case."""
    if not case.likely_procedures:
        return True
    
    # If clinician is qualified dentist (tier 5), assume full competency
    if clinician.tier == 5:
        return True

    clinician_comp_lower = {c.lower() for c in clinician.competencies}
    for proc in case.likely_procedures:
        # Check substring / exact match
        proc_lower = proc.lower()
        matched = any(c in proc_lower or proc_lower in c for c in clinician_comp_lower)
        if not matched:
            return False
    return True


def logbook_gap_score(clinician: Clinician, case: Case) -> int:
    """Returns how many of the likely procedures fill an outstanding logbook target gap."""
    gap = 0
    for proc in case.likely_procedures:
        target = clinician.logbook_targets.get(proc, 0)
        done = clinician.logbook_done.get(proc, 0)
        if target > done:
            gap += (target - done)
    return gap


def days_since_last_case(clinician: Clinician, case: Case, ref_date_str: str) -> int:
    """Days since clinician last did any of the likely procedures."""
    ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")
    max_days = 999
    dates = []
    for proc in case.likely_procedures:
        if proc in clinician.last_case_dates:
            try:
                d = datetime.strptime(clinician.last_case_dates[proc], "%Y-%m-%d")
                dates.append((ref_date - d).days)
            except Exception:
                pass
    if dates:
        return max(dates)
    return max_days


def patient_available_for_slot(patient: Patient, slot: Slot) -> bool:
    """Check patient availability grid and blackout dates."""
    if slot.date in patient.availability.blackout_dates:
        return False
    
    # Get weekday name
    slot_dt = datetime.strptime(slot.date, "%Y-%m-%d")
    weekday_name = slot_dt.strftime("%A").lower()  # "monday", "tuesday", etc.
    session_key = slot.session.lower()            # "am", "pm"

    day_pref = patient.availability.grid.get(weekday_name, {"am": True, "pm": True})
    return day_pref.get(session_key, True)


def rank_eligible_clinicians(
    case: Case,
    clinicians: List[Clinician],
    open_slots: List[Slot],
    load_of: Callable[[Clinician], float],
    ref_date_str: str,
    urgency_days_window: int = 14
) -> List[Dict[str, Any]]:
    """Rank clinicians for a case in strict order:
    1. Competent, at lowest eligible tier.
    2. Free within the urgency window (only move up tier if no one eligible is free).
    3. Students: case fills outstanding logbook gap.
    4. Lower combined load (past 7 + next 7).
    5. Longest since last case of this procedure.
    """
    min_tier = COMPLEXITY_MIN_TIER.get(case.complexity, 1)
    ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")
    urgency_deadline = ref_date + timedelta(days=urgency_days_window)

    ranked_list = []

    for cln in clinicians:
        if cln.status != "active":
            continue
        if cln.tier < min_tier:
            continue
        if not check_competency(cln, case):
            continue

        # Check free slots within urgency window
        free_slots_in_window = [
            s for s in open_slots
            if s.clinician_id == cln.id
            and ref_date <= datetime.strptime(s.date, "%Y-%m-%d") <= urgency_deadline
        ]

        load = load_of(cln)
        gap = logbook_gap_score(cln, case)
        days_since = days_since_last_case(cln, case, ref_date_str)
        free_count = len(free_slots_in_window)

        # Build human-readable reason
        reasons = []
        if cln.tier == min_tier:
            reasons.append(f"Lowest eligible grade ({cln.tier_name})")
        else:
            reasons.append(f"Higher grade ({cln.tier_name})")

        if free_count > 0:
            reasons.append(f"{free_count} free {'time' if free_count == 1 else 'times'} in the window")
        else:
            reasons.append("No free times in the window")

        if gap > 0:
            reasons.append(f"{gap} logbook cases outstanding")

        reasons.append(f"Load {round(load * 100)}%")
        reasons.append(f"Last did this {days_since} days ago") if days_since < 999 else None

        sort_key = (
            cln.tier,                        # 1. Lowest eligible tier (ascending)
            0 if free_count > 0 else 1,      # 2. Free within urgency window (0 is better)
            -gap,                            # 3. Logbook gap (higher gap first)
            load,                            # 4. Lower combined load (ascending)
            -days_since                      # 5. Longest since last case (higher first)
        )

        ranked_list.append({
            "clinician": cln,
            "sort_key": sort_key,
            "free_slots_in_window": free_slots_in_window,
            "load": load,
            "logbook_gap": gap,
            "days_since_last_case": days_since,
            "reason_summary": "; ".join(reasons)
        })

    ranked_list.sort(key=lambda x: x["sort_key"])
    return ranked_list


def calculate_waitlist_priority(case: Case, patient: Patient, ref_date_str: str) -> Tuple[int, int, int]:
    """Waitlist priority (strict order):
    1. Urgency class (urgent=1, soon=2, routine=3)
    2. Days waiting (higher days waiting = lower number = higher priority)
    3. Teaching value (logbook gap, higher gap = higher priority)
    """
    urgency_map = {"emergency": 0, "urgent": 1, "soon": 2, "routine": 3}
    urg_score = urgency_map.get(case.urgency, 3)

    ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")
    try:
        created_dt = datetime.fromisoformat(case.created_at.replace("Z", "+00:00"))
        days_waiting = max(0, (ref_date.date() - created_dt.date()).days)
    except Exception:
        days_waiting = 0

    # Teaching value estimated from complexity & procedures
    teaching_value = len(case.likely_procedures) * 2 + case.complexity

    return (urg_score, -days_waiting, -teaching_value)

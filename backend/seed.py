"""Synthetic seed data for Apollo."""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Any

import random

from models import (
    ClinicSession, appointment_id, case_minutes, slot_when, to_clock, to_minutes,
)
from models import (
    Patient, Availability, Case, Clinician, Slot, Booking, Offer,
    PatientMessage, Event, NeedsAttentionItem, CallRecord, TIER_NAMES,
    DEFAULT_COMPLEXITY_TIERS as COMPLEXITY_MIN_TIER, utc_now_iso
)

BASE_DATE_STR = "2026-11-09"  # Monday


def generate_seed_data() -> Tuple[
    List[Patient],
    List[Case],
    List[Clinician],
    List[Slot],
    List[Booking],
    List[Offer],
    List[PatientMessage],
    List[Event],
    List[NeedsAttentionItem],
    List[CallRecord],
    List[ClinicSession],
]:
    base_dt = datetime.strptime(BASE_DATE_STR, "%Y-%m-%d")

    # 1. Clinicians (14 clinicians across all 5 tiers)
    clinicians = [
        # Tier 1: Year 3 Students (simple restorations, scale & polish, fissure sealants)
        Clinician(
            id="cln-y3-01",
            name="Maya Lin",
            tier=1,
            tier_name=TIER_NAMES[1],
            year=3,
            supervisor_id="cln-qd-01",
            competencies=["Simple restoration", "Scale & polish", "Fissure sealant", "Preventive advice"],
            logbook_targets={"Simple restoration": 10, "Scale & polish": 10, "Fissure sealant": 5},
            logbook_done={"Simple restoration": 4, "Scale & polish": 5, "Fissure sealant": 3},
            sessions=["monday_am", "monday_pm", "tuesday_pm", "thursday_am", "friday_am"],
            status="active",
            last_case_dates={"Simple restoration": "2026-11-04", "Scale & polish": "2026-11-05"},
        ),
        Clinician(
            id="cln-y3-02",
            name="Liam Patel",
            tier=1,
            tier_name=TIER_NAMES[1],
            year=3,
            supervisor_id="cln-qd-01",
            competencies=["Simple restoration", "Scale & polish", "Preventive advice", "Fissure sealant"],
            logbook_targets={"Simple restoration": 10, "Scale & polish": 10, "Fissure sealant": 5},
            logbook_done={"Simple restoration": 7, "Scale & polish": 8, "Fissure sealant": 4},
            sessions=["monday_am", "monday_pm", "wednesday_am", "thursday_pm", "friday_pm"],
            status="active",
            last_case_dates={"Simple restoration": "2026-11-06", "Scale & polish": "2026-11-02"},
        ),
        Clinician(
            id="cln-y3-03",
            name="Sophie Turner",
            tier=1,
            tier_name=TIER_NAMES[1],
            year=3,
            supervisor_id="cln-qd-01",
            competencies=["Simple restoration", "Scale & polish", "Fissure sealant"],
            logbook_targets={"Simple restoration": 10, "Scale & polish": 10},
            logbook_done={"Simple restoration": 3, "Scale & polish": 4},
            sessions=["tuesday_am", "wednesday_pm", "thursday_am"],
            status="active",
            last_case_dates={"Simple restoration": "2026-10-31"},
        ),

        # Tier 2: Year 4 Students (composite restorations, simple extractions, perio scaling)
        Clinician(
            id="cln-y4-01",
            name="Chloe Bennett",
            tier=2,
            tier_name=TIER_NAMES[2],
            year=4,
            supervisor_id="cln-qd-01",
            competencies=["Simple restoration", "Composite restoration", "Simple extraction", "Periodontal scaling", "Temporary crown"],
            logbook_targets={"Composite restoration": 15, "Simple extraction": 8, "Periodontal scaling": 12},
            logbook_done={"Composite restoration": 9, "Simple extraction": 2, "Periodontal scaling": 7},
            sessions=["monday_am", "monday_pm", "tuesday_am", "wednesday_pm", "friday_am"],
            status="active",
            last_case_dates={"Composite restoration": "2026-11-03", "Simple extraction": "2026-10-28"},
        ),
        Clinician(
            id="cln-y4-02",
            name="Tariq Khan",
            tier=2,
            tier_name=TIER_NAMES[2],
            year=4,
            supervisor_id="cln-qd-01",
            competencies=["Simple restoration", "Composite restoration", "Simple extraction", "Periodontal scaling"],
            logbook_targets={"Composite restoration": 15, "Simple extraction": 8, "Periodontal scaling": 12},
            logbook_done={"Composite restoration": 13, "Simple extraction": 6, "Periodontal scaling": 11},
            sessions=["monday_am", "monday_pm", "tuesday_pm", "wednesday_am", "thursday_pm", "friday_am"],
            status="active",
            last_case_dates={"Composite restoration": "2026-11-05", "Simple extraction": "2026-11-01"},
        ),
        Clinician(
            id="cln-y4-03",
            name="Emily Davies",
            tier=2,
            tier_name=TIER_NAMES[2],
            year=4,
            supervisor_id="cln-qd-02",
            competencies=["Simple restoration", "Composite restoration", "Simple extraction", "Periodontal scaling"],
            logbook_targets={"Composite restoration": 15, "Simple extraction": 8, "Periodontal scaling": 12},
            logbook_done={"Composite restoration": 10, "Simple extraction": 3, "Periodontal scaling": 9},
            sessions=["tuesday_am", "wednesday_pm", "thursday_am", "friday_pm"],
            status="active",
            last_case_dates={"Composite restoration": "2026-11-02", "Simple extraction": "2026-10-30"},
        ),

        # Tier 3: Year 5 Students (surgical extractions, anterior endo, crown & bridge, removable prosthetics)
        Clinician(
            id="cln-y5-01",
            name="Aisha Taylor",
            tier=3,
            tier_name=TIER_NAMES[3],
            year=5,
            supervisor_id="cln-qd-02",
            competencies=["Composite restoration", "Simple extraction", "Surgical extraction", "Endodontics - anterior", "Crown & bridge", "Periodontal scaling"],
            logbook_targets={"Endodontics - anterior": 6, "Surgical extraction": 5, "Composite restoration": 15},
            logbook_done={"Endodontics - anterior": 2, "Surgical extraction": 1, "Composite restoration": 14},
            sessions=["monday_am", "tuesday_am", "wednesday_pm", "thursday_am", "friday_pm"],
            status="active",
            last_case_dates={"Endodontics - anterior": "2026-10-20", "Surgical extraction": "2026-10-25"},
        ),
        Clinician(
            id="cln-y5-02",
            name="Marcus Wood",
            tier=3,
            tier_name=TIER_NAMES[3],
            year=5,
            supervisor_id="cln-qd-02",
            competencies=["Composite restoration", "Simple extraction", "Surgical extraction", "Endodontics - anterior", "Crown & bridge", "Removable dentures"],
            logbook_targets={"Endodontics - anterior": 6, "Surgical extraction": 5, "Removable dentures": 4},
            logbook_done={"Endodontics - anterior": 5, "Surgical extraction": 4, "Removable dentures": 3},
            sessions=["monday_am", "monday_pm", "tuesday_pm", "thursday_am", "thursday_pm", "friday_am"],
            status="active",
            last_case_dates={"Endodontics - anterior": "2026-11-02", "Removable dentures": "2026-11-03"},
        ),
        Clinician(
            id="cln-y5-03",
            name="Lucas Brown",
            tier=3,
            tier_name=TIER_NAMES[3],
            year=5,
            supervisor_id="cln-qd-02",
            competencies=["Composite restoration", "Simple extraction", "Surgical extraction", "Endodontics - anterior", "Crown & bridge"],
            logbook_targets={"Endodontics - anterior": 6, "Surgical extraction": 5},
            logbook_done={"Endodontics - anterior": 3, "Surgical extraction": 3},
            sessions=["wednesday_am", "thursday_pm", "friday_am"],
            status="active",
            last_case_dates={"Endodontics - anterior": "2026-10-29"},
        ),

        # Tier 4: Postgraduate Registrars (molar endo, complex perio surgery, trauma)
        Clinician(
            id="cln-pg-01",
            name="Dr. Hannah Clark",
            tier=4,
            tier_name=TIER_NAMES[4],
            year=None,
            supervisor_id="cln-qd-02",
            competencies=["Endodontics - anterior", "Molar root canal", "Surgical extraction", "Complex periodontal surgery", "Trauma management"],
            logbook_targets={"Molar root canal": 8, "Complex periodontal surgery": 6},
            logbook_done={"Molar root canal": 5, "Complex periodontal surgery": 4},
            sessions=["monday_am", "monday_pm", "tuesday_am", "wednesday_am", "thursday_am", "friday_pm"],
            status="active",
            last_case_dates={"Molar root canal": "2026-11-04"},
        ),
        Clinician(
            id="cln-pg-02",
            name="Dr. James Murphy",
            tier=4,
            tier_name=TIER_NAMES[4],
            year=None,
            supervisor_id="cln-qd-01",
            competencies=["Molar root canal", "Surgical extraction", "Complex periodontal surgery", "Fixed prosthodontics"],
            logbook_targets={"Molar root canal": 8, "Surgical extraction": 10},
            logbook_done={"Molar root canal": 6, "Surgical extraction": 8},
            sessions=["tuesday_pm", "wednesday_pm", "friday_am"],
            status="active",
            last_case_dates={"Molar root canal": "2026-11-05"},
        ),

        # Tier 5: Qualified Dentists / Clinical Tutors (all clinical dentistry, supervision)
        Clinician(
            id="cln-qd-01",
            name="Dr. Alistair MacIntyre",
            tier=5,
            tier_name=TIER_NAMES[5],
            year=None,
            supervisor_id=None,
            competencies=["All clinical dentistry", "Oral surgery", "Complex restorative", "Tutor supervision"],
            logbook_targets={},
            logbook_done={},
            sessions=["monday_am", "monday_pm", "tuesday_pm", "wednesday_am", "thursday_pm", "friday_am"],
            status="active",
            last_case_dates={},
        ),
        Clinician(
            id="cln-qd-02",
            name="Dr. Fiona Stewart",
            tier=5,
            tier_name=TIER_NAMES[5],
            year=None,
            supervisor_id=None,
            competencies=["All clinical dentistry", "Endodontics", "Prosthodontics", "Tutor supervision"],
            logbook_targets={},
            logbook_done={},
            sessions=["monday_am", "monday_pm", "tuesday_am", "wednesday_pm", "thursday_am", "friday_am"],
            status="active",
            last_case_dates={},
        ),
        Clinician(
            id="cln-qd-03",
            name="Dr. Rebecca Campbell",
            tier=5,
            tier_name=TIER_NAMES[5],
            year=None,
            supervisor_id=None,
            competencies=["All clinical dentistry", "Emergency dental triage", "Oral surgery", "Tutor supervision"],
            logbook_targets={},
            logbook_done={},
            sessions=["tuesday_am", "wednesday_am", "friday_pm"],
            status="active",
            last_case_dates={},
        ),
    ]

    # 2. Slots for 2 weeks. One clinician per bay per session.
    sessions: List[ClinicSession] = []
    slots: List[Slot] = []
    bays = [f"Bay {i}" for i in range(1, 11)]

    clinician_session_map = {}
    for cln in clinicians:
        for s in cln.sessions:
            clinician_session_map.setdefault(s, []).append(cln)

    for day_offset in range(14):
        slot_date_dt = base_dt + timedelta(days=day_offset)
        # Skip weekends (5=Sat, 6=Sun)
        if slot_date_dt.weekday() >= 5:
            continue

        weekday_name = slot_date_dt.strftime("%A").lower()
        date_str = slot_date_dt.strftime("%Y-%m-%d")

        for session, start_t, end_t in [("AM", "09:00", "12:30"), ("PM", "13:30", "17:00")]:
            session_key = f"{weekday_name}_{session.lower()}"
            available_clinicians = clinician_session_map.get(session_key, [])

            bay_idx = 0
            for cln in available_clinicians:
                bay_name = bays[bay_idx % len(bays)]
                bay_idx += 1
                sessions.append(
                    ClinicSession(
                        id=f"ses-{date_str}-{session.lower()}-{cln.id}",
                        clinician_id=cln.id,
                        bay=bay_name,
                        date=date_str,
                        session=session,
                        start=start_t,
                        end=end_t,
                    )
                )

    patients: List[Patient] = []
    cases: List[Case] = []
    bookings: List[Booking] = []
    offers: List[Offer] = []
    messages: List[PatientMessage] = []
    events: List[Event] = []
    attention_items: List[NeedsAttentionItem] = []
    calls: List[CallRecord] = []

    # Helper function to add a patient and case cleanly
    def add_patient_and_case(
        pid: str,
        name: str,
        phone: str,
        token: str,
        summary_plain: str,
        complaint_quote: str,
        urgency: str,
        complexity: int,
        confidence: str,
        possible_issues: List[str],
        not_ruled_out: List[str],
        likely_procedures: List[str],
        short_notice_ok: bool = True,
        wants_earlier: bool = True,
        flags: List[str] = None,
        status: str = "waitlist",
        case_status: str = "accepted",
        created_days_ago: int = 1,
        dna_count: int = 0,
    ) -> Tuple[Patient, Case]:
        created_dt = base_dt - timedelta(days=created_days_ago, hours=3)
        created_iso = created_dt.isoformat() + "Z"
        req_tier = COMPLEXITY_MIN_TIER.get(complexity, 1)

        pat = Patient(
            id=pid,
            name=name,
            phone=phone,
            contact_token=token,
            short_notice_ok=short_notice_ok,
            wants_earlier=wants_earlier,
            flags=flags or [],
            status=status,
            dna_count=dna_count,
            created_at=created_iso,
        )
        c = Case(
            id=f"case-{pid.replace('pat-', '')}",
            patient_id=pid,
            summary_plain=summary_plain,
            complaint_quote=complaint_quote,
            urgency=urgency,
            complexity=complexity,
            confidence=confidence,
            possible_issues=possible_issues,
            not_ruled_out=not_ruled_out,
            likely_procedures=likely_procedures,
            required_tier=req_tier,
            status=case_status,
            created_at=created_iso,
        )
        patients.append(pat)
        cases.append(c)
        return pat, c

    session_cursor: Dict[str, int] = {}
    rng_times = random.Random(9)

    # Helper function to book a slot
    def create_booking(bkg_id: str, session: ClinicSession, pat: Patient, case: Case, state: str = "confirmed", reason: str = "Lowest eligible grade with a free chair", gap: int = 0):
        """Cut this appointment from the session, after whatever is already booked."""
        start = session_cursor.get(session.id, to_minutes(session.start)) + gap
        end = start + case_minutes(case.likely_procedures)
        if end > to_minutes(session.end):
            return None
        session_cursor[session.id] = end
        slot = Slot(
            id=appointment_id(session.date, to_clock(start), session.clinician_id),
            clinician_id=session.clinician_id, bay=session.bay, date=session.date, session=session.session,
            start=to_clock(start), end=to_clock(end),
        )
        b = Booking(
            id=bkg_id,
            slot_id=slot.id,
            case_id=case.id,
            patient_id=pat.id,
            state=state,
            reason=reason,
            created_by="engine",
            created_at=(base_dt - timedelta(days=2)).isoformat() + "Z",
        )
        slot.booking_id = b.id
        slots.append(slot)
        bookings.append(b)
        if bkg_id != "bkg-001":
            messages.append(PatientMessage(
                id=f"msg-{bkg_id}",
                patient_id=pat.id,
                type="confirmed",
                title="Appointment booked",
                body=f"Booked: {slot_when(slot)}, {slot.bay}. Please arrive 10 minutes early. Reply CANCEL if you can't make it.",
                created_at=(base_dt - timedelta(days=2, hours=rng_times.randint(6, 13), minutes=rng_times.choice([4, 12, 27, 38, 51]))).isoformat() + "Z",
            ))
        return b

    # =========================================================================
    # CORE DEMO PATIENTS (Preserved for Demo Script Flow)
    # =========================================================================

    # Patient 1: Booked Today AM with Chloe Bennett (Year 4)
    p1, c1 = add_patient_and_case(
        "pat-001", "Gordon Findlay", "07700 900101", "tok-gordon",
        "Intermittent sharp pain in lower right premolar upon eating hot foods",
        "I've got a sharp twinge in my lower right back tooth when I drink tea or soup. Started about ten days ago.",
        "routine", 2, "high",
        ["Reversible pulpitis", "Dental caries"],
        ["Periapical periodontitis"],
        ["Composite restoration"],
        status="scheduled", case_status="scheduled", created_days_ago=5
    )
    s_chloe_am = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "AM" and s.clinician_id == "cln-y4-01"), None)
    if s_chloe_am:
        create_booking("bkg-001", s_chloe_am, p1, c1, "confirmed", "Year 4 student needs composite restorations for logbook")
        messages.append(
            PatientMessage(
                id="msg-001",
                patient_id=p1.id,
                type="confirmed",
                title="Appointment confirmed",
                body=f"Booked: today at {s_chloe_am.start} with Chloe Bennett, {s_chloe_am.bay}. Reply CANCEL if you can't make it.",
                created_at=(base_dt - timedelta(days=3)).isoformat() + "Z",
            )
        )

    # Patient 2: Booked Today AM with Maya Lin (Year 3)
    p2, c2 = add_patient_and_case(
        "pat-002", "Hannah MacLeod", "07700 900102", "tok-hannah",
        "Routine checkup request and minor tartar build-up on lower incisors",
        "Haven't seen a dentist in 18 months, just need a checkup and clean.",
        "routine", 1, "high",
        ["Calculus buildup", "Mild gingivitis"],
        [],
        ["Scale & polish"],
        status="scheduled", case_status="scheduled", created_days_ago=6
    )
    s_maya_am = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "AM" and s.clinician_id == "cln-y3-01"), None)
    if s_maya_am:
        create_booking("bkg-002", s_maya_am, p2, c2, "confirmed", "Year 3 student needs scale and polish for logbook")

    # Patient 3: Booked Today AM with Aisha Taylor (Year 5)
    p3, c3 = add_patient_and_case(
        "pat-003", "Robert Kelly", "07700 900103", "tok-robert",
        "Dull persistent throbbing ache upper left canine with heat sensitivity",
        "A dull ache in my front tooth that keeps me awake at night. Feels tender when pressed.",
        "soon", 3, "high",
        ["Irreversible pulpitis", "Periapical periodontitis"],
        [],
        ["Endodontics - anterior"],
        flags=["anxious"],
        status="scheduled", case_status="scheduled", created_days_ago=3
    )
    s_aisha_am = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "AM" and s.clinician_id == "cln-y5-01"), None)
    if s_aisha_am:
        create_booking("bkg-003", s_aisha_am, p3, c3, "confirmed", "Year 5 student needs anterior endodontics for logbook")

    # Patient 4: Booked Today PM with Tariq Khan (Year 4)
    p4, c4 = add_patient_and_case(
        "pat-004", "Jennifer Burns", "07700 900104", "tok-jennifer",
        "Broken cuspal wall on upper right molar after biting on nut",
        "Broke a piece of my molar yesterday, not too painful but sharp edge catches tongue.",
        "soon", 2, "high",
        ["Fractured cusp", "Dentin hypersensitivity"],
        [],
        ["Composite restoration"],
        status="scheduled", case_status="scheduled", created_days_ago=2
    )
    s_tariq_pm = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "PM" and s.clinician_id == "cln-y4-02"), None)
    if s_tariq_pm:
        create_booking("bkg-004", s_tariq_pm, p4, c4, "confirmed", "Lowest eligible grade with a free chair")

    # Standby Pool Candidates (Pre-seeded for judges and live demonstration)
    p_sb1, c_sb1 = add_patient_and_case(
        "pat-sb1", "Elena Rostova", "07700 900201", "tok-elena",
        "Cavity in lower left molar with occasional ache on sweet foods",
        "I have a cavity in my lower left tooth. Sweet things sting for a minute.",
        "routine", 2, "high",
        ["Dental caries", "Reversible pulpitis"],
        [],
        ["Composite restoration"],
        short_notice_ok=True, wants_earlier=True, status="standby", case_status="accepted", created_days_ago=4
    )
    messages.append(
        PatientMessage(
            id="msg-sb1",
            patient_id=p_sb1.id,
            type="joined",
            title="You are on the standby list",
            body="You are on our short-notice standby list. If a chair opens up we will text you here.",
            created_at=p_sb1.created_at,
        )
    )

    p_sb2, c_sb2 = add_patient_and_case(
        "pat-sb2", "David Craig", "07700 900202", "tok-david",
        "Lost filling on lower right first premolar, food packing and mild discomfort",
        "Lost an old filling eating toast last week. Food keeps getting stuck.",
        "routine", 2, "high",
        ["Defective restoration", "Dentin caries"],
        [],
        ["Composite restoration"],
        short_notice_ok=True, wants_earlier=True, status="standby", case_status="accepted", created_days_ago=3
    )
    messages.append(
        PatientMessage(
            id="msg-sb2",
            patient_id=p_sb2.id,
            type="joined",
            title="You are on the standby list",
            body="You are on our short-notice standby list. If a chair opens up we will text you here.",
            created_at=p_sb2.created_at,
        )
    )

    p_sb3, c_sb3 = add_patient_and_case(
        "pat-sb3", "Samuel O'Connor", "07700 900203", "tok-samuel",
        "Loose restoration on upper right premolar with sensitivity to cold drinks",
        "My filling on the top right feels loose and cold water makes it sensitive.",
        "routine", 2, "high",
        ["Leaking restoration", "Thermal sensitivity"],
        [],
        ["Composite restoration"],
        short_notice_ok=True, wants_earlier=True, flags=["interpreter"], status="standby", case_status="accepted", created_days_ago=2
    )
    messages.append(
        PatientMessage(
            id="msg-sb3",
            patient_id=p_sb3.id,
            type="joined",
            title="You are on the standby list",
            body="You are on our short-notice standby list. If a chair opens up we will text you here.",
            created_at=p_sb3.created_at,
        )
    )

    # Core Urgent Trauma Case
    p_urg, c_urg = add_patient_and_case(
        "pat-urg", "Arthur Pendelton", "07700 900301", "tok-arthur",
        "Traumatic incisor crown fracture with exposed bleeding pinpoint and acute pain",
        "I tripped yesterday and chipped my front tooth in half. It is bleeding slightly and throbbing when exposed to air.",
        "urgent", 3, "high",
        ["Complicated crown fracture", "Acute pulpitis"],
        ["Alveolar fracture"],
        ["Endodontics - anterior", "Composite restoration"],
        status="waitlist", case_status="accepted", created_days_ago=0
    )

    # Borderline Tutor Review Case
    p_tutor, c_tutor = add_patient_and_case(
        "pat-tutor", "Gemma Collins", "07700 900302", "tok-gemma",
        "Deep subgingival decay on lower second molar adjacent to inferior alveolar nerve on radiograph history",
        "I have a deep hole in my wisdom tooth area. My dentist told me it was tricky and close to the nerve.",
        "soon", 3, "medium",
        ["Deep carious lesion", "Pulpal involvement"],
        ["Surgical extraction requirement"],
        ["Surgical extraction", "Composite restoration"],
        status="waitlist", case_status="awaiting_tutor", created_days_ago=1
    )
    attention_items.append(
        NeedsAttentionItem(
            id="att-001",
            patient_id=p_tutor.id,
            case_id=c_tutor.id,
            reason="borderline_complexity",
            summary="Deep decay near inferior alveolar nerve. Complexity is borderline between Year 5 and Postgraduate.",
            suggested_action="Tutor to approve for Year 5 or refer to Dr. Clark.",
            created_at=(base_dt - timedelta(hours=4)).isoformat() + "Z",
        )
    )

    # Emergency Red Flag Case
    p_emg, c_emg = add_patient_and_case(
        "pat-emg", "Patrick Campbell", "07700 900303", "tok-patrick",
        "Swelling spreading from the jaw into the neck, with difficulty swallowing",
        "My jaw swelled up huge overnight and now my neck feels tight and I can barely swallow a sip of water.",
        "emergency", 5, "high",
        ["Ludwig's angina / Deep neck space infection"],
        ["Airway compromise"],
        ["Immediate Emergency Department / Maxillofacial Surgery"],
        status="cancelled", case_status="emergency_redirected", created_days_ago=0
    )
    attention_items.append(
        NeedsAttentionItem(
            id="att-002",
            patient_id=p_emg.id,
            case_id=c_emg.id,
            reason="red_flag",
            summary="Spreading neck swelling and difficulty swallowing. Caller was told to go to A&E.",
            suggested_action="Call the patient to check they went to A&E.",
            created_at=(base_dt - timedelta(hours=2)).isoformat() + "Z",
        )
    )

    # Low Confidence / Symptoms Unclear Case
    p_unclear, c_unclear = add_patient_and_case(
        "pat-unclear", "Morag Smith", "07700 900304", "tok-morag",
        "Vague bilateral tingling sensation in lower jaw with no pain, swelling or thermal triggers",
        "My chin feels a bit numb or tingly sometimes when I wake up. Doesn't hurt at all, just strange.",
        "routine", 2, "low",
        ["Atypical facial pain", "Paraesthesia"],
        ["Neurological etiology"],
        ["Clinical assessment by tutor"],
        status="waitlist", case_status="intake_done", created_days_ago=1
    )
    attention_items.append(
        NeedsAttentionItem(
            id="att-003",
            patient_id=p_unclear.id,
            case_id=c_unclear.id,
            reason="symptoms_unclear",
            summary="Non-specific chin tingling with no pain or swelling. Triage confidence is low.",
            suggested_action="Call back to clarify symptoms, or book a short assessment.",
            created_at=(base_dt - timedelta(hours=5)).isoformat() + "Z",
        )
    )

    # =========================================================================
    # ADDITIONAL CLINIC BOOKINGS (Today AM and PM full schedules)
    # =========================================================================

    # Patient 5: Liam Patel Bay 4 AM
    p5, c5 = add_patient_and_case(
        "pat-005", "Sean Ferguson", "07700 900105", "tok-sean",
        "Supragingival calculus buildup on lower anterior teeth with bleeding on brushing",
        "Need a clean and checkup. Gums bleed slightly when brushing.",
        "routine", 1, "high",
        ["Calculus buildup", "Marginal gingivitis"], [], ["Scale & polish"],
        status="scheduled", case_status="scheduled", created_days_ago=4
    )
    s_liam_am = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "AM" and s.clinician_id == "cln-y3-02"), None)
    if s_liam_am:
        create_booking("bkg-005", s_liam_am, p5, c5, "confirmed", "Year 3 scale & polish competency")

    # Patient 6: Marcus Wood Bay 5 AM
    p6, c6 = add_patient_and_case(
        "pat-006", "Fiona Henderson", "07700 900106", "tok-fiona",
        "Review and adjustment of complete acrylic upper removable prosthesis",
        "My upper denture has a sore spot on the gum near the back.",
        "routine", 3, "high",
        ["Denture stomatitis", "Overextended denture border"], [], ["Removable dentures"],
        status="scheduled", case_status="scheduled", created_days_ago=7
    )
    s_marcus_am = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "AM" and s.clinician_id == "cln-y5-02"), None)
    if s_marcus_am:
        create_booking("bkg-006", s_marcus_am, p6, c6, "confirmed", "Year 5 removable prosthetics logbook requirement")

    # Patient 7: Dr. Hannah Clark Bay 6 AM
    p7, c7 = add_patient_and_case(
        "pat-007", "Callum Stewart", "07700 900107", "tok-callum",
        "Lower second molar with irreversible pulpitis requiring curved root canal instrumentation",
        "Severe throbbing in my lower back tooth that radiates to my ear. Keeps me up all night.",
        "soon", 4, "high",
        ["Irreversible pulpitis", "Apical periodontitis"], [], ["Molar root canal"],
        status="scheduled", case_status="scheduled", created_days_ago=3
    )
    s_hannah_am = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "AM" and s.clinician_id == "cln-pg-01"), None)
    if s_hannah_am:
        create_booking("bkg-007", s_hannah_am, p7, c7, "confirmed", "Postgraduate molar endodontics referral")

    # Patient 8: Maya Lin Bay 1 PM
    p8, c8 = add_patient_and_case(
        "pat-008", "Isobel MacIntosh", "07700 900108", "tok-isobel",
        "Preventive resin pit sealant on deep occlusal grooves of first permanent molars",
        "My hygienist recommended sealing the deep grooves on my back teeth.",
        "routine", 1, "high",
        ["High caries risk", "Deep occlusal fissures"], [], ["Fissure sealant", "Simple restoration"],
        status="scheduled", case_status="scheduled", created_days_ago=5
    )
    s_maya_pm = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "PM" and s.clinician_id == "cln-y3-01"), None)
    if s_maya_pm:
        create_booking("bkg-008", s_maya_pm, p8, c8, "confirmed", "Year 3 fissure sealant target gap")

    # Patient 9: Chloe Bennett Bay 3 PM
    p9, c9 = add_patient_and_case(
        "pat-009", "Donald Ross", "07700 900109", "tok-donald",
        "Retained non-restorable root tip upper right premolar requiring forceps extraction",
        "The dentist told me this root stump needs to come out before it gets infected.",
        "routine", 2, "high",
        ["Retained root tip", "Chronic apical periodontitis"], [], ["Simple extraction"],
        status="scheduled", case_status="scheduled", created_days_ago=6
    )
    s_chloe_pm = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "PM" and s.clinician_id == "cln-y4-01"), None)
    if s_chloe_pm:
        create_booking("bkg-009", s_chloe_pm, p9, c9, "confirmed", "Year 4 simple extraction logbook target")

    # Patient 10: Dr. Alistair MacIntyre Bay 5 PM
    p10, c10 = add_patient_and_case(
        "pat-010", "Craig Wallace", "07700 900110", "tok-craig",
        "Consultant complex case review for multiple heavily restored broken teeth and bite rehabilitation",
        "My teeth have worn down flat over the years and several crowns have broken.",
        "routine", 5, "high",
        ["Severe tooth surface loss", "Reduced vertical dimension"], [], ["Complex restorative", "All clinical dentistry"],
        status="scheduled", case_status="scheduled", created_days_ago=8
    )
    s_alistair_pm = next((s for s in sessions if s.date == BASE_DATE_STR and s.session == "PM" and s.clinician_id == "cln-qd-01"), None)
    if s_alistair_pm:
        create_booking("bkg-010", s_alistair_pm, p10, c10, "confirmed", "Senior clinical tutor consultation")

    # =========================================================================
    # MORE STANDBY POOL CANDIDATES (Various procedures)
    # =========================================================================
    p_sb4, c_sb4 = add_patient_and_case(
        "pat-sb4", "Nathan Graham", "07700 900204", "tok-nathan",
        "Heavy tartar buildup on lingual incisors, flexible availability for hygiene",
        "I work five minutes away and can come in on 30 minutes notice for a clean.",
        "routine", 1, "high",
        ["Calculus buildup", "Mild gingivitis"], [], ["Scale & polish"],
        short_notice_ok=True, wants_earlier=True, status="standby", case_status="accepted", created_days_ago=4
    )
    p_sb5, c_sb5 = add_patient_and_case(
        "pat-sb5", "Grace Montgomery", "07700 900205", "tok-grace",
        "Chipped buccal cusp on lower right molar, standby for restorative session",
        "Broke a corner off my filling. Can arrive anytime if a chair frees up.",
        "routine", 2, "high",
        ["Defective restoration", "Carious lesion"], [], ["Composite restoration"],
        short_notice_ok=True, wants_earlier=True, status="standby", case_status="accepted", created_days_ago=3
    )
    p_sb6, c_sb6 = add_patient_and_case(
        "pat-sb6", "Euan Sinclair", "07700 900206", "tok-euan",
        "Firm mobile lower incisor with severe localized bone loss",
        "Front tooth is loose and tender when biting toast. Ready to come in today.",
        "soon", 2, "high",
        ["Localized severe periodontitis", "Tooth mobility class III"], [], ["Simple extraction"],
        short_notice_ok=True, wants_earlier=True, status="standby", case_status="accepted", created_days_ago=2
    )
    p_sb7, c_sb7 = add_patient_and_case(
        "pat-sb7", "Kirsty Hamilton", "07700 900207", "tok-kirsty",
        "Aesthetic composite filling replacement on upper lateral incisor",
        "Old white filling on my front tooth has turned brown and rough.",
        "routine", 2, "high",
        ["Stained composite restoration", "Marginal ditching"], [], ["Composite restoration"],
        short_notice_ok=True, wants_earlier=True, flags=["anxious"], status="standby", case_status="accepted", created_days_ago=5
    )
    p_sb8, c_sb8 = add_patient_and_case(
        "pat-sb8", "Angus Macdonald", "07700 900208", "tok-angus",
        "Loose lower partial cobalt-chrome denture clasp",
        "Metal clip on my partial plate is loose. Can attend at short notice.",
        "routine", 3, "high",
        ["Deformed clasp assembly", "Partial denture instability"], [], ["Removable dentures"],
        short_notice_ok=True, wants_earlier=True, status="standby", case_status="accepted", created_days_ago=6
    )

    # =========================================================================
    # EXTENSIVE WAITLIST PATIENTS (Across stages, tiers, and conditions)
    # =========================================================================
    waitlist_specs = [
        ("pat-wl01", "Alistair Boyd", "07700 900401", "tok-wl01", "Failing MOD amalgam restoration on lower right molar", "Old silver filling is crumbling and food collects between teeth.", "routine", 2, "high", ["Recurrent caries", "Defective amalgam"], [], ["Composite restoration"], ["access_needs"], 9),
        ("pat-wl02", "Catriona Morrison", "07700 900402", "tok-wl02", "Sharp sensitivity to cold air and chilled water on upper left premolar", "Cold drinks give me a sharp jolt of pain that goes away after ten seconds.", "soon", 2, "high", ["Reversible pulpitis", "Cervical abrasion"], [], ["Composite restoration"], [], 3),
        ("pat-wl03", "Douglas Fraser", "07700 900403", "tok-wl03", "Generalized gingival bleeding and calculus deposits", "My gums bleed every time I brush and floss.", "routine", 1, "high", ["Chronic gingivitis", "Calculus accumulation"], [], ["Scale & polish"], [], 8),
        ("pat-wl04", "Lorna Robertson", "07700 900404", "tok-wl04", "Partially erupted lower left wisdom tooth with recurrent pericoronal soreness", "Gum flap over my back tooth gets inflamed every few weeks.", "soon", 3, "medium", ["Pericoronitis", "Impacted third molar"], ["Deep fascial infection"], ["Surgical extraction"], [], 4),
        ("pat-wl05", "Hamish Murray", "07700 900405", "tok-wl05", "Discoloured non-vital upper central incisor following sports trauma 2 years ago", "Front tooth has turned grey. Dentist said the nerve died after a rugby tackle.", "routine", 3, "high", ["Pulpal necrosis", "Tooth discolouration"], [], ["Endodontics - anterior", "Composite restoration"], [], 7),
        ("pat-wl06", "Mhairi Cameron", "07700 900406", "tok-wl06", "Debonded lingual orthodontic retainer wire scratching tongue", "The wire behind my bottom front teeth popped off and is poking my tongue.", "urgent", 2, "high", ["Debonded orthodontic retainer", "Mucosal irritation"], [], ["Composite restoration"], [], 1),
        ("pat-wl07", "Stuart Kerr", "07700 900407", "tok-wl07", "Xerostomia dry mouth sensation with generalized plaque", "My mouth feels constantly dry due to medication and I need a checkup.", "routine", 1, "high", ["Drug-induced xerostomia", "Plaque accumulation"], [], ["Scale & polish", "Preventive advice"], [], 5),
        ("pat-wl08", "Alison Thomson", "07700 900408", "tok-wl08", "Deep occlusal pit decay on upper premolar detected on routine screening", "Dentist spotted a deep cavity during a screening session.", "routine", 2, "high", ["Dental caries occlusal", "Dentin caries"], [], ["Composite restoration"], [], 6),
        ("pat-wl09", "Blair Paterson", "07700 900409", "tok-wl09", "Mild painless clicking in right temporomandibular joint on opening", "My jaw clicks when I open wide to yawn. No pain at all.", "routine", 2, "low", ["Temporomandibular joint internal derangement"], [], ["Clinical assessment by tutor"], [], 4),
        ("pat-wl10", "Gillian Vance", "07700 900410", "tok-wl10", "Cervical dentin hypersensitivity at gingival margin of lower canines", "Brushing the necks of my teeth feels very sensitive.", "routine", 1, "high", ["Dentin hypersensitivity", "Gingival recession"], [], ["Preventive advice", "Fissure sealant"], [], 10),
        ("pat-wl11", "Keith McInnes", "07700 900411", "tok-wl11", "Unrestored palatal cusp fracture on upper first molar", "Lost a piece of tooth chewing a crusty roll. Edge is sharp.", "soon", 2, "high", ["Fractured cusp", "Exposed dentin"], [], ["Composite restoration"], [], 2),
        ("pat-wl12", "Shona Macrae", "07700 900412", "tok-wl12", "Upper acrylic denture dropping when talking or laughing", "Dentures have become very loose over the past six months.", "routine", 3, "high", ["Alveolar ridge resorption", "Loss of denture retention"], [], ["Removable dentures"], [], 12),
        ("pat-wl13", "Neil Armstrong", "07700 900413", "tok-wl13", "Subgingival calculus bridge behind lower anterior incisors", "Haven't had a dental clean in three years, lots of hard tartar.", "routine", 1, "high", ["Severe calculus accumulation", "Gingivitis"], [], ["Scale & polish"], [], 8),
        ("pat-wl14", "Morven Clark", "07700 900414", "tok-wl14", "Spontaneous throbbing pain in upper left first molar keeping patient awake", "Severe aching tooth pain at 3 AM that needed painkillers.", "urgent", 3, "high", ["Acute irreversible pulpitis"], ["Acute apical abscess"], ["Endodontics - anterior", "Composite restoration"], [], 1),
        ("pat-wl15", "Duncan Gillespie", "07700 900415", "tok-wl15", "Extreme dental anxiety, hasn't visited a dental surgery in 6 years", "Terrified of dental drills and needles. Need a gentle checkup.", "routine", 1, "high", ["Dental phobia", "Calculus accumulation"], [], ["Scale & polish", "Preventive advice"], ["anxious"], 14),
        ("pat-wl16", "Lesley Cunningham", "07700 900416", "tok-wl16", "Subgingival fracture on heavily restored root-treated premolar", "My root-treated tooth split down the side. Wondering if it can be saved.", "soon", 3, "medium", ["Vertical root fracture risk", "Defective coronal seal"], ["Non-restorable fracture"], ["Surgical extraction", "Composite restoration"], [], 3),
        ("pat-wl17", "Malcolm Scott", "07700 900417", "tok-wl17", "Extrinsic chlorhexidine and nicotine staining on anterior teeth", "Lots of dark brown stains on the front teeth.", "routine", 1, "high", ["Extrinsic dental staining"], [], ["Scale & polish"], [], 7),
        ("pat-wl18", "Iona Sutherland", "07700 900418", "tok-wl18", "Palatally impacted upper canine requiring surgical exposure assessment", "Orthodontist referred me to check if my impacted canine can be brought down.", "routine", 4, "high", ["Impacted maxillary canine"], [], ["Surgical extraction", "Complex periodontal surgery"], [], 11),
        ("pat-wl19", "Ross Macfarlane", "07700 900419", "tok-wl19", "Sharp fractured composite edge causing traumatic ulcer on lateral tongue", "Filling chipped and the rough spot is rubbing my tongue raw.", "routine", 2, "high", ["Traumatic lingual ulcer", "Fractured restoration"], [], ["Composite restoration"], [], 5),
        ("pat-wl20", "Aileen Baird", "07700 900420", "tok-wl20", "Margin gap and cement wash-out under full gold crown on upper second molar", "Old gold crown feels loose and food catches underneath.", "routine", 3, "high", ["Recurrent marginal caries", "Decemented crown"], [], ["Crown & bridge", "Composite restoration"], [], 9),
        ("pat-wl21", "Kenneth Ross", "07700 900421", "tok-wl21", "Post-stroke patient requiring wheelchair hoist / wide bay access for exam", "Wheelchair user following stroke. Needs wide chair transfer space.", "routine", 2, "high", ["Post-stroke oral care", "Gingival recession"], [], ["Scale & polish", "Composite restoration"], ["wheelchair", "access_needs"], 13),
        ("pat-wl22", "Heather Maclean", "07700 900422", "tok-wl22", "Annual volunteer clinic recall checkup and bite-wing review", "Volunteer patient here for my annual checkup and cleaning.", "routine", 1, "high", ["Routine dental checkup"], [], ["Scale & polish"], [], 6),
        ("pat-wl23", "Alan Fleming", "07700 900423", "tok-wl23", "Interproximal cavity between upper canine and first premolar", "Floss catches and tears between my top teeth.", "routine", 2, "high", ["Interproximal carious lesion"], [], ["Composite restoration"], [], 4),
        ("pat-wl24", "Christine Drummond", "07700 900424", "tok-wl24", "Porcelain fused to metal crown debonded cleanly while eating toffee", "My front crown fell off in one piece. I have it with me in a box.", "urgent", 2, "high", ["Decemented crown", "Exposed dentin core"], [], ["Composite restoration", "Crown & bridge"], [], 1),
        ("pat-wl25", "Fraser Macleod", "07700 900425", "tok-wl25", "Bilateral buccal abfraction notches with thermal sensitivity", "Notches at the gumline on my premolars feel cold and sore.", "routine", 2, "high", ["Abfraction lesions", "Cervical sensitivity"], [], ["Composite restoration"], [], 5),
    ]

    for pid, name, phone, token, summary, quote, urg, comp, conf, issues, nro, procs, flags, days_ago in waitlist_specs:
        add_patient_and_case(
            pid, name, phone, token, summary, quote, urg, comp, conf, issues, nro, procs,
            short_notice_ok=(comp <= 2 and urg != "urgent"),
            wants_earlier=True,
            flags=flags,
            status="waitlist",
            case_status="accepted" if comp != 3 or urg != "soon" else "awaiting_tutor",
            created_days_ago=days_ago,
        )

    # Additional Emergency & Human-in-the-loop Cases
    p_emg2, c_emg2 = add_patient_and_case(
        "pat-emg2", "Derek Buchanan", "07700 900305", "tok-derek",
        "Continuous oozing and active arterial bleeding 6 hours after molar extraction elsewhere",
        "Had a tooth pulled at a private clinic at 2 PM. It won't stop bleeding, mouth filling with blood.",
        "emergency", 5, "high",
        ["Secondary post-extraction hemorrhage"], ["Coagulopathy"], ["Emergency Department / Oral Surgery"],
        status="cancelled", case_status="emergency_redirected", created_days_ago=0
    )
    attention_items.append(
        NeedsAttentionItem(
            id="att-004",
            patient_id=p_emg2.id,
            case_id=c_emg2.id,
            reason="red_flag",
            summary="Uncontrolled bleeding after an extraction. Caller was told to go to A&E.",
            suggested_action="Call the patient to check they went to A&E.",
            created_at=(base_dt - timedelta(hours=3, minutes=15)).isoformat() + "Z",
        )
    )

    p_emg3, c_emg3 = add_patient_and_case(
        "pat-emg3", "Margaret MacPherson", "07700 900306", "tok-margaret",
        "Facial trauma from cycling fall with severe malocclusion and numbness in lower lip",
        "Fell off my bike this morning. Jaw hit the tarmac and now my teeth don't meet and lip is numb.",
        "emergency", 5, "high",
        ["Mandibular fracture", "Inferior alveolar nerve injury"], ["Facial bone displacement"], ["Emergency Maxillofacial Unit"],
        status="cancelled", case_status="emergency_redirected", created_days_ago=0
    )
    attention_items.append(
        NeedsAttentionItem(
            id="att-005",
            patient_id=p_emg3.id,
            case_id=c_emg3.id,
            reason="red_flag",
            summary="Facial injury with a suspected jaw fracture. Caller was told to go to A&E.",
            suggested_action="Call the patient to check they went to A&E.",
            created_at=(base_dt - timedelta(hours=1, minutes=30)).isoformat() + "Z",
        )
    )

    p_att_pers, c_att_pers = add_patient_and_case(
        "pat-att1", "Siobhan Kelly", "07700 900307", "tok-siobhan",
        "Patient repeatedly requested to speak to a human receptionist during automated voice intake",
        "I want to speak with a real person please. Can someone call me back?",
        "routine", 2, "high",
        ["Routine dental inquiry"], [], ["Clinical assessment by tutor"],
        status="waitlist", case_status="intake_done", created_days_ago=1
    )
    attention_items.append(
        NeedsAttentionItem(
            id="att-006",
            patient_id=p_att_pers.id,
            case_id=c_att_pers.id,
            reason="asked_for_person",
            summary="Caller asked to speak to a person.",
            suggested_action="Call back to complete the booking.",
            created_at=(base_dt - timedelta(hours=6)).isoformat() + "Z",
        )
    )

    p_att_low, c_att_low = add_patient_and_case(
        "pat-att2", "Liam Gallagher", "07700 900308", "tok-liam",
        "Unexplained metallic taste and unilateral tongue tingling without apparent mucosal lesion",
        "Tongue feels strange and tastes metallic on the right side. No tooth pain.",
        "routine", 2, "low",
        ["Dysgeusia", "Neuropathic oral dysesthesia"], ["Oral pathology"], ["Clinical assessment by tutor"],
        status="waitlist", case_status="intake_done", created_days_ago=2
    )
    attention_items.append(
        NeedsAttentionItem(
            id="att-007",
            patient_id=p_att_low.id,
            case_id=c_att_low.id,
            reason="low_confidence",
            summary="Symptoms do not point to a dental cause. Triage confidence is low.",
            suggested_action="Book a short assessment with a tutor.",
            created_at=(base_dt - timedelta(hours=7)).isoformat() + "Z",
        )
    )

    # =========================================================================
    # EXTENSIVE OVERNIGHT CALLS (10+ realistic records)
    # =========================================================================
    calls.extend([
        CallRecord(
            id="call-001",
            patient_id=p_emg.id,
            direction="inbound",
            outcome="emergency_redirected",
            transcript=[
                {"speaker": "agent", "text": "You're through to Apollo. How can we help today?", "t": 1.2},
                {"speaker": "patient", "text": "My jaw is swollen and the swelling is spreading into my neck. I can't swallow.", "t": 6.8},
                {"speaker": "agent", "text": "Please seek immediate emergency medical care. Go straight to A&E or call 999. We cannot treat this at the volunteer student clinic.", "t": 14.5},
            ],
            summary="Neck swelling and difficulty swallowing. Told to go to A&E.",
            started_at=(base_dt - timedelta(hours=5, minutes=12)).isoformat() + "Z",
            ended_at=(base_dt - timedelta(hours=5, minutes=10)).isoformat() + "Z",
        ),
        CallRecord(
            id="call-002",
            patient_id=p_urg.id,
            direction="inbound",
            outcome="intake_completed",
            transcript=[
                {"speaker": "agent", "text": "You're through to Apollo. How can we help today?", "t": 1.0},
                {"speaker": "patient", "text": "I tripped and fractured my front tooth. It's bleeding and hurts very badly.", "t": 7.3},
                {"speaker": "agent", "text": "Understood. No swelling to the eyes or neck? Any breathing difficulty?", "t": 13.0},
                {"speaker": "patient", "text": "No breathing trouble, just severe sharp tooth pain and bleeding.", "t": 18.2},
                {"speaker": "agent", "text": "Thank you. We have recorded your intake as urgent. You will receive an appointment offer within 30 minutes.", "t": 25.0},
            ],
            summary="Fractured front tooth with bleeding. Needs seeing within 48 hours.",
            started_at=(base_dt - timedelta(hours=3, minutes=45)).isoformat() + "Z",
            ended_at=(base_dt - timedelta(hours=3, minutes=41)).isoformat() + "Z",
        ),
        CallRecord(
            id="call-003",
            patient_id=p_tutor.id,
            direction="inbound",
            outcome="intake_completed",
            transcript=[
                {"speaker": "agent", "text": "You're through to Apollo. How can we help today?", "t": 1.5},
                {"speaker": "patient", "text": "I have deep decay at the back of my mouth. Dentist said it was tricky and close to the nerve.", "t": 8.0},
                {"speaker": "agent", "text": "Recorded. We have queued your details for tutor review.", "t": 16.0},
            ],
            summary="Deep decay at the back of the mouth. Waiting for tutor review.",
            started_at=(base_dt - timedelta(hours=4, minutes=10)).isoformat() + "Z",
            ended_at=(base_dt - timedelta(hours=4, minutes=7)).isoformat() + "Z",
        ),
        CallRecord(
            id="call-004",
            patient_id=p_unclear.id,
            direction="inbound",
            outcome="intake_completed",
            transcript=[
                {"speaker": "agent", "text": "You're through to Apollo. How can we help today?", "t": 1.0},
                {"speaker": "patient", "text": "My chin tingles a bit in the morning.", "t": 5.0},
                {"speaker": "agent", "text": "Any pain or swelling?", "t": 9.0},
                {"speaker": "patient", "text": "No, neither.", "t": 12.0},
            ],
            summary="Occasional chin tingling, no pain or swelling. Symptoms unclear.",
            started_at=(base_dt - timedelta(hours=6, minutes=20)).isoformat() + "Z",
            ended_at=(base_dt - timedelta(hours=6, minutes=17)).isoformat() + "Z",
        ),
        CallRecord(
            id="call-005",
            patient_id=p_emg2.id,
            direction="inbound",
            outcome="emergency_redirected",
            transcript=[
                {"speaker": "agent", "text": "You're through to Apollo. How can we help today?", "t": 1.0},
                {"speaker": "patient", "text": "I had a tooth pulled this afternoon and it won't stop bleeding. Mouth is full of blood clots.", "t": 6.5},
                {"speaker": "agent", "text": "Bite firmly on a clean folded cloth and go straight to A&E.", "t": 14.0},
            ],
            summary="Heavy bleeding after an extraction. Told to go to A&E.",
            started_at=(base_dt - timedelta(hours=3, minutes=16)).isoformat() + "Z",
            ended_at=(base_dt - timedelta(hours=3, minutes=14)).isoformat() + "Z",
        ),
        CallRecord(
            id="call-006",
            patient_id=p_emg3.id,
            direction="inbound",
            outcome="emergency_redirected",
            transcript=[
                {"speaker": "agent", "text": "You're through to Apollo. How can we help today?", "t": 1.0},
                {"speaker": "patient", "text": "I came off my road bike and hit my jaw hard on the road. My bite feels crooked and lip is completely numb.", "t": 7.0},
                {"speaker": "agent", "text": "That indicates a possible jaw fracture. Please attend the nearest Emergency Department immediately for maxillofacial assessment.", "t": 15.0},
            ],
            summary="Suspected jaw fracture after a cycling fall. Told to go to A&E.",
            started_at=(base_dt - timedelta(hours=1, minutes=32)).isoformat() + "Z",
            ended_at=(base_dt - timedelta(hours=1, minutes=29)).isoformat() + "Z",
        ),
        CallRecord(
            id="call-007",
            patient_id=p_att_pers.id,
            direction="inbound",
            outcome="escalated",
            transcript=[
                {"speaker": "agent", "text": "You're through to Apollo. How can we help today?", "t": 1.0},
                {"speaker": "patient", "text": "I do not want to talk to an automated machine. I want to speak with a human receptionist right now.", "t": 6.0},
                {"speaker": "agent", "text": "I understand. I am escalating your request directly to our reception staff queue for a prompt callback.", "t": 12.0},
            ],
            summary="Caller asked to speak to a person. Passed to reception.",
            started_at=(base_dt - timedelta(hours=6, minutes=5)).isoformat() + "Z",
            ended_at=(base_dt - timedelta(hours=6, minutes=3)).isoformat() + "Z",
        ),
        CallRecord(
            id="call-008",
            patient_id=p_sb1.id,
            direction="inbound",
            outcome="intake_completed",
            transcript=[
                {"speaker": "agent", "text": "You're through to Apollo. How can we help today?", "t": 1.0},
                {"speaker": "patient", "text": "I have a small cavity in my lower tooth that needs a white filling. I live nearby and can come on short notice.", "t": 7.5},
                {"speaker": "agent", "text": "Thank you Elena. You are now on our standby list.", "t": 15.0},
            ],
            summary="Added to the standby list.",
            started_at=(base_dt - timedelta(days=4, hours=2)).isoformat() + "Z",
            ended_at=(base_dt - timedelta(days=4, hours=1, minutes=57)).isoformat() + "Z",
        ),
    ])

    # =========================================================================
    # DETAILED AUDIT TRAIL EVENTS
    # =========================================================================
    events.extend([
        Event(
            id="evt-001",
            at=(base_dt - timedelta(hours=5, minutes=10)).isoformat() + "Z",
            actor="Automated line",
            type="emergency_redirected",
            entity="patient",
            payload={"patient_id": p_emg.id, "case_id": c_emg.id, "red_flag": "spreading neck swelling"},
            reason="Neck swelling and difficulty swallowing. Patient instructed to attend A&E.",
        ),
        Event(
            id="evt-002",
            at=(base_dt - timedelta(hours=3, minutes=41)).isoformat() + "Z",
            actor="Automated line",
            type="intake_created",
            entity="case",
            payload={"patient_id": p_urg.id, "case_id": c_urg.id, "urgency": "urgent"},
            reason="Fractured tooth triaged as urgent (needs care within 48h).",
        ),
        Event(
            id="evt-003",
            at=(base_dt - timedelta(days=3)).isoformat() + "Z",
            actor="System",
            type="booking_confirmed",
            entity="booking",
            payload={"booking_id": "bkg-001", "slot_id": s_chloe_am.id if s_chloe_am else "", "patient_id": p1.id},
            reason="Booked with Chloe Bennett (Year 4).",
        ),
        Event(
            id="evt-004",
            at=(base_dt - timedelta(days=2)).isoformat() + "Z",
            actor="System",
            type="booking_confirmed",
            entity="booking",
            payload={"booking_id": "bkg-003", "slot_id": s_aisha_am.id if s_aisha_am else "", "patient_id": p3.id},
            reason="Booked with Aisha Taylor (Year 5).",
        ),
        Event(
            id="evt-005",
            at=(base_dt - timedelta(hours=3, minutes=14)).isoformat() + "Z",
            actor="Automated line",
            type="emergency_redirected",
            entity="patient",
            payload={"patient_id": p_emg2.id, "red_flag": "uncontrolled bleeding"},
            reason="Heavy bleeding after an extraction. Patient told to attend A&E.",
        ),
        Event(
            id="evt-006",
            at=(base_dt - timedelta(hours=1, minutes=29)).isoformat() + "Z",
            actor="Automated line",
            type="emergency_redirected",
            entity="patient",
            payload={"patient_id": p_emg3.id, "red_flag": "facial trauma / numbness"},
            reason="Suspected jaw fracture. Patient told to attend A&E.",
        ),
        Event(
            id="evt-007",
            at=(base_dt - timedelta(days=1)).isoformat() + "Z",
            actor="Dr. Alistair MacIntyre",
            type="triage_reviewed",
            entity="case",
            payload={"case_id": c_tutor.id, "decision": "under_review"},
            reason="Tutor reviewing a borderline case.",
        ),
    ])

    # A working clinic: dense today, thinning out through the week, with uneven gaps.
    rng = random.Random(26)
    first_names = ["Ailsa", "Angus", "Beth", "Calum", "Cara", "Colin", "Dawn", "Eilidh", "Erin", "Finlay", "Gavin", "Greer",
                   "Ian", "Jean", "Joan", "Kyle", "Lewis", "Lynn", "Mairi", "Murray", "Nora", "Owen", "Rhona", "Rowan",
                   "Stuart", "Tess", "Una", "Wendy"]
    last_names = ["Aitken", "Baxter", "Cairns", "Dunlop", "Ewing", "Forsyth", "Geddes", "Hogg", "Irvine", "Kerr", "Lamont",
                  "Mackie", "Nairn", "Ogilvie", "Pollock", "Rennie", "Shaw", "Tait", "Urquhart", "Wallace", "Young"]
    names = [f"{first} {last}" for first in first_names for last in last_names]
    rng.shuffle(names)
    senior_work = ["Crown & bridge", "Complex restorative", "Molar root canal", "Surgical extraction"]
    visit_notes = {
        "Preventive advice": "Advice on brushing and diet",
        "Scale & polish": "Routine clean",
        "Fissure sealant": "Sealant on back teeth",
        "Simple restoration": "Small filling",
        "Simple extraction": "Loose tooth to remove",
        "Periodontal scaling": "Gum treatment, next visit",
        "Composite restoration": "White filling",
        "Temporary crown": "Temporary crown fitting",
        "Removable dentures": "Denture fitting",
        "Trauma management": "Follow-up after a tooth injury",
        "Surgical extraction": "Tooth removal under local anaesthetic",
        "Endodontics - anterior": "Root canal on a front tooth",
        "Molar root canal": "Root canal on a back tooth",
        "Crown & bridge": "Crown preparation",
        "Complex periodontal surgery": "Gum surgery",
        "Complex restorative": "Bridge work",
    }
    fill_by_day = [0.85, 0.6, 0.4, 0.25, 0.15]
    clinic_days = sorted({s.date for s in sessions})[:len(fill_by_day)]
    tier_of = {c.id: c for c in clinicians}
    number = 0
    for day, fill in zip(clinic_days, fill_by_day):
        for session in (s for s in sessions if s.date == day):
            clinician = tier_of[session.clinician_id]
            pool = [p for p in clinician.competencies if p in visit_notes] or senior_work
            while True:
                gap = rng.choice([0, 0, 0, 15, 15, 30, 45])
                procedure = rng.choice(pool)
                if session_cursor.get(session.id, to_minutes(session.start)) + gap + case_minutes([procedure]) > to_minutes(session.end):
                    break
                if rng.random() > fill:
                    session_cursor[session.id] = session_cursor.get(session.id, to_minutes(session.start)) + 30
                    continue
                number += 1
                name = names.pop()
                pat, case = add_patient_and_case(
                    f"pat-c{number:03d}", name, f"07700 91{number:04d}", f"tok-c{number:03d}",
                    visit_notes[procedure], "Booked at the clinic for ongoing treatment.",
                    "routine", min(clinician.tier, 3), "high", [], [], [procedure],
                    short_notice_ok=False, wants_earlier=False, status="scheduled", case_status="scheduled",
                    created_days_ago=rng.randint(3, 20),
                )
                create_booking(f"bkg-c{number:03d}", session, pat, case, "confirmed", "Booked at the clinic", gap=gap)

    return patients, cases, clinicians, slots, bookings, offers, messages, events, attention_items, calls, sessions

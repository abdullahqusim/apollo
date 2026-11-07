"""Intake must keep what the voice script collects. Run: python -m unittest discover backend"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient
from pydantic import ValidationError

import pipeline
import state
from intake_parsing import parse_dob, read_history
from main import app
from models import MedicalHistory
from state import STATE
from triage import Assessment, has_red_flag

client = TestClient(app)

ROUTINE_PROBLEM = "My name is Rory Sinclair. I lost a filling and cold drinks hurt."
DOB_QUESTION = "Please may I have your date of birth."
HISTORY_QUESTION = "Do you have any known conditions, allergies or take any regular medications?"


def agent(text):
    return {"speaker": "agent", "text": text}


def caller(text):
    return {"speaker": "patient", "text": text}


class IntakeTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        snapshot = patch.object(state, "SNAPSHOT_FILE", os.path.join(folder.name, "state.json"))
        snapshot.start()
        self.addCleanup(snapshot.stop)
        STATE.reset_demo(save=False)
        self.calls = 0

    def call(self, *lines, **fields):
        self.calls += 1
        body = {"call_id": f"test-{self.calls}", "caller_phone": f"07700 900{self.calls:03d}", "transcript": list(lines)}
        response = client.post("/webhooks/call-ended", json={**body, **fields})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def routine_call(self, *extra, **fields):
        return self.call(caller(ROUTINE_PROBLEM), *extra, **fields)

    def flags(self, case_id):
        return [item.reason for item in STATE.needs_attention.values() if item.case_id == case_id]

    def active_bookings(self, patient_id):
        return [b for b in STATE.bookings.values() if b.patient_id == patient_id and b.state != "cancelled"]


class DateOfBirth(IntakeTest):
    def test_reads_common_spoken_and_written_forms(self):
        for said in ("3rd of March 1985", "the third of March, 1985", "March 3rd 1985", "03/03/1985", "3 Mar 1985"):
            self.assertEqual(parse_dob(said), "1985-03-03", said)
        self.assertEqual(parse_dob("twenty-first of June 1990"), "1990-06-21")

    def test_slashed_dates_are_day_first(self):
        self.assertEqual(parse_dob("02/11/1970"), "1970-11-02")

    def test_keeps_the_caller_words_when_it_cannot_read_a_date(self):
        self.assertEqual(parse_dob("nineteen eighty five I think."), "nineteen eighty five I think")
        self.assertEqual(parse_dob("31/02/1985"), "31/02/1985")
        self.assertEqual(parse_dob("01/01/2999"), "01/01/2999")

    def test_call_stores_date_from_transcript(self):
        result = self.routine_call(agent(DOB_QUESTION), caller("It's the 3rd of March 1985."))
        self.assertEqual(STATE.patients[result["patient_id"]].date_of_birth, "1985-03-03")

    def test_field_from_the_agent_wins_over_transcript(self):
        result = self.routine_call(agent(DOB_QUESTION), caller("1st of May 1970"), caller_dob="02/02/1990")
        self.assertEqual(STATE.patients[result["patient_id"]].date_of_birth, "1990-02-02")

    def test_returning_caller_gains_a_date_of_birth(self):
        first = self.routine_call(caller_phone="07700 900999")
        self.assertIsNone(STATE.patients[first["patient_id"]].date_of_birth)
        second = self.routine_call(caller_phone="07700 900999", caller_dob="02/02/1990")
        self.assertEqual(second["outcome"], "updated")
        self.assertEqual(STATE.patients[first["patient_id"]].date_of_birth, "1990-02-02")

    def test_online_form_stores_it(self):
        response = client.post("/api/patient/register", json={
            "name": "Ada Fox", "phone": "07700 900500", "problem": "I lost a filling", "date_of_birth": "1985-03-03",
        })
        self.assertEqual(STATE.patients[response.json()["patient_id"]].date_of_birth, "1985-03-03")

    def test_voice_tool_stores_it(self):
        response = client.post("/api/tools/create_intake", json={
            "name": "Ada Fox", "phone": "07700 900501", "dob": "03/03/1985",
        })
        self.assertEqual(STATE.patients[response.json()["patient_id"]].date_of_birth, "1985-03-03")


class MedicalHistoryFields(IntakeTest):
    def read(self, reply):
        return read_history(f"agent: {HISTORY_QUESTION}\npatient: {reply}\nagent: Thanks.")

    def test_splits_one_answer_into_three_fields(self):
        history = self.read("Yes, I've got asthma, I'm allergic to penicillin and I take ibuprofen.")
        self.assertEqual(history.conditions, ["asthma"])
        self.assertEqual(history.allergies, ["penicillin"])
        self.assertEqual(history.medications, ["ibuprofen"])

    def test_a_list_stays_in_the_same_field(self):
        self.assertEqual(self.read("I take metformin and ramipril").medications, ["metformin", "ramipril"])

    def test_nothing_to_report_is_not_the_same_as_never_asked(self):
        self.assertEqual(self.read("No, none of those."), MedicalHistory(conditions=[], allergies=[], medications=[], declined=False))
        self.assertIsNone(read_history("agent: What's the problem?\npatient: Toothache."))

    def test_rather_not_say_is_recorded_as_declined(self):
        history = self.read("I'd rather not say.")
        self.assertTrue(history.declined)
        self.assertEqual(history.conditions, [])

    def test_call_fills_the_case(self):
        result = self.routine_call(agent(HISTORY_QUESTION), caller("I'm allergic to penicillin."))
        self.assertEqual(STATE.cases[result["case_id"]].medical_history.allergies, ["penicillin"])

    def test_fields_from_the_agent_win_over_transcript(self):
        result = self.routine_call(
            agent(HISTORY_QUESTION), caller("I'm allergic to penicillin."), allergies=["latex"], medications=["warfarin"],
        )
        history = STATE.cases[result["case_id"]].medical_history
        self.assertEqual(history.allergies, ["latex"])
        self.assertEqual(history.medications, ["warfarin"])

    def test_live_triage_extraction_is_used(self):
        found = MedicalHistory(conditions=["diabetes"], allergies=[], medications=[], declined=False)
        with patch.object(pipeline, "get_anthropic_client", return_value=fake_model(medical_history=found)):
            result = self.routine_call()
        self.assertEqual(STATE.cases[result["case_id"]].medical_history, found)

    def test_only_the_clinical_view_gets_it(self):
        result = self.routine_call(agent(HISTORY_QUESTION), caller("I'm allergic to penicillin."))
        path = f"/api/console/patient/{result['patient_id']}"
        reception = client.get(path, params={"role": "receptionist"}).json()
        clinical = client.get(path, params={"role": "clinical"}).json()
        self.assertNotIn("medical_history", reception["patient"])
        self.assertNotIn("medical_history", reception["case"])
        self.assertEqual(clinical["case"]["clinical_panel"]["medical_history"]["allergies"], ["penicillin"])

    def test_online_form_stores_it(self):
        response = client.post("/api/patient/register", json={
            "name": "Ada Fox", "phone": "07700 900502", "problem": "I lost a filling",
            "medical_history": {"conditions": [], "allergies": ["latex"], "medications": [], "declined": False},
        })
        self.assertEqual(STATE.cases[response.json()["case_id"]].medical_history.allergies, ["latex"])

    def test_voice_tool_stores_it(self):
        case = client.post("/api/tools/create_intake", json={"name": "Ada Fox", "phone": "07700 900503"}).json()
        client.post("/api/tools/submit_triage", json={
            "case_id": case["case_id"], "complaint_quote": "I lost a filling",
            "medical_history": {"conditions": [], "allergies": ["latex"], "medications": [], "declined": False},
        })
        self.assertEqual(STATE.cases[case["case_id"]].medical_history.allergies, ["latex"])


class UrgencyDisagreement(IntakeTest):
    def test_agent_raises_a_routine_triage(self):
        result = self.routine_call(agent_urgency="urgent")
        case = STATE.cases[result["case_id"]]
        self.assertEqual(case.urgency, "urgent")
        self.assertEqual(case.agent_urgency, "urgent")

    def test_agent_cannot_lower_triage(self):
        result = self.call(caller("My name is Isla Grant. I have severe pain."), agent_urgency="routine")
        self.assertEqual(STATE.cases[result["case_id"]].urgency, "urgent")

    def test_disagreement_is_kept_on_the_case_without_a_flag(self):
        result = self.routine_call(agent_urgency="urgent")
        self.assertEqual(self.flags(result["case_id"]), [])
        self.assertEqual(STATE.cases[result["case_id"]].status, "accepted")
        self.assertIn(result["outcome"], ("offered", "waiting"))
        self.assertTrue(any("Automated line said urgent" in event.reason for event in STATE.events))

    def test_unknown_urgency_never_loses_the_call(self):
        result = self.routine_call(agent_urgency="very bad")
        self.assertIsNone(STATE.cases[result["case_id"]].agent_urgency)

    def test_urgency_label_ignores_case(self):
        result = self.routine_call(agent_urgency="Urgent")
        self.assertEqual(STATE.cases[result["case_id"]].urgency, "urgent")

    def test_agent_urgency_survives_a_triage_outage(self):
        with patch.object(pipeline, "get_anthropic_client", return_value=fake_model(error=RuntimeError("down"))):
            result = self.routine_call(agent_urgency="urgent")
        self.assertEqual(STATE.cases[result["case_id"]].urgency, "urgent")

    def test_voice_tool_takes_the_safer_urgency(self):
        case = client.post("/api/tools/create_intake", json={"name": "Ada Fox", "phone": "07700 900504"}).json()
        response = client.post("/api/tools/submit_triage", json={
            "case_id": case["case_id"], "complaint_quote": "I lost a filling, cold drinks hurt", "agent_urgency": "urgent",
        }).json()
        self.assertEqual(response["urgency"], "urgent")
        self.assertEqual(self.flags(case["case_id"]), [])


class Emergencies(IntakeTest):
    def test_caller_sent_to_999_is_never_booked(self):
        result = self.call(
            caller("My name is Rory Sinclair. My filling fell out and my arm feels odd."),
            agent("This sounds like it could be an emergency. Please hang up and dial 999 now."),
            outcome="emergency_redirected",
        )
        case = STATE.cases[result["case_id"]]
        self.assertEqual(result["outcome"], "emergency")
        self.assertEqual(case.status, "emergency_redirected")
        self.assertEqual(self.active_bookings(result["patient_id"]), [])

    def test_script_emergencies_are_caught_online_too(self):
        for problem in (
            "I have chest pain", "I think I'm having a stroke", "I can't speak properly", "I keep passing out",
            "I had a severe allergic reaction", "I want to harm myself",
        ):
            response = client.post("/api/patient/register", json={
                "name": "Ada Fox", "phone": f"07700 {abs(hash(problem)) % 1000000:06d}", "problem": problem,
            })
            self.assertEqual(response.json()["outcome"], "emergency", problem)

    def test_past_or_denied_symptoms_are_not_emergencies(self):
        result = self.routine_call(
            agent(HISTORY_QUESTION), caller("I had a stroke years ago, no chest pain, and I hurt myself playing rugby."),
        )
        self.assertNotEqual(result["outcome"], "emergency")

    def test_returning_caller_with_an_emergency_is_not_just_updated(self):
        self.routine_call(caller_phone="07700 900998")
        result = self.routine_call(caller_phone="07700 900998", outcome="emergency_redirected")
        self.assertEqual(result["outcome"], "emergency")

    def test_emergency_call_without_a_name_is_flagged_as_one(self):
        self.call(caller("I can't feel my arm."), outcome="emergency_redirected")
        reasons = [item.reason for item in STATE.needs_attention.values() if "Possible emergency" in item.summary]
        self.assertEqual(reasons, ["red_flag"])


class RedFlagWording(unittest.TestCase):
    def test_everyday_ways_of_saying_an_emergency_are_caught(self):
        for said in (
            "My neck is swollen and it's spreading", "my eye is swollen shut from the tooth",
            "my tongue is swelling up", "my throat is swollen", "I can barely breathe", "I can hardly swallow",
            "I'm having difficulty in swallowing", "I have trouble with breathing",
            "the bleeding hasn't stopped for hours", "the bleeding isn't stopping",
        ):
            self.assertTrue(has_red_flag(said), said)

    def test_a_symptom_clearly_in_the_past_is_not_an_emergency(self):
        for said in (
            "I had chest pain last year but that's sorted, I'm calling about a filling",
            "I had a high temperature last week, gone now",
            "neck swelling from a cyst years ago, I want a scale and polish",
            "I had chest pain in 2019",
            "I passed out two years ago at the gym",
        ):
            self.assertFalse(has_red_flag(said), said)

    def test_a_symptom_that_is_still_going_stays_an_emergency(self):
        for said in (
            "I've had swelling in my neck since last week", "my neck swelling started last week",
            "I had chest pain last week and I still have chest pain", "I still have chest pain from last year",
            "chest pain last year and it's back again now",
        ):
            self.assertTrue(has_red_flag(said), said)


class ProcedureNames(unittest.TestCase):
    def test_the_model_can_only_name_procedures_clinicians_are_listed_for(self):
        for invented in ("Filling", "Root canal treatment", "Denture repair"):
            with self.assertRaises(ValidationError, msg=invented):
                fake_model(likely_procedures=[invented])

    def test_the_schema_sent_to_the_model_lists_the_procedures(self):
        items = Assessment.model_json_schema()["properties"]["likely_procedures"]["items"]
        self.assertIn("Composite restoration", items["enum"])
        self.assertIn("Molar root canal", items["enum"])


class RedFlagAcrossTurns(IntakeTest):
    def test_a_past_date_in_the_next_turn_does_not_hide_an_emergency(self):
        result = self.call(
            caller("My name is Rory Sinclair. I have chest pain"),
            agent("Have you had any injuries?"),
            caller("last year I broke my arm"),
        )
        self.assertEqual(result["outcome"], "emergency")


class AutoMatching(IntakeTest):
    def assessed_call(self, *args, **fields):
        with patch.object(pipeline, "get_anthropic_client", return_value=fake_model(**fields)):
            return self.routine_call(*args)

    def texts(self, patient_id):
        return [m.type for m in STATE.messages.values() if m.patient_id == patient_id]

    def test_ordinary_call_gets_an_appointment_text_without_a_person(self):
        result = self.assessed_call(confidence="high")
        self.assertEqual(result["outcome"], "offered")
        self.assertEqual(self.flags(result["case_id"]), [])
        self.assertIn("offer_single", self.texts(result["patient_id"]))

    def test_medium_confidence_is_matched_automatically(self):
        result = self.assessed_call(confidence="medium")
        self.assertEqual(result["outcome"], "offered")
        self.assertEqual(self.flags(result["case_id"]), [])

    def test_too_little_information_is_flagged(self):
        result = self.assessed_call(confidence="low")
        self.assertEqual(result["outcome"], "review")
        self.assertEqual(self.flags(result["case_id"]), ["symptoms_unclear"])
        self.assertNotIn("offer_single", self.texts(result["patient_id"]))

    def test_urgent_case_needing_senior_care_is_flagged_as_too_severe(self):
        result = self.assessed_call(urgency="urgent", complexity=4)
        self.assertEqual(result["outcome"], "review")
        self.assertEqual(self.flags(result["case_id"]), ["too_severe"])
        self.assertNotIn("offer_single", self.texts(result["patient_id"]))

    def test_agent_raising_a_complex_case_to_urgent_flags_it(self):
        with patch.object(pipeline, "get_anthropic_client", return_value=fake_model(complexity=4)):
            result = self.routine_call(agent_urgency="urgent")
        self.assertEqual(self.flags(result["case_id"]), ["too_severe"])

    def test_complex_but_not_urgent_cases_are_still_matched(self):
        result = self.assessed_call(urgency="routine", complexity=5)
        self.assertNotEqual(result["outcome"], "review")
        self.assertEqual(self.flags(result["case_id"]), [])

    def test_urgent_case_a_student_can_treat_is_matched(self):
        result = self.assessed_call(urgency="urgent", complexity=3)
        self.assertNotEqual(result["outcome"], "review")

    def test_everyday_dental_problems_match_without_a_model(self):
        for number, problem in enumerate(("My denture is loose.", "My gum is sore.", "I have a bad toothache in a crown.")):
            result = self.call(caller(f"My name is Test Person{'ab'[number % 2] * (number + 1)}. {problem}"))
            self.assertNotEqual(result["outcome"], "review", problem)

    def test_vague_call_without_a_model_is_flagged(self):
        result = self.call(caller("My name is Ewan Reid. Something feels a bit odd on one side sometimes."))
        self.assertEqual(self.flags(result["case_id"]), ["symptoms_unclear"])

    def test_severe_words_without_a_model_are_flagged(self):
        result = self.call(caller("My name is Ewan Reid. I think I have an abscess under my tooth."))
        self.assertEqual(self.flags(result["case_id"]), ["too_severe"])

    def expire_offer_for(self, patient_id):
        offer = pipeline._active_offer(patient_id)
        offer.expires_at = "2020-01-01T00:00:00+00:00"
        pipeline.expire_offers()

    def test_urgent_patient_who_never_replies_reaches_a_person(self):
        result = self.assessed_call(urgency="urgent", complexity=3)
        self.expire_offer_for(result["patient_id"])
        self.assertEqual(self.flags(result["case_id"]), ["no_reply"])

    def test_routine_patient_who_never_replies_just_keeps_their_place(self):
        result = self.assessed_call(urgency="routine", complexity=2)
        self.expire_offer_for(result["patient_id"])
        self.assertEqual(self.flags(result["case_id"]), [])
        self.assertEqual(STATE.patients[result["patient_id"]].status, "waitlist")

    def test_voice_tool_flags_too_severe(self):
        case = client.post("/api/tools/create_intake", json={"name": "Ada Fox", "phone": "07700 900505"}).json()
        with patch("tools_api.get_anthropic_client", return_value=fake_model(urgency="urgent", complexity=4)):
            response = client.post("/api/tools/submit_triage", json={
                "case_id": case["case_id"], "complaint_quote": "It really hurts",
            }).json()
        self.assertEqual(response["next_step"], "review")
        self.assertEqual(self.flags(case["case_id"]), ["too_severe"])


class FlagList(IntakeTest):
    def flagged(self):
        with patch.object(pipeline, "get_anthropic_client", return_value=fake_model(confidence="low")):
            result = self.routine_call()
        item = next(i for i in STATE.needs_attention.values() if i.case_id == result["case_id"])
        return result, item

    def test_accepting_sends_the_normal_appointment_text(self):
        result, item = self.flagged()
        client.post("/api/console/resolve_attention", json={"item_id": item.id, "action": "resolve"})
        self.assertEqual(STATE.cases[result["case_id"]].status, "accepted")
        self.assertTrue(any(
            m.type == "offer_single" for m in STATE.messages.values() if m.patient_id == result["patient_id"]
        ))

    def test_denying_closes_the_case_and_tells_the_patient(self):
        result, item = self.flagged()
        client.post("/api/console/resolve_attention", json={"item_id": item.id, "action": "dismiss"})
        self.assertEqual(STATE.cases[result["case_id"]].status, "discharged")
        self.assertEqual(STATE.patients[result["patient_id"]].status, "discharged")
        messages = [m for m in STATE.messages.values() if m.patient_id == result["patient_id"]]
        self.assertEqual(messages[-1].title, "We can't book this")
        self.assertEqual(self.active_bookings(result["patient_id"]), [])

    def test_list_says_which_flags_need_a_decision(self):
        _, item = self.flagged()
        items = client.get("/api/console/needs_attention").json()["items"]
        self.assertEqual(next(i for i in items if i["id"] == item.id)["case"]["status"], "awaiting_tutor")

    def test_seed_flags_follow_the_rules(self):
        reasons = {item.reason for item in STATE.needs_attention.values()}
        self.assertNotIn("borderline_complexity", reasons)
        self.assertIn("too_severe", reasons)

    def test_an_unfilled_chair_stays_on_the_schedule_and_off_the_flags(self):
        booking = next(b for b in STATE.bookings.values() if b.state == "confirmed")
        for patient in STATE.patients.values():
            patient.short_notice_ok = False
        STATE.trigger_cascade_for_slot(booking.slot_id, booking.id, "Test")
        self.assertEqual(STATE.active_cascades[booking.slot_id]["status"], "no_candidate")
        reasons = {item.reason for item in STATE.needs_attention.values()}
        self.assertNotIn("no_backfill_candidate", reasons)


class PatientRecordCalls(IntakeTest):
    def test_record_has_each_transcript_newest_first(self):
        phone = "07700 900997"
        first = self.routine_call(caller_phone=phone, started_at="2026-11-07T09:00:00+00:00")
        self.routine_call(caller_phone=phone, started_at="2026-11-07T10:00:00+00:00")
        record = client.get(f"/api/console/patient/{first['patient_id']}").json()
        history = record["call_history"]
        self.assertEqual([call["started_at"][:13] for call in history], ["2026-11-07T10", "2026-11-07T09"])
        self.assertEqual(history[0]["transcript"][0]["text"], ROUTINE_PROBLEM)


class DeniedSymptoms(IntakeTest):
    def test_saying_you_do_not_have_a_symptom_is_not_an_emergency(self):
        for said in (
            "No trouble breathing", "no difficulty swallowing, just a loose crown", "no high fever",
            "I don't have any chest pain", "I haven't had chest pain", "without any trouble speaking",
            "no fever or trouble breathing", "no swelling near my eye", "not having chest pain",
        ):
            self.assertFalse(has_red_flag(said), said)

    def test_real_emergencies_survive_nearby_negatives(self):
        for said in (
            "I can't breathe", "No, I can't breathe", "It's not okay, I have chest pain", "no I have chest pain",
            "My swelling is going down my neck, no pain though", "I'm not sure but I can't breathe",
            "I don't know what to do, I have chest pain", "It won't stop bleeding",
        ):
            self.assertTrue(has_red_flag(said), said)

    def test_ordinary_call_mentioning_no_breathing_trouble_is_matched(self):
        result = self.call(caller("My name is Rory Sinclair. I lost a filling. No trouble breathing or anything."))
        self.assertEqual(result["outcome"], "offered")

    def test_denied_swelling_is_not_too_severe(self):
        result = self.call(caller("My name is Rory Sinclair. My tooth aches but there is no swelling."))
        self.assertEqual(self.flags(result["case_id"]), [])


class ReturningCallers(IntakeTest):
    PHONE = "07700 920001"

    def ring(self, words):
        return self.call(caller(f"My name is Rory Sinclair. {words}"), caller_phone=self.PHONE)

    def booked_first(self):
        first = self.ring("I lost a filling and cold drinks hurt.")
        token = STATE.patients[first["patient_id"]].contact_token
        client.post(f"/api/patient/{token}/reply", json={"text": "YES"})
        return first

    def test_getting_worse_raises_the_urgency_and_flags_it(self):
        first = self.ring("I lost a filling and cold drinks hurt.")
        second = self.ring("It is now severe pain and I can't sleep.")
        self.assertEqual(second["outcome"], "updated")
        self.assertEqual(STATE.cases[first["case_id"]].urgency, "urgent")
        self.assertEqual(self.flags(first["case_id"]), ["got_worse"])

    def test_an_appointment_is_not_moved_without_a_person(self):
        first = self.booked_first()
        self.ring("It is now severe pain and I can't sleep.")
        booking = self.active_bookings(first["patient_id"])
        self.assertEqual([b.state for b in booking], ["confirmed"])
        self.assertEqual(self.flags(first["case_id"]), ["got_worse"])

    def test_calling_again_about_the_same_thing_raises_nothing(self):
        first = self.ring("I lost a filling and cold drinks hurt.")
        self.ring("I lost a filling. I can do Tuesdays now.")
        self.assertEqual(STATE.cases[first["case_id"]].urgency, "routine")
        self.assertEqual(self.flags(first["case_id"]), [])

    def test_a_vaguer_second_call_never_lowers_the_urgency(self):
        first = self.ring("I have severe pain.")
        self.ring("Just checking in.")
        self.assertEqual(STATE.cases[first["case_id"]].urgency, "urgent")

    def test_emergency_cancels_the_appointment_and_frees_the_chair(self):
        first = self.booked_first()
        slot_id = next(b for b in STATE.bookings.values() if b.patient_id == first["patient_id"]).slot_id
        second = self.ring("I have chest pain.")
        self.assertEqual(second["outcome"], "emergency")
        self.assertEqual(self.active_bookings(first["patient_id"]), [])
        self.assertIn(slot_id, STATE.active_cascades)
        self.assertEqual(STATE.cases[first["case_id"]].status, "cancelled")
        self.assertEqual(STATE.patients[first["patient_id"]].status, "cancelled")

    def test_emergency_withdraws_a_pending_offer(self):
        first = self.ring("I lost a filling and cold drinks hurt.")
        self.ring("I have chest pain.")
        offers = [o for o in STATE.offers.values() if o.patient_id == first["patient_id"]]
        self.assertTrue(offers)
        self.assertNotIn("pending", [o.response for o in offers])
        self.assertEqual(self.active_bookings(first["patient_id"]), [])


class StaffActions(IntakeTest):
    def flagged(self):
        return self.call(caller("My name is Ewan Reid. Something feels a bit odd on one side."))

    def test_clinical_reject_tells_the_patient(self):
        result = self.flagged()
        client.post("/api/console/review_triage", json={"case_id": result["case_id"], "decision": "reject"})
        self.assertEqual(STATE.patients[result["patient_id"]].status, "discharged")
        messages = [m for m in STATE.messages.values() if m.patient_id == result["patient_id"]]
        self.assertEqual(messages[-1].title, "We can't book this")

    def test_clinical_reject_frees_any_appointment(self):
        result = self.routine_call()
        token = STATE.patients[result["patient_id"]].contact_token
        client.post(f"/api/patient/{token}/reply", json={"text": "YES"})
        client.post("/api/console/review_triage", json={"case_id": result["case_id"], "decision": "reject"})
        self.assertEqual(self.active_bookings(result["patient_id"]), [])
        self.assertEqual(STATE.cases[result["case_id"]].status, "discharged")

    def test_booking_by_hand_closes_the_flag(self):
        result = self.flagged()
        shortlist = client.get(f"/api/console/assign_shortlist/{result['case_id']}").json()["shortlist"]
        slot = next(s for row in shortlist for s in row["candidate_slots"])
        client.post("/api/console/assign", json={
            "case_id": result["case_id"], "slot_id": slot["slot_id"], "reason_chip": "other",
        })
        items = [i for i in STATE.needs_attention.values() if i.case_id == result["case_id"]]
        self.assertEqual([i.status for i in items], ["resolved"])


class DemoData(IntakeTest):
    def test_nobody_waits_for_review_without_a_flag(self):
        open_items = {i.case_id for i in STATE.needs_attention.values() if i.status == "open"}
        stuck = [c.id for c in STATE.cases.values() if c.status in ("awaiting_tutor", "intake_done") and c.id not in open_items]
        self.assertEqual(stuck, [])

    def test_activity_is_never_in_the_future(self):
        now = datetime.now(timezone.utc).isoformat()
        stamps = [c.started_at for c in STATE.calls.values()] + [e.at for e in STATE.events]
        stamps += [i.created_at for i in STATE.needs_attention.values()]
        self.assertEqual([s for s in stamps if s[:19] > now[:19]], [])

    def test_a_new_call_is_first_in_the_call_log(self):
        result = self.routine_call()
        calls = client.get("/api/console/overnight").json()["calls"]
        self.assertEqual(calls[0]["patient_id"], result["patient_id"])

    def test_seed_agent_never_diagnoses_or_advises(self):
        said = " ".join(
            line["text"] for call in STATE.calls.values() for line in call.transcript if line["speaker"] == "agent"
        ).lower()
        for words in ("fracture", "bite firmly", "tutor review"):
            self.assertNotIn(words, said)

    def test_audit_log_reads_plainly(self):
        self.routine_call()
        details = " ".join(event.reason for event in STATE.events)
        self.assertNotIn("heuristic", details)
        self.assertNotRegex(details, r"offered \d{4}-\d{2}-\d{2}")


def fake_model(error=None, **fields):
    """Stands in for the Anthropic client at the network boundary."""
    assessment = Assessment(**{**dict(
        urgency="routine", complexity=2, confidence="high", summary_plain="Lost filling.", possible_issues=[],
        not_ruled_out=[], likely_procedures=["Simple restoration"], medical_history=None,
    ), **fields})

    async def parse(**_):
        if error:
            raise error
        return SimpleNamespace(stop_reason="end_turn", parsed_output=assessment)

    return SimpleNamespace(messages=SimpleNamespace(parse=parse))


if __name__ == "__main__":
    unittest.main()

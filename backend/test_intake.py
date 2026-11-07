"""Intake must keep what the voice script collects. Run: python -m unittest discover backend"""

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient

import pipeline
import state
from intake_parsing import parse_dob, read_history
from main import app
from models import MedicalHistory
from state import STATE
from triage import Assessment

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

    def test_disagreement_goes_to_the_worklist_without_blocking_matching(self):
        result = self.routine_call(agent_urgency="urgent")
        self.assertIn("urgency_disagreement", self.flags(result["case_id"]))
        self.assertEqual(STATE.cases[result["case_id"]].status, "accepted")
        self.assertIn(result["outcome"], ("offered", "waiting"))

    def test_agreement_raises_nothing(self):
        result = self.routine_call(agent_urgency="routine")
        self.assertEqual(self.flags(result["case_id"]), [])

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

    def test_closing_a_disagreement_during_review_needs_the_tutor(self):
        with patch.object(pipeline, "get_anthropic_client", return_value=fake_model(confidence="low")):
            result = self.routine_call(agent_urgency="urgent")
        self.assertEqual(STATE.cases[result["case_id"]].status, "awaiting_tutor")
        self.assertNotIn("urgency_disagreement", self.flags(result["case_id"]))

    def test_voice_tool_takes_the_safer_urgency(self):
        case = client.post("/api/tools/create_intake", json={"name": "Ada Fox", "phone": "07700 900504"}).json()
        response = client.post("/api/tools/submit_triage", json={
            "case_id": case["case_id"], "complaint_quote": "I lost a filling, cold drinks hurt", "agent_urgency": "urgent",
        }).json()
        self.assertEqual(response["urgency"], "urgent")
        self.assertIn("urgency_disagreement", self.flags(case["case_id"]))


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

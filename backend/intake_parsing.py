"""Turns what a caller said into the same fields the online form collects."""

from __future__ import annotations
import calendar
import re
from datetime import date
from typing import Dict, List, Optional

from models import MedicalHistory

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
_DAY = re.compile(r"\b(mon|tues?|wed(?:nes)?|thu(?:rs?)?|fri)(?:day)?s?\b")
_DAY_KEYS = {"mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday", "fri": "friday"}
_NEGATIVE = re.compile(r"\b(not|never|can'?t|cannot|can not|won'?t|unable|except|apart from|other than|avoid|no)\b")
_MORNING = re.compile(r"\b(morning|mornings|am|before lunch|early)\b")
_AFTERNOON = re.compile(r"\b(afternoon|afternoons|pm|after lunch|late)\b")
_YES = re.compile(r"\b(yes|yeah|yep|sure|definitely|of course|i can|that'?s fine|no problem)\b")
_NO = re.compile(r"\b(no|nope|not really|i can'?t|cannot|rather not)\b")
_NAME = re.compile(
    r"\b(?i:my name is|my name'?s|this is|it'?s|i'?m|i am)\s+([A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)*)"
)

_ONES = ("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth "
         "fifteenth sixteenth seventeenth eighteenth nineteenth").split()
_ORDINALS = {word: day for day, word in enumerate(_ONES, 1)}
_ORDINALS.update({"twentieth": 20, "thirtieth": 30, "thirty first": 31})
_ORDINALS.update({f"twenty {word}": 20 + day for day, word in enumerate(_ONES[:9], 1)})
_ORDINAL = re.compile(r"\b(" + "|".join(sorted(_ORDINALS, key=len, reverse=True)) + r")\b")
_MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})
_MONTH = re.compile(r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\b")
_SLASHED = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-]((?:19|20)\d{2})\b")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_DAY_NUMBER = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\b")

_HISTORY_QUESTION = re.compile(r"condition|allerg|medication|medicine|medical history", re.IGNORECASE)
_DECLINED = re.compile(r"\b(rather not|prefer not|don'?t want to|not comfortable)\b", re.IGNORECASE)
_NOTHING = re.compile(r"(no|nope|none|nothing|not|never)\b", re.IGNORECASE)
_FILLER = re.compile(r"yes|yeah|yep|well|um|so|ok|okay", re.IGNORECASE)
_ALLERGY = re.compile(r"allergic to (.+)|allergy to (.+)|(.+?) allergy", re.IGNORECASE)
_MEDICATION = re.compile(r"\b(?:take|takes|taking|i'?m on|i am on)\s+(.+)", re.IGNORECASE)
_CONDITION_START = re.compile(r"^(?:i'?ve got|i have got|i have|i'?ve|i suffer from|got|have)\s+", re.IGNORECASE)


def full_week(am: bool = True, pm: bool = True) -> Dict[str, Dict[str, bool]]:
    return {day: {"am": am, "pm": pm} for day in DAYS}


def parse_availability(text: str) -> Dict[str, Dict[str, bool]]:
    """Read day and session preferences from plain speech. Unknown means available."""
    grid = full_week()
    only_days: List[str] = []
    only_sessions: Dict[str, str] = {}
    all_sessions: Optional[str] = None

    for clause in re.split(r"[.;,!?\n]|\bbut\b", text.lower()):
        negative = bool(_NEGATIVE.search(clause))
        # "Tuesday mornings or Thursday afternoons" is two preferences in one clause.
        mixed = _MORNING.search(clause) and _AFTERNOON.search(clause)
        parts = re.split(r"\b(?:or|and)\b", clause) if mixed else [clause]

        for part in parts:
            days = [_DAY_KEYS[match[:3]] for match in _DAY.findall(part)]
            morning = bool(_MORNING.search(part))
            afternoon = bool(_AFTERNOON.search(part))
            session = "am" if morning and not afternoon else "pm" if afternoon and not morning else None

            if days and negative:
                for day in days:
                    if session:
                        grid[day][session] = False
                    else:
                        grid[day] = {"am": False, "pm": False}
            elif days:
                only_days.extend(days)
                if session:
                    for day in days:
                        only_sessions[day] = session
            elif session:
                if negative:
                    all_sessions = "pm" if session == "am" else "am"
                else:
                    all_sessions = session

    if only_days:
        for day in DAYS:
            if day not in only_days:
                grid[day] = {"am": False, "pm": False}
    if all_sessions:
        other = "pm" if all_sessions == "am" else "am"
        for day in DAYS:
            grid[day][other] = False
    for day, session in only_sessions.items():
        other = "pm" if session == "am" else "am"
        grid[day][other] = False
    return grid


def answer_to(transcript: List[dict], question: str) -> Optional[bool]:
    """Find the caller's yes or no to the agent's question about a topic."""
    pattern = re.compile(question, re.IGNORECASE)
    for index, line in enumerate(transcript):
        if line.get("speaker") == "patient" or not pattern.search(line.get("text", "")):
            continue
        for reply in transcript[index + 1:]:
            if reply.get("speaker") != "patient":
                continue
            text = reply.get("text", "").lower()
            if _NO.search(text) and not _YES.search(text):
                return False
            return True if _YES.search(text) else None
    return None


def availability_words(transcript: List[dict]) -> str:
    """The caller's answers after the agent asks about days or times."""
    pattern = re.compile(r"\b(days?|times?|when|available|availability|mornings?|afternoons?)\b", re.IGNORECASE)
    lines: List[str] = []
    for index, line in enumerate(transcript):
        if line.get("speaker") == "patient" or not pattern.search(line.get("text", "")):
            continue
        for reply in transcript[index + 1:]:
            if reply.get("speaker") != "patient":
                break
            lines.append(reply.get("text", ""))
    return " . ".join(lines)


def parse_dob(text: str) -> Optional[str]:
    """YYYY-MM-DD if the words are a real past date, otherwise the words themselves for staff to read."""
    said = text.strip().rstrip(".")
    if not said:
        return None
    lowered = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", said.lower())
    slashed = _SLASHED.search(lowered)
    year = _YEAR.search(lowered)
    month = _MONTH.search(lowered)
    try:
        if slashed:
            day_number, month_number, year_number = (int(part) for part in slashed.groups())
        elif year and month:
            rest = lowered.replace(year.group(), " ")
            ordinal = _ORDINAL.search(rest)
            day_number = _ORDINALS[ordinal.group(1)] if ordinal else int(_DAY_NUMBER.search(rest).group(1))
            month_number, year_number = _MONTHS[month.group(1)], int(year.group())
        else:
            return said
        born = date(year_number, month_number, day_number)
    except (AttributeError, ValueError):
        return said
    return born.isoformat() if born <= date.today() else said


def caller_dob(transcript: List[dict]) -> Optional[str]:
    pattern = re.compile(r"date of birth|birthday|\bborn\b", re.IGNORECASE)
    for index, line in enumerate(transcript):
        if line.get("speaker") == "patient" or not pattern.search(line.get("text", "")):
            continue
        for reply in transcript[index + 1:]:
            if reply.get("speaker") == "patient":
                return parse_dob(reply.get("text", ""))
    return None


def _sort_history(answer: str, history: MedicalHistory) -> None:
    """Rule-based fallback for when no model is available. A bare name joins the list before it."""
    target = history.conditions
    for clause in re.split(r"[.;,!?\n]|\band\b", answer):
        clause = clause.strip()
        if not clause or _NOTHING.match(clause) or _FILLER.fullmatch(clause):
            continue
        allergy = _ALLERGY.search(clause)
        medication = _MEDICATION.search(clause)
        if allergy:
            target = history.allergies
            target.append(next(group for group in allergy.groups() if group).strip())
        elif medication:
            target = history.medications
            target.append(medication.group(1).strip())
        else:
            target.append(_CONDITION_START.sub("", clause))


def read_history(transcript: str) -> Optional[MedicalHistory]:
    """Sort the caller's answer into fields. None means the question never came up."""
    lines = [line.partition(": ") for line in transcript.splitlines()]
    history = None
    for index, (speaker, _, text) in enumerate(lines):
        if speaker == "patient" or not _HISTORY_QUESTION.search(text):
            continue
        history = history or MedicalHistory(conditions=[], allergies=[], medications=[], declined=False)
        for reply_speaker, _, reply in lines[index + 1:]:
            if reply_speaker != "patient":
                break
            if _DECLINED.search(reply):
                history.declined = True
            else:
                _sort_history(reply, history)
    return history


def caller_name(transcript: List[dict]) -> Optional[str]:
    for line in transcript:
        if line.get("speaker") == "patient":
            match = _NAME.search(line.get("text", ""))
            if match:
                return match.group(1)
    return None


def patient_words(transcript: List[dict]) -> str:
    return " ".join(line.get("text", "") for line in transcript if line.get("speaker") == "patient")


def transcript_text(transcript: List[dict]) -> str:
    return "\n".join(f"{line.get('speaker', 'unknown')}: {line.get('text', '')}" for line in transcript)

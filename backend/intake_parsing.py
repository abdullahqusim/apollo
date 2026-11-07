"""Turns what a caller said into the same fields the online form collects."""

from __future__ import annotations
import re
from typing import Dict, List, Optional

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


def full_week(am: bool = True, pm: bool = True) -> Dict[str, Dict[str, bool]]:
    return {day: {"am": am, "pm": pm} for day in DAYS}


def parse_availability(text: str) -> Dict[str, Dict[str, bool]]:
    """Read day and session preferences from plain speech. Unknown means available."""
    grid = full_week()
    only_days: List[str] = []
    only_sessions: Dict[str, str] = {}
    all_sessions: Optional[str] = None

    for clause in re.split(r"[.;,!?\n]|\bbut\b", text.lower()):
        days = [_DAY_KEYS[match[:3]] for match in _DAY.findall(clause)]
        morning = bool(_MORNING.search(clause))
        afternoon = bool(_AFTERNOON.search(clause))
        session = "am" if morning and not afternoon else "pm" if afternoon and not morning else None
        negative = bool(_NEGATIVE.search(clause))

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

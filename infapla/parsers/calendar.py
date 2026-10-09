import re
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

def unfold_ics_lines(raw_text: str) -> List[str]:
    """
    Unfolds lines in iCalendar files according to RFC 5545 (lines starting with space/tab continue previous line).
    """
    lines = raw_text.splitlines()
    unfolded = []
    for line in lines:
        if (line.startswith(" ") or line.startswith("\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded

def parse_ics_datetime(val: str) -> Optional[datetime.datetime]:
    """
    Parses DTSTART or DTEND strings into datetime objects.
    Formats:
    20261012T090000Z
    20261012T090000
    20261012
    """
    val = val.strip()
    # Strip parameter prefixes like TZID=...:20261012T090000
    if ":" in val:
        val = val.split(":")[-1]

    try:
        if len(val) == 8 and val.isdigit():
            # Date only
            return datetime.datetime.strptime(val, "%Y%m%d")
        if val.endswith("Z"):
            return datetime.datetime.strptime(val, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
        if "T" in val:
            return datetime.datetime.strptime(val[:15], "%Y%m%dT%H%M%S")
    except Exception:
        pass
    return None

def format_datetime_ics(dt: datetime.datetime) -> str:
    """
    Formats a datetime object to standard ICS format.
    """
    if dt.tzinfo:
        utc_dt = dt.astimezone(datetime.timezone.utc)
        return utc_dt.strftime("%Y%m%dT%H%M%SZ")
    return dt.strftime("%Y%m%dT%H%M%S")

def parse_ics_file(file_content: str, filename: str = "") -> List[Dict[str, Any]]:
    """
    Parses an .ics file string into a list of event dictionaries.
    """
    lines = unfold_ics_lines(file_content)
    events = []
    current_event: Optional[Dict[str, Any]] = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.upper() == "BEGIN:VEVENT":
            current_event = {
                "source_file": filename,
                "summary": "Untitled Event",
                "dtstart": None,
                "dtend": None,
                "location": "",
                "description": "",
                "uid": ""
            }
            continue

        if stripped.upper() == "END:VEVENT":
            if current_event:
                # Add human readable time strings
                dt_start = current_event["dtstart"]
                dt_end = current_event["dtend"]
                current_event["start_str"] = dt_start.strftime("%Y-%m-%d %H:%M") if dt_start else "TBD"
                current_event["end_str"] = dt_end.strftime("%Y-%m-%d %H:%M") if dt_end else ""
                current_event["is_all_day"] = (
                    dt_start is not None and 
                    dt_start.hour == 0 and dt_start.minute == 0 and dt_start.second == 0 and
                    (dt_end is None or (dt_end.hour == 0 and dt_end.minute == 0))
                )
                events.append(current_event)
                current_event = None
            continue

        if current_event is not None and ":" in stripped:
            key_part, val = stripped.split(":", 1)
            key = key_part.split(";")[0].upper()
            val = val.replace(r"\n", "\n").replace(r"\,", ",").replace(r"\;", ";").replace(r"\\", "\\")

            if key == "SUMMARY":
                current_event["summary"] = val
            elif key == "DTSTART":
                current_event["dtstart"] = parse_ics_datetime(stripped)
            elif key == "DTEND":
                current_event["dtend"] = parse_ics_datetime(stripped)
            elif key == "LOCATION":
                current_event["location"] = val
            elif key == "DESCRIPTION":
                current_event["description"] = val
            elif key == "UID":
                current_event["uid"] = val

    return events

def create_ics_event(
    summary: str,
    dtstart: datetime.datetime,
    dtend: Optional[datetime.datetime] = None,
    location: str = "",
    description: str = "",
    uid: Optional[str] = None
) -> str:
    """
    Generates a full VCALENDAR string containing a single VEVENT.
    """
    if dtend is None:
        dtend = dtstart + datetime.timedelta(hours=1)
    if uid is None:
        uid = f"{uuid.uuid4()}@infapla.local"

    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    start_str = format_datetime_ics(dtstart)
    end_str = format_datetime_ics(dtend)

    desc_escaped = description.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
    loc_escaped = location.replace("\\", "\\\\").replace("\n", " ").replace(",", "\\,").replace(";", "\\;")
    sum_escaped = summary.replace("\\", "\\\\").replace("\n", " ").replace(",", "\\,").replace(";", "\\;")

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//InFaPla//Intelligent Family Planner//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{now_str}
DTSTART:{start_str}
DTEND:{end_str}
SUMMARY:{sum_escaped}
LOCATION:{loc_escaped}
DESCRIPTION:{desc_escaped}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""
    return ics_content

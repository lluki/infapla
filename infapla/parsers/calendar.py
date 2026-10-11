import re
import uuid
import hashlib
import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

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

def generate_vtimezone(tz_name: str = "Europe/Zurich") -> str:
    """
    Generates standard RFC 5545 VTIMEZONE component for a given timezone.
    """
    if tz_name in (
        "Europe/Zurich", "Europe/Berlin", "Europe/Vienna", "Europe/Paris",
        "Europe/Rome", "Europe/Madrid", "Europe/Amsterdam", "Europe/Brussels",
        "Europe/Stockholm", "Europe/Oslo", "Europe/Copenhagen", "Europe/Warsaw"
    ):
        return f"""BEGIN:VTIMEZONE
TZID:{tz_name}
X-LIC-LOCATION:{tz_name}
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""

    try:
        tz = ZoneInfo(tz_name)
        dt_jan = datetime.datetime(2026, 1, 15, 12, 0, tzinfo=tz)
        dt_jul = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=tz)
        off_jan = dt_jan.utcoffset() or datetime.timedelta(0)
        off_jul = dt_jul.utcoffset() or datetime.timedelta(0)

        def fmt_offset(td):
            sec = int(td.total_seconds())
            sign = "+" if sec >= 0 else "-"
            sec = abs(sec)
            h = sec // 3600
            m = (sec % 3600) // 60
            return f"{sign}{h:02d}{m:02d}"

        if off_jan == off_jul:
            return f"""BEGIN:VTIMEZONE
TZID:{tz_name}
BEGIN:STANDARD
TZOFFSETFROM:{fmt_offset(off_jan)}
TZOFFSETTO:{fmt_offset(off_jan)}
TZNAME:{dt_jan.tzname() or tz_name}
DTSTART:19700101T000000
END:STANDARD
END:VTIMEZONE"""
        else:
            std_dt = dt_jan if off_jan < off_jul else dt_jul
            dst_dt = dt_jul if off_jan < off_jul else dt_jan
            return f"""BEGIN:VTIMEZONE
TZID:{tz_name}
BEGIN:DAYLIGHT
TZOFFSETFROM:{fmt_offset(std_dt.utcoffset())}
TZOFFSETTO:{fmt_offset(dst_dt.utcoffset())}
TZNAME:{dst_dt.tzname() or 'DST'}
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:{fmt_offset(dst_dt.utcoffset())}
TZOFFSETTO:{fmt_offset(std_dt.utcoffset())}
TZNAME:{std_dt.tzname() or 'STD'}
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""
    except Exception:
        return f"""BEGIN:VTIMEZONE
TZID:{tz_name}
BEGIN:STANDARD
TZOFFSETFROM:+0100
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19700101T000000
END:STANDARD
END:VTIMEZONE"""

def parse_ics_datetime(val: str, default_tz: str = "Europe/Zurich") -> Optional[datetime.datetime]:
    """
    Parses DTSTART or DTEND strings into datetime objects.
    Formats:
    20261012T090000Z
    20261012T090000
    20261012
    DTSTART;TZID=Europe/Zurich:20261012T090000
    """
    val = val.strip()
    extracted_tz = None
    if ";" in val and ":" in val:
        params, val_part = val.split(":", 1)
        for p in params.split(";"):
            if p.upper().startswith("TZID="):
                extracted_tz = p.split("=", 1)[1].strip().strip('"')
        val = val_part
    elif ":" in val:
        val = val.split(":")[-1]

    try:
        if len(val) == 8 and val.isdigit():
            # Date only
            return datetime.datetime.strptime(val, "%Y%m%d")

        effective_tz = extracted_tz or default_tz
        try:
            tz = ZoneInfo(effective_tz)
        except Exception:
            tz = None

        if val.endswith("Z"):
            dt_utc = datetime.datetime.strptime(val, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
            if tz:
                return dt_utc.astimezone(tz)
            return dt_utc
        if "T" in val:
            dt_naive = datetime.datetime.strptime(val[:15], "%Y%m%dT%H%M%S")
            if tz:
                return dt_naive.replace(tzinfo=tz)
            return dt_naive
    except Exception:
        pass
    return None

def format_datetime_ics(dt: datetime.datetime) -> str:
    """
    Formats a datetime object to standard local ICS format (YYYYMMDDTHHMMSS).
    """
    return dt.strftime("%Y%m%dT%H%M%S")

def parse_ics_file(file_content: str, filename: str = "", default_tz: str = "Europe/Zurich") -> List[Dict[str, Any]]:
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
                if dt_start:
                    if dt_start.tzinfo is not None:
                        try:
                            dt_start = dt_start.astimezone(ZoneInfo(default_tz))
                        except Exception:
                            pass
                    current_event["start_str"] = dt_start.strftime("%Y-%m-%d %H:%M")
                else:
                    current_event["start_str"] = "TBD"

                if dt_end:
                    if dt_end.tzinfo is not None:
                        try:
                            dt_end = dt_end.astimezone(ZoneInfo(default_tz))
                        except Exception:
                            pass
                    current_event["end_str"] = dt_end.strftime("%Y-%m-%d %H:%M")
                else:
                    current_event["end_str"] = ""

                current_event["is_all_day"] = (
                    dt_start is not None and 
                    dt_start.hour == 0 and dt_start.minute == 0 and dt_start.second == 0 and
                    (dt_end is None or (dt_end.hour == 0 and dt_end.minute == 0))
                )
                if not current_event["uid"]:
                    seed = f"{filename}:{current_event['summary']}:{current_event['start_str']}"
                    current_event["uid"] = f"event-{hashlib.sha256(seed.encode()).hexdigest()[:16]}"
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
                current_event["dtstart"] = parse_ics_datetime(stripped, default_tz=default_tz)
            elif key == "DTEND":
                current_event["dtend"] = parse_ics_datetime(stripped, default_tz=default_tz)
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
    uid: Optional[str] = None,
    tz_name: str = "Europe/Zurich"
) -> str:
    """
    Generates a full VCALENDAR string containing a VTIMEZONE and a single VEVENT.
    """
    if dtend is None:
        dtend = dtstart + datetime.timedelta(hours=1)
    if uid is None:
        uid = f"{uuid.uuid4()}@infapla.local"

    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    start_str = format_datetime_ics(dtstart)
    end_str = format_datetime_ics(dtend)
    vtz = generate_vtimezone(tz_name)

    desc_escaped = description.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
    loc_escaped = location.replace("\\", "\\\\").replace("\n", " ").replace(",", "\\,").replace(";", "\\;")
    sum_escaped = summary.replace("\\", "\\\\").replace("\n", " ").replace(",", "\\,").replace(";", "\\;")

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//InFaPla//Intelligent Family Planner//EN
CALSCALE:GREGORIAN
{vtz}
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{now_str}
DTSTART;TZID={tz_name}:{start_str}
DTEND;TZID={tz_name}:{end_str}
SUMMARY:{sum_escaped}
LOCATION:{loc_escaped}
DESCRIPTION:{desc_escaped}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""
    return ics_content

def delete_ics_event(
    file_content: str,
    uid: Optional[str] = None,
    summary: Optional[str] = None,
    filename: str = ""
) -> Tuple[str, int]:
    """
    Removes VEVENT blocks matching `uid` or `summary` from `file_content`.
    Returns (updated_ics_string, deleted_count).
    """
    newline = "\r\n" if "\r\n" in file_content else "\n"
    lines = file_content.splitlines()

    output_lines: List[str] = []
    current_block: List[str] = []
    in_vevent = False
    deleted_count = 0

    clean_uid = uid.strip() if uid else None
    clean_summary = summary.strip().lower() if summary else None

    for line in lines:
        stripped = line.strip()
        if stripped.upper() == "BEGIN:VEVENT":
            in_vevent = True
            current_block = [line]
            continue

        if in_vevent:
            current_block.append(line)
            if stripped.upper() == "END:VEVENT":
                in_vevent = False
                parsed = parse_ics_file(newline.join(current_block), filename=filename)
                matched = False
                if parsed:
                    ev = parsed[0]
                    if clean_uid and ev.get("uid") == clean_uid:
                        matched = True
                    elif not clean_uid and clean_summary and ev.get("summary", "").strip().lower() == clean_summary:
                        matched = True
                if matched:
                    deleted_count += 1
                else:
                    output_lines.extend(current_block)
                current_block = []
        else:
            output_lines.append(line)

    if current_block:
        output_lines.extend(current_block)

    res = newline.join(output_lines)
    if file_content.endswith(("\n", "\r\n")) and res and not res.endswith(("\n", "\r\n")):
        res += newline
    return res, deleted_count

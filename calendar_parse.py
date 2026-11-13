"""
calendar_parse.py - turn typed sentences into calendar drafts. Pure logic: no window, no internet, no Google.

    "CS31 hw due Friday 11pm"                     ->  CS31 hw due    Fri Nov 20 11:00 pm - midnight
    "Discussion every Mon/Wed 2pm until Dec 5"    ->  Discussion     Mon 2:00 pm - 3:00 pm, Weekly on MO, WE until 12/05/2026

This is a port of ECHO Calendar's script.js (github.com/htmiyagi/echo-calendar), same rules and same defaults:
    - one event per line or per semicolon; commas never split ("Mon, Wed, Fri" stays one event)
    - "every" / "daily" / "weekly" / "biweekly" / two or more weekdays  ->  a repeat rule (an RRULE, below)
    - no time given -> due at 11:59 pm; a time but no end -> 1 hour long
    - nothing understood -> a placeholder (tomorrow 9 am) flagged needs_review, so it's never silently wrong

RRULE = the standard text line calendars use for repeats, e.g. "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261205T235959Z"
(weekly, on Mondays and Wednesdays, until Dec 5). Google Calendar takes it as is.

ECHO used the chrono-node library to read dates. Here it's parsedatetime, with a small "forward" rule on top so a
time that already passed today means tomorrow (chrono's forwardDate). Times are plain local times (no time zone);
the code that talks to Google adds the zone.

Try it:   .venv/bin/python calendar_parse.py "CS31 hw due Friday 11pm"
"""

import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from parsedatetime import pdt_locales

# parsedatetime reads "lunch", "breakfast" and "dinner" as times (12 pm, 8 am, 7 pm), so "Lunch with Sam tomorrow"
# would lose "Lunch" from its title. Chrono doesn't do that, so take them out. Must happen BEFORE Constants() is built.
for _meal in ("lunch", "breakfast", "dinner"):
    pdt_locales.base.re_sources.pop(_meal, None)

import parsedatetime  # noqa: E402  (has to come after the fix above)

_CAL = parsedatetime.Calendar(parsedatetime.Constants(), version=parsedatetime.VERSION_CONTEXT_STYLE)

DUE_TIME = time(23, 59)                    # no time given -> due at 11:59 pm
DUE_LENGTH = timedelta(minutes=30)         # ...and lasts 30 minutes (ECHO's choice)
DEFAULT_LENGTH = timedelta(hours=1)        # a time but no end -> 1 hour
REVIEW_TIME = time(9, 0)                   # nothing understood -> placeholder tomorrow at 9 am

DAY_CODES = {
    "sun": "SU", "sunday": "SU",
    "mon": "MO", "monday": "MO",
    "tue": "TU", "tues": "TU", "tuesday": "TU",
    "wed": "WE", "weds": "WE", "wednesday": "WE",
    "thu": "TH", "thur": "TH", "thurs": "TH", "thursday": "TH",
    "fri": "FR", "friday": "FR",
    "sat": "SA", "saturday": "SA",
}
WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]   # Python's weekday(): Monday = 0
DAY_NAME_RE = re.compile(r"\b(sunday|sun|monday|mon|tuesday|tues|tue|wednesday|weds|wed|"
                         r"thursday|thurs|thur|thu|friday|fri|saturday|sat)\b", re.IGNORECASE)
# ECHO's pattern, plus an optional ", 2026" year: ECHO stopped at the comma, and the leftover "2026" read as 8:26 pm.
UNTIL_RE = re.compile(r"\buntil\s+([a-zA-Z0-9,/\-\s]+?(?:,\s*\d{4})?)(?=$|[,;.])", re.IGNORECASE)
RANGE_GAP_RE = re.compile(r"\s*(-|to)?\s*", re.IGNORECASE)     # what may sit between "2pm" and "4pm" in a range
TITLE_EDGES_RE = re.compile(r"^[\s,.\-–:]+|[\s,.\-–:]+$")


@dataclass(frozen=True)
class Recurrence:
    freq: str                        # "DAILY" or "WEEKLY"
    interval: int | None = None      # 2 = every other week
    byday: tuple[str, ...] = ()      # ("MO", "WE")
    until: date | None = None


@dataclass(frozen=True)
class Draft:
    """One event, shown to the user before anything is added ("show me first")."""
    title: str
    start: datetime
    end: datetime
    rrule: str | None
    repeats: bool
    needs_review: bool
    raw: str


# ---- dates -----------------------------------------------------------------------------------------
def _find_dates(text: str, now: datetime) -> list[tuple[datetime, bool, int, int]]:
    """Every date/time found in text, as (when, has_time, start index, end index)."""
    found = _CAL.nlp(text, sourceTime=now) or ()
    return [(when, ctx.hasTime, first, last) for when, ctx, first, last, _ in found]


def _parse_date(text: str, now: datetime) -> date | None:
    found = _find_dates(text, now)
    return found[0][0].date() if found else None


# ---- repeats (ECHO's extractRecurrence) ------------------------------------------------------------
def _weekly_cleanup(text: str) -> str:
    """Remove the day names and their glue words once they've become a repeat rule."""
    text = DAY_NAME_RE.sub(" ", text)
    text = re.sub(r"\bevery\b", " ", text, count=1, flags=re.IGNORECASE)
    text = re.sub(r"\bon\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r",\s*and\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\band\b", " ", text, flags=re.IGNORECASE)
    text = text.replace("/", " ")
    return re.sub(r"[,\s]{2,}", " ", text)


def extract_recurrence(text: str, now: datetime) -> tuple[Recurrence | None, str]:
    """Find a repeat rule in text. Returns (the rule or None, text with the repeat words taken out)."""
    cleaned = text
    until = None
    match = UNTIL_RE.search(cleaned)
    if match:
        until = _parse_date(match.group(1), now)
        if until:
            cleaned = cleaned.replace(match.group(0), " ", 1)

    has_trigger = re.search(r"\b(every|recurring)\b", cleaned, re.IGNORECASE) is not None
    day_codes = list(dict.fromkeys(DAY_CODES[m.lower()] for m in DAY_NAME_RE.findall(cleaned)))  # no repeats, in order

    recurrence = None
    if re.search(r"\b(every day|daily)\b", cleaned, re.IGNORECASE):
        recurrence = Recurrence("DAILY")
        cleaned = re.sub(r"\b(every day|daily)\b", " ", cleaned, count=1, flags=re.IGNORECASE)
    elif len(day_codes) >= 2 or (day_codes and has_trigger):
        # Two or more weekdays together ("Mon, Wed, Fri") is a class schedule even without "every".
        recurrence = Recurrence("WEEKLY", byday=tuple(day_codes))
        cleaned = _weekly_cleanup(cleaned)
    else:
        for word, rule in (("biweekly", Recurrence("WEEKLY", interval=2)), ("weekly", Recurrence("WEEKLY")),
                           ("recurring", Recurrence("WEEKLY"))):
            if re.search(rf"\b{word}\b", cleaned, re.IGNORECASE):
                recurrence = rule
                cleaned = re.sub(rf"\b{word}\b", " ", cleaned, count=1, flags=re.IGNORECASE)
                break

    if recurrence and until:
        recurrence = Recurrence(recurrence.freq, recurrence.interval, recurrence.byday, until)
    return recurrence, cleaned


# ---- RRULE text (ECHO's toRRule, recurrenceSummary, getUntilFromRRule, setUntilOnRRule) -------------
def _until_text(day: date) -> str:
    # Zero-padded on purpose, so a strange year can't make a too-short UNTIL. (Note: "Z" means UTC, as in ECHO.)
    return f"UNTIL={day.year:04d}{day.month:02d}{day.day:02d}T235959Z"


def to_rrule(rec: Recurrence | None) -> str | None:
    if rec is None:
        return None
    parts = [f"FREQ={rec.freq}"]
    if rec.interval:
        parts.append(f"INTERVAL={rec.interval}")
    if rec.byday:
        parts.append("BYDAY=" + ",".join(rec.byday))
    if rec.until:
        parts.append(_until_text(rec.until))
    return "RRULE:" + ";".join(parts)


def recurrence_summary(rrule: str | None) -> str:
    """Short words for a draft card, e.g. "Weekly on MO, WE until 12/05/2026"."""
    if not rrule:
        return "Does not repeat"
    freq = re.search(r"FREQ=(\w+)", rrule)
    byday = re.search(r"BYDAY=([\w,]+)", rrule)
    until = re.search(r"UNTIL=(\d{8})", rrule)
    summary = "Daily" if freq and freq.group(1) == "DAILY" else "Weekly"
    if byday:
        summary += " on " + ", ".join(byday.group(1).split(","))
    if until:
        s = until.group(1)
        summary += f" until {s[4:6]}/{s[6:8]}/{s[0:4]}"
    else:
        summary += " — no end date"
    return summary


def get_until(rrule: str | None) -> date | None:
    match = re.search(r"UNTIL=(\d{4})(\d{2})(\d{2})", rrule or "")
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else None


def set_until(rrule: str | None, day: date | None) -> str | None:
    """Change (or remove, with day=None) the end date of a repeat rule.

    Removes EVERY old UNTIL, however broken, before adding one. In ECHO a half-typed year left short UNTILs
    behind that piled up, and Google rejected the rule with a 400 error. This is the fix, kept on purpose.
    """
    if not rrule:
        return rrule
    base = re.sub(r";?UNTIL=[^;]*", "", rrule)
    return base if day is None else f"{base};{_until_text(day)}"


# ---- one event (ECHO's parseSegment) ---------------------------------------------------------------
def split_into_segments(text: str) -> list[str]:
    """One event per line or semicolon. Commas never split: they live inside "Mon, Wed, Fri" and "Dec 5, 2026"."""
    return [part.strip() for part in re.split(r"\r?\n|;", text) if part.strip()]


def _range_end(cleaned: str, found: list, start: datetime) -> tuple[datetime | None, int]:
    """If the first date is followed by "- 4pm" or "to 4pm", return (that end time, where the range text ends)."""
    if len(found) < 2:
        return None, found[0][3]
    _, _, _, first_end = found[0]
    when, has_time, second_start, second_end = found[1]
    if not has_time or not RANGE_GAP_RE.fullmatch(cleaned[first_end:second_start]):
        return None, first_end
    end = datetime.combine(start.date(), when.time())
    if end <= start:                     # "11pm - 1am" ends the next day
        end += timedelta(days=1)
    return end, second_end


def _first_matching_day(start: datetime, byday: tuple[str, ...]) -> datetime:
    """Move start forward to the first day the rule repeats on (so "every Mon/Wed" doesn't also land on a Friday)."""
    for _ in range(7):
        if WEEKDAY_CODES[start.weekday()] in byday:
            return start
        start += timedelta(days=1)
    return start


def _clean_title(title: str, raw: str) -> str:
    title = TITLE_EDGES_RE.sub("", re.sub(r"\s{2,}", " ", title)).strip()
    return title or raw.strip()


def parse_segment(raw: str, now: datetime) -> Draft:
    recurrence, cleaned = extract_recurrence(raw.replace("–", "-").replace("—", "-"), now)
    found = _find_dates(cleaned, now)

    if not found:
        start = datetime.combine(now.date() + timedelta(days=1), REVIEW_TIME)
        return Draft(_clean_title(cleaned, raw), start, start + DEFAULT_LENGTH, to_rrule(recurrence),
                     recurrence is not None, True, raw)

    start, has_time, first, _ = found[0]
    start = start.replace(second=0, microsecond=0)
    end, last = _range_end(cleaned, found, start)
    title = cleaned[:first] + cleaned[last:]

    if not has_time:
        start = datetime.combine(start.date(), DUE_TIME)
    elif start < now and start.date() == now.date():
        start += timedelta(days=1)                       # "2pm" when it's already 3 pm means tomorrow
        end = end + timedelta(days=1) if end else None
    if recurrence and recurrence.byday:
        moved = _first_matching_day(start, recurrence.byday)
        end = end + (moved - start) if end else None
        start = moved
    if end is None:
        end = start + (DEFAULT_LENGTH if has_time else DUE_LENGTH)

    return Draft(_clean_title(title, raw), start, end, to_rrule(recurrence), recurrence is not None, False, raw)


def parse(text: str, now: datetime | None = None) -> list[Draft]:
    """All the drafts in a block of typed text. now is only passed in by tests."""
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    return [parse_segment(segment, now) for segment in split_into_segments(text)]


if __name__ == "__main__":
    for draft in parse(" ".join(sys.argv[1:]) or "CS31 hw due Friday 11pm\nDiscussion every Mon/Wed 2pm until Dec 5"):
        flag = "  [NEEDS REVIEW]" if draft.needs_review else ""
        print(f"{draft.title!r}: {draft.start:%a %b %d %I:%M %p} -> {draft.end:%a %b %d %I:%M %p}, "
              f"{recurrence_summary(draft.rrule)}{flag}")

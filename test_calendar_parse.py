"""
Tests for calendar_parse.py (typed sentences -> calendar drafts). No internet, no Google: pure logic.

Run them:   .venv/bin/python -m unittest test_calendar_parse -v

"Now" is pinned to Friday, Nov 13 2026, 12:50 am, so "Friday" and "tomorrow" always mean the same day.
"""

import unittest
from datetime import date, datetime, timedelta

import calendar_parse as cp

NOW = datetime(2026, 11, 13, 0, 50)          # a Friday, just after midnight
AFTERNOON = datetime(2026, 11, 13, 15, 0)    # the same Friday, 3 pm


def one(text, now=NOW):
    """Parse text that should give exactly one draft, and return it."""
    drafts = cp.parse(text, now)
    assert len(drafts) == 1, drafts
    return drafts[0]


class TheDoneWhenExamples(unittest.TestCase):
    """The two sentences from CALENDAR.md's "Done when"."""

    def test_homework_due_friday_11pm(self):
        d = one("CS31 hw due Friday 11pm")
        self.assertEqual(d.title, "CS31 hw due")
        self.assertEqual(d.start, datetime(2026, 11, 20, 23, 0))     # the COMING Friday, not today
        self.assertEqual(d.end, d.start + timedelta(hours=1))         # time but no end -> 1 hour
        self.assertIsNone(d.rrule)
        self.assertFalse(d.needs_review)

    def test_discussion_every_mon_wed_until_dec_5(self):
        d = one("Discussion every Mon/Wed 2pm until Dec 5")
        self.assertEqual(d.title, "Discussion")
        self.assertEqual(d.rrule, "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261205T235959Z")
        self.assertEqual(d.start, datetime(2026, 11, 16, 14, 0))     # first Monday, not today (a Friday)
        self.assertEqual(d.end, datetime(2026, 11, 16, 15, 0))
        self.assertTrue(d.repeats)
        self.assertEqual(cp.recurrence_summary(d.rrule), "Weekly on MO, WE until 12/05/2026")


class Recurrence(unittest.TestCase):
    def test_two_weekdays_mean_weekly_even_without_every(self):
        d = one("Lecture Mon, Wed, Fri 10am")
        self.assertEqual(d.title, "Lecture")
        self.assertEqual(d.rrule, "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR")
        self.assertEqual(d.start, datetime(2026, 11, 13, 10, 0))     # today is a Friday, so today counts

    def test_one_weekday_with_every_is_weekly(self):
        d = one("Office hours every Tuesday 3pm")
        self.assertEqual(d.rrule, "RRULE:FREQ=WEEKLY;BYDAY=TU")
        self.assertEqual(d.start, datetime(2026, 11, 17, 15, 0))

    def test_one_weekday_without_every_does_not_repeat(self):
        self.assertIsNone(one("Dentist Tuesday 3pm").rrule)

    def test_daily(self):
        d = one("Gym daily 7am")
        self.assertEqual(d.title, "Gym")
        self.assertEqual(d.rrule, "RRULE:FREQ=DAILY")

    def test_every_day(self):
        self.assertEqual(one("Stretch every day 9pm").rrule, "RRULE:FREQ=DAILY")

    def test_biweekly(self):
        d = one("Club biweekly Thursday 6pm")
        self.assertEqual(d.title, "Club")
        self.assertEqual(d.rrule, "RRULE:FREQ=WEEKLY;INTERVAL=2")
        self.assertEqual(d.start, datetime(2026, 11, 19, 18, 0))

    def test_until_with_a_year_keeps_the_year_out_of_the_time(self):
        d = one("Lab every Thursday 5pm until Dec 10, 2026")
        self.assertEqual(d.title, "Lab")
        self.assertEqual(d.start, datetime(2026, 11, 19, 17, 0))
        self.assertEqual(d.rrule, "RRULE:FREQ=WEEKLY;BYDAY=TH;UNTIL=20261210T235959Z")

    def test_until_that_is_not_a_date_is_left_alone(self):
        d = one("Standup every Mon 9am until whenever")
        self.assertEqual(d.rrule, "RRULE:FREQ=WEEKLY;BYDAY=MO")


class Until(unittest.TestCase):
    RULE = "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261205T235959Z"

    def test_changing_until_never_leaves_two(self):
        rule = self.RULE
        for day in (date(2027, 1, 1), date(2027, 2, 3), date(2027, 3, 4)):
            rule = cp.set_until(rule, day)
            self.assertEqual(rule.count("UNTIL="), 1, rule)
        self.assertEqual(rule, "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20270304T235959Z")

    def test_broken_untils_from_half_typed_years_are_all_removed(self):
        # The ECHO bug: a half-typed year left short UNTILs behind, and Google said 400.
        messy = "RRULE:FREQ=WEEKLY;UNTIL=00021205T235959Z;BYDAY=MO;UNTIL=2;UNTIL="
        self.assertEqual(cp.set_until(messy, date(2026, 12, 5)),
                         "RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20261205T235959Z")

    def test_clearing_until(self):
        self.assertEqual(cp.set_until(self.RULE, None), "RRULE:FREQ=WEEKLY;BYDAY=MO,WE")

    def test_no_rule_stays_no_rule(self):
        self.assertIsNone(cp.set_until(None, date(2026, 12, 5)))

    def test_get_until(self):
        self.assertEqual(cp.get_until(self.RULE), date(2026, 12, 5))
        self.assertIsNone(cp.get_until("RRULE:FREQ=DAILY"))
        self.assertIsNone(cp.get_until(None))


class Summary(unittest.TestCase):
    def test_no_repeat(self):
        self.assertEqual(cp.recurrence_summary(None), "Does not repeat")

    def test_no_end_date(self):
        self.assertEqual(cp.recurrence_summary("RRULE:FREQ=DAILY"), "Daily — no end date")


class Defaults(unittest.TestCase):
    def test_no_time_means_due_at_11_59_pm(self):
        d = one("CS31 hw due Friday")
        self.assertEqual(d.start, datetime(2026, 11, 20, 23, 59))
        self.assertEqual(d.end, d.start + timedelta(minutes=30))    # ECHO's length for an all-day "due"

    def test_a_time_already_past_today_means_tomorrow(self):
        d = one("Call mom 2pm", now=AFTERNOON)
        self.assertEqual(d.start, datetime(2026, 11, 14, 14, 0))

    def test_a_time_still_ahead_today_means_today(self):
        self.assertEqual(one("Call mom 5pm", now=AFTERNOON).start, datetime(2026, 11, 13, 17, 0))

    def test_a_past_date_means_next_year(self):
        self.assertEqual(one("Dentist Nov 2 10am").start, datetime(2027, 11, 2, 10, 0))

    def test_time_range_sets_the_end(self):
        d = one("Study group Saturday 2pm-4pm")
        self.assertEqual(d.title, "Study group")
        self.assertEqual((d.start, d.end), (datetime(2026, 11, 14, 14, 0), datetime(2026, 11, 14, 16, 0)))

    def test_time_range_with_to(self):
        d = one("Shift Sunday 9am to 11:30am")
        self.assertEqual(d.end, datetime(2026, 11, 15, 11, 30))

    def test_meal_words_stay_in_the_title(self):
        d = one("Lunch with Sam tomorrow at noon")
        self.assertEqual(d.title, "Lunch with Sam")
        self.assertEqual(d.start, datetime(2026, 11, 14, 12, 0))


class NeedsReview(unittest.TestCase):
    def test_nothing_understood_is_flagged_not_guessed_silently(self):
        d = one("buy milk")
        self.assertTrue(d.needs_review)
        self.assertEqual(d.title, "buy milk")
        self.assertEqual(d.start, datetime(2026, 11, 14, 9, 0))     # placeholder: tomorrow 9 am
        self.assertEqual(d.end, datetime(2026, 11, 14, 10, 0))

    def test_only_a_date_gives_the_whole_text_as_title(self):
        self.assertEqual(one("Friday 3pm").title, "Friday 3pm")


class Splitting(unittest.TestCase):
    def test_lines_and_semicolons_split_commas_do_not(self):
        text = "CS31 hw due Friday 11pm\nLecture Mon, Wed, Fri 10am; Gym daily 7am\n\n  "
        self.assertEqual(cp.split_into_segments(text),
                         ["CS31 hw due Friday 11pm", "Lecture Mon, Wed, Fri 10am", "Gym daily 7am"])

    def test_parse_gives_one_draft_per_segment(self):
        self.assertEqual([d.title for d in cp.parse("a Friday 1pm; b Saturday 2pm", NOW)], ["a", "b"])

    def test_empty_text_gives_no_drafts(self):
        self.assertEqual(cp.parse("  \n ; ", NOW), [])


if __name__ == "__main__":
    unittest.main()

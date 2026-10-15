from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from app.ai.natural_language import (
    event_category,
    extract_recurrence,
    extract_title,
    parse_datetime,
)
from app.ai.orchestrator import AIOrchestrator
from app.tools.calendar import _event_occurrences
from types import SimpleNamespace
from uuid import uuid4


class NaturalLanguageTests(unittest.TestCase):
    def setUp(self):
        self.reference = datetime(2026, 10, 6, 14, 0, tzinfo=ZoneInfo("Asia/Jakarta"))

    def test_parse_explicit_date_and_time_in_user_timezone(self):
        parsed = parse_datetime(
            "Besok jam 8 pagi",
            "Asia/Jakarta",
            require_date=True,
            reference=self.reference,
        )
        self.assertEqual(parsed, datetime(2026, 10, 7, 8, 0, tzinfo=ZoneInfo("Asia/Jakarta")))

    def test_parses_today_reminder_with_afternoon_time(self):
        reference = datetime(2026, 10, 7, 15, 27, tzinfo=ZoneInfo("Asia/Jakarta"))
        parsed = parse_datetime(
            "ingetin aku hari ini voli jam 5 sore",
            "Asia/Jakarta",
            require_date=True,
            reference=reference,
        )
        self.assertEqual(
            parsed,
            datetime(2026, 10, 7, 17, 0, tzinfo=ZoneInfo("Asia/Jakarta")),
        )

    def test_date_or_time_is_not_guessed_when_required(self):
        self.assertIsNone(
            parse_datetime("jam 8", "Asia/Jakarta", require_date=True, reference=self.reference)
        )
        self.assertIsNone(
            parse_datetime("besok", "Asia/Jakarta", reference=self.reference)
        )
        self.assertIsNone(
            parse_datetime(
                "hari ini jam 8",
                "Asia/Jakarta",
                require_date=True,
                reference=self.reference,
            )
        )

    def test_month_name_rolls_to_next_year_when_date_has_passed(self):
        parsed = parse_datetime(
            "15 januari jam 9",
            "Asia/Jakarta",
            require_date=True,
            reference=self.reference,
        )
        self.assertEqual(parsed.year, 2027)
        self.assertEqual((parsed.month, parsed.day, parsed.hour), (1, 15, 9))

    def test_extracts_event_and_task_titles(self):
        self.assertEqual(extract_title("Jadwalkan kuliah besok jam 09.00"), "kuliah")
        self.assertEqual(extract_title("Jumat harus kumpul laporan"), "kumpul laporan")
        self.assertEqual(
            extract_title("ingetin aku hari ini voli jam 5 sore"),
            "voli",
        )

    def test_classifies_core_indonesian_requests(self):
        self.assertEqual(
            AIOrchestrator.detect_intent("Besok jam 8 aku ada kuliah"),
            "CREATE_EVENT",
        )
        self.assertEqual(
            AIOrchestrator.detect_intent("Jumat harus kumpul laporan"),
            "CREATE_TASK",
        )
        self.assertEqual(
            AIOrchestrator.detect_intent("Ingatkan aku bayar listrik tanggal 15 jam 9"),
            "CREATE_REMINDER",
        )

    def test_event_category_and_weekly_recurrence(self):
        self.assertEqual(event_category("kuliah setiap Jumat"), "ACADEMIC")
        self.assertEqual(extract_recurrence("rapat setiap Jumat jam 10"), "WEEKLY:4")

    def test_daily_recurrence_expands_in_the_user_timezone(self):
        event = SimpleNamespace(
            id=uuid4(),
            title="Belajar",
            description=None,
            category="STUDY",
            start_at=datetime(2026, 10, 5, 1, 0),
            end_at=None,
            location=None,
            recurrence="DAILY",
            status="ACTIVE",
        )
        occurrences = _event_occurrences(
            event,
            datetime(2026, 10, 6, 0, 0),
            datetime(2026, 10, 9, 0, 0),
            "Asia/Jakarta",
        )
        self.assertEqual(len(occurrences), 3)
        self.assertEqual(occurrences[0]["start_at"], "2026-10-06T01:00:00+00:00")


if __name__ == "__main__":
    unittest.main()

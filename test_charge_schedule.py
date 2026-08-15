import unittest
from datetime import datetime

from charge_schedule import (
    TZ_BEIJING,
    build_charge_plan,
    next_scheduled_datetime,
    parse_schedule_time,
)


class ChargeScheduleTest(unittest.TestCase):
    def test_default_schedule_time_and_plan_fields(self):
        plan = build_charge_plan("50959132", 12, "0")

        self.assertEqual(plan["scheduled_time"], "06:05")
        self.assertEqual(plan["timezone"], "Asia/Shanghai")
        self.assertEqual(plan["device"], "50959132")
        self.assertEqual(plan["port"], "12")
        self.assertTrue(plan["port_free"])
        self.assertTrue(plan["ready"])

    def test_custom_schedule_time(self):
        plan = build_charge_plan("50959132", "12", "1", "07:30")

        self.assertEqual(plan["scheduled_time"], "07:30")
        self.assertFalse(plan["port_free"])
        self.assertFalse(plan["ready"])

    def test_rejects_invalid_schedule_time(self):
        with self.assertRaises(ValueError):
            parse_schedule_time("6:5")

    def test_schedules_later_today(self):
        now = datetime(2026, 8, 4, 5, 30, tzinfo=TZ_BEIJING)
        self.assertEqual(
            next_scheduled_datetime(now, "06:05"),
            datetime(2026, 8, 4, 6, 5, tzinfo=TZ_BEIJING),
        )

    def test_schedules_next_day_after_time_has_passed(self):
        now = datetime(2026, 8, 4, 6, 6, tzinfo=TZ_BEIJING)
        self.assertEqual(
            next_scheduled_datetime(now, "06:05"),
            datetime(2026, 8, 5, 6, 5, tzinfo=TZ_BEIJING),
        )


if __name__ == "__main__":
    unittest.main()

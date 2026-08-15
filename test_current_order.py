import unittest

from current_order import is_active_order, summarize_order


class CurrentOrderTest(unittest.TestCase):
    def test_missing_end_timestamp_is_active_candidate(self):
        record = {
            "devaddress": "50959132",
            "devport": 12,
            "startdt": 1786100000000,
            "enddt": 0,
        }
        self.assertTrue(is_active_order(record))
        summary = summarize_order(record)
        self.assertEqual(summary["device"], "50959132")
        self.assertEqual(summary["port"], 12)
        self.assertIsNone(summary["end_time"])

    def test_finished_record_is_not_active(self):
        record = {
            "devaddress": "50959132",
            "devport": 12,
            "startdt": 1786100000000,
            "enddt": 1786103600000,
            "endtype": 39,
        }
        self.assertFalse(is_active_order(record))

    def test_explicit_active_status_is_supported(self):
        record = {
            "device": "50959132",
            "port": "12",
            "status": "charging",
        }
        self.assertTrue(is_active_order(record))

    def test_neptune_compact_start_time_is_formatted(self):
        record = {
            "devaddress": "50959132",
            "devport": "12",
            "begindt": "20260811174957",
            "enddt": 1786442353000,
        }
        summary = summarize_order(record)
        self.assertEqual(summary["start_time"], "2026-08-11 17:49:57")


if __name__ == "__main__":
    unittest.main()

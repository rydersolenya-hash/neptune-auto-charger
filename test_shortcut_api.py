import unittest

from shortcut_api import parse_request


class ShortcutApiRequestTest(unittest.TestCase):
    def test_parses_device_port_time_and_amount(self):
        self.assertEqual(
            parse_request(
                {
                    "device": "50959132",
                    "port": "12",
                    "scheduled_time": "06:05",
                    "charge_money": 100,
                }
            ),
            ("50959132", "12", "06:05", 100),
        )

    def test_rejects_invalid_port(self):
        result = parse_request({"device": "50959132", "port": "0"})
        self.assertEqual(result.status, 400)


if __name__ == "__main__":
    unittest.main()

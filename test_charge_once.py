import unittest
from unittest.mock import patch

from charge_once import DEFAULT_CHARGE_MONEY, parse_args


class ChargeOnceTest(unittest.TestCase):
    def test_default_charge_amount(self):
        with patch("sys.argv", ["charge_once.py", "50959132", "12"]):
            args = parse_args()
        self.assertEqual(args.device, "50959132")
        self.assertEqual(args.port, "12")
        self.assertEqual(args.charge_money, DEFAULT_CHARGE_MONEY)


if __name__ == "__main__":
    unittest.main()

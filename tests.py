import os
import unittest
from decimal import Decimal
from pathlib import Path

import app


class ImporterTests(unittest.TestCase):
    def setUp(self):
        if app.DB_PATH.exists():
            app.DB_PATH.unlink()

    def test_import_detects_messy_csv_and_balances(self):
        report = app.import_csv(app.CSV_PATH)
        self.assertEqual(report["rows_seen"], 42)
        self.assertGreaterEqual(len(report["anomalies"]), 20)
        codes = {item["code"] for item in report["anomalies"]}
        expected_codes = {
            "duplicate_expense",
            "amount_normalized",
            "name_normalized",
            "missing_payer",
            "settlement_not_expense",
            "percentage_total_not_100",
            "currency_converted",
            "near_duplicate_conflict",
            "negative_amount",
            "missing_currency",
            "zero_amount",
            "inactive_member_in_split",
            "split_details_on_equal",
        }
        self.assertTrue(expected_codes.issubset(codes))

        summary = app.load_summary()
        total = sum(summary["balances"].values(), Decimal("0"))
        self.assertEqual(app.money(total), Decimal("0.00"))
        self.assertTrue(summary["suggestions"])


if __name__ == "__main__":
    unittest.main()
